import asyncio
import json
import py_compile
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from budget import TokenBudget  # noqa: E402
from consumer import MAX_ATTEMPTS, DeadLetterQueue, MerchantInquiry, Message, Retryable, deliver, handle  # noqa: E402
from events import Event, EventLog, LocalConnection, StaleState, open_case, relay, transition  # noqa: E402


def test_transition_writes_state_and_event_together():
    conn = LocalConnection()
    open_case(conn, "C-1")
    transition(conn, "C-1", "RECEIVED", "INVESTIGATING", Event("case.state_changed", "C-1", {}, "case"))
    assert conn.query("SELECT state, version FROM cases") == [("INVESTIGATING", 1)]
    assert conn.query("SELECT COUNT(*) FROM outbox")[0][0] == 2


def test_stale_transition_writes_nothing():
    conn = LocalConnection()
    open_case(conn, "C-1")
    with pytest.raises(StaleState):
        transition(conn, "C-1", "INVESTIGATING", "CLOSED", Event("case.state_changed", "C-1", {}, "agent"))
    assert conn.query("SELECT state FROM cases")[0][0] == "RECEIVED"
    assert conn.query("SELECT COUNT(*) FROM outbox")[0][0] == 1


def test_relay_crash_publishes_again():
    conn, log = LocalConnection(), EventLog()
    open_case(conn, "C-1")
    with pytest.raises(ConnectionError):
        relay(conn, log, fail_after=0)
    relay(conn, log)
    assert len(list(log.messages())) == 2          # at least once
    assert conn.query("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL")[0][0] == 0


def test_consumer_skips_duplicates():
    producer, conn, log = LocalConnection(), LocalConnection(), EventLog()
    open_case(producer, "C-1")
    relay(producer, log)
    msg = list(log.messages())[0]
    h, dlq = MerchantInquiry(), DeadLetterQueue()
    assert handle(conn, Message(msg), h, dlq) == "ok"
    assert handle(conn, Message(msg), h, dlq) == "duplicate"
    assert conn.query("SELECT COUNT(*) FROM inquiries")[0][0] == 1


def test_failures_roll_back_then_dead_letter():
    producer, conn, log = LocalConnection(), LocalConnection(), EventLog()
    open_case(producer, "C-9")
    relay(producer, log)
    msg = list(log.messages())[0]
    h, dlq = MerchantInquiry(fail_on={"C-9"}), DeadLetterQueue()
    assert deliver(conn, msg, h, dlq) == "dead_lettered"
    assert h.calls == MAX_ATTEMPTS
    assert dlq.depth() == 1
    assert conn.query("SELECT COUNT(*) FROM processed")[0][0] == 0      # work rolled back


def test_retryable_is_reraised_and_rolled_back():
    producer, conn, log = LocalConnection(), LocalConnection(), EventLog()
    open_case(producer, "C-2")
    relay(producer, log)

    def throttled(conn, event):
        raise Retryable("429")
    throttled.name = "writer"
    with pytest.raises(Retryable):
        handle(conn, Message(list(log.messages())[0], attempts=MAX_ATTEMPTS), throttled, DeadLetterQueue())
    assert conn.query("SELECT COUNT(*) FROM processed")[0][0] == 0


def test_token_budget_serves_urgent_first():
    async def run():
        budget = TokenBudget(6_000_000)
        budget.tokens = 0
        order = []

        async def req(kind):
            await budget.acquire(5_000, urgent=(kind == "urgent"))
            order.append(kind)
        await asyncio.gather(*[req("normal") for _ in range(6)], *[req("urgent") for _ in range(3)])
        return order
    order = asyncio.run(run())
    assert order[:3] == ["urgent"] * 3


def test_intake_is_idempotent_and_reconciles():
    from fastapi.testclient import TestClient
    import intake_service
    client = TestClient(intake_service.app)
    claim = {"claim_id": "CLM-1", "amount": 249.0, "intake_reason": "not_received"}
    a = client.post("/api/claims", json=claim, headers={"Idempotency-Key": "k-1"})
    b = client.post("/api/claims", json=claim, headers={"Idempotency-Key": "k-1"})
    assert a.status_code == b.status_code == 202
    assert a.json()["case_id"] == b.json()["case_id"] and b.json()["duplicate"]
    rec = client.get("/api/reconcile").json()
    assert rec["reconciled"] and rec["cases_created"] == 1


def test_deploy_manifests_parse_and_writer_rule_matches_listing():
    for path in (HERE / "deploy").rglob("*.yaml"):
        list(yaml.safe_load_all(path.read_text()))
    so = yaml.safe_load((HERE / "deploy" / "writer-scaledobject.yaml").read_text())
    assert so["kind"] == "ScaledObject"
    assert (so["spec"]["minReplicaCount"], so["spec"]["maxReplicaCount"], so["spec"]["cooldownPeriod"]) == (2, 20, 300)
    assert so["spec"]["triggers"][0]["metadata"]["lagThreshold"] == "50"
    # The writer's maximum is set from the token limit: 20 workers x 10 drafts = 200 = 1M / 5,000.
    import peak_day
    assert so["spec"]["maxReplicaCount"] * peak_day.DRAFTS_PER_WORKER_MINUTE == \
        peak_day.TOKENS_PER_MINUTE / peak_day.TOKENS_PER_CLAIM


def test_python_files_compile():
    for path in [HERE / "loadtest" / "locustfile.py", *(HERE / "deploy").glob("*.py")]:
        py_compile.compile(str(path), doraise=True)


def test_cost_per_claim_matches_table_14_6():
    import peak_day
    cost = peak_day.cost_per_claim()
    assert round(cost.dollars.sum() * 100, 1) == 11.8
    assert list(cost.cents.round(2)) == [7.29, 2.70, 0.77, 0.54, 0.40, 0.05]


def test_event_driven_intake_stays_flat_until_saturation():
    import peak_day
    idle = peak_day.mmc_p99(160, 0.04, 1e-6)
    assert abs(idle - 0.184) < 0.002
    assert peak_day.mmc_p99(160, 0.04, 0.9) / idle < 1.01
    assert peak_day.mmc_p99(16, 6.5, 0.9) / idle > 1


def test_event_json_round_trip():
    ev = Event("evidence.scored", "C-1", {"score": 0.95}, producer="evidence")
    assert json.loads(json.dumps(ev.__dict__))["schema_version"] == 1
