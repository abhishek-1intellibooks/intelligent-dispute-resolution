"""Event handlers that bind the earlier chapters' components to the event log.

Each handler has the signature ``handler(conn, event)`` used by
consumer.handle (Listing 14.2): it does its work and writes its own events to
the outbox in the transaction that handle() opened. The chapter components are
imported lazily from the module copied into the image (see Dockerfile.worker),
using the interfaces shown in the book's listings:

  case_and_clocks  Ch. 2, 3, 8   self-contained here: case state and clock rows
  triage           Ch. 9         HTTP call to chapter09/triage_service.py (/triage)
  recovery         Ch. 10        chapter10/fight_or_accept.py: fight_or_accept(cases)
  evidence         Ch. 11        chapter11/evidence_pipeline.py: build_evidence(case, readings, review)
  writer           Ch. 12        chapter12/service.py: produce(kind, case, evidence, decision, writer, log)
  agent            Ch. 13        chapter13/agent.py: run_agent(case, model, world)

These adapters run only inside the deployed images, against PostgreSQL and the
event log; this chapter's local tests exercise the patterns (events.py,
consumer.py) rather than the adapters.
"""
import json
import os
from dataclasses import asdict
from datetime import date, datetime, timedelta

from events import Event

CLOCK_BUSINESS_DAYS = 10          # Regulation E first deadline (Chapter 2)


def emit(conn, case_id, type_, data, producer):
    event = Event(type_, case_id, data, producer=producer)
    conn.execute("INSERT INTO outbox (event_id, case_id, type, payload) VALUES (%s, %s, %s, %s)",
                 (event.event_id, case_id, event.type, json.dumps(asdict(event), default=str)))
    return event


def add_business_days(start: date, n: int) -> date:
    d = start
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def case_and_clocks(conn, event):
    """Deadlines are data: a clock row, scanned every minute, never a timer in memory."""
    if event["type"] == "claim.received":
        received = datetime.fromisoformat(event["occurred_at"]).date()
        due = add_business_days(received, CLOCK_BUSINESS_DAYS)
        conn.execute("INSERT INTO clocks (case_id, clock, started_on, due_on) VALUES (%s, %s, %s, %s) "
                     "ON CONFLICT DO NOTHING", (event["case_id"], "reg_e_investigation", received, due))
        emit(conn, event["case_id"], "clock.started", {"clock": "reg_e_investigation", "due_on": str(due)},
             "case")
    conn.execute("INSERT INTO case_history (case_id, event_id, type, payload) VALUES (%s, %s, %s, %s)",
                 (event["case_id"], event["event_id"], event["type"], json.dumps(event)))
case_and_clocks.name = "case"


def triage(conn, event):
    import httpx
    from consumer import Retryable
    url = os.environ.get("TRIAGE_URL", "http://triage:8000/triage")
    try:
        r = httpx.post(url, json=event["data"], timeout=2.0)
    except httpx.TransportError as exc:
        raise Retryable(repr(exc))
    if r.status_code in (429, 503):
        raise Retryable(f"triage returned {r.status_code}")
    r.raise_for_status()
    emit(conn, event["case_id"], "claim.classified", r.json(), "triage")
triage.name = "triage"


def recovery(conn, event):
    import pandas as pd
    from fight_or_accept import fight_or_accept
    case = pd.DataFrame([event["data"]["case"]])
    decision = fight_or_accept(case).iloc[0].to_dict()
    emit(conn, event["case_id"], "recovery.decided", decision, "recovery")
recovery.name = "recovery"


def evidence(conn, event):
    from evidence_pipeline import build_evidence
    d = event["data"]
    record = build_evidence(d["case"], d["readings_by_fact"], d.get("review"))
    emit(conn, event["case_id"], "evidence.scored", record, "evidence")
evidence.name = "evidence"


def writer(conn, event):
    import service
    d = event["data"]
    result = service.produce(d.get("kind", "letter"), d["case"], d.get("evidence"), d.get("decision"),
                             writer=None, log=None)
    emit(conn, event["case_id"], "letter.drafted", {"status": result["status"]}, "writer")
writer.name = "writer"


def agent(conn, event):
    from agent import run_agent
    d = event["data"]
    result = run_agent(d["case"], model=d.get("model"), world=d.get("world"))
    kind = "case.escalated" if result.get("status") == "escalated" else "agent.action_taken"
    emit(conn, event["case_id"], kind, result, "agent")
agent.name = "agent"
