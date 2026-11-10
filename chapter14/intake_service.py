"""Event-driven intake: validate, record the claim and its event, reply (Chapter 14).

Acknowledge fast, work later. The request does about a database write's worth
of work: it checks the Idempotency-Key, writes the case and a claim.received
event to the outbox in one transaction, and replies 202 with the case id. The
same key sent twice returns the same case (the duplicate-storm test of
Table 14.7). /api/reconcile returns the three counts that must agree after every
load test: claims accepted, cases created and claim.received events.

Run:  uvicorn intake_service:app --port 8080
"""
import json
import os
import threading
import uuid
from dataclasses import asdict

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from events import Event, LocalConnection

DB_PATH = os.environ.get("INTAKE_DB", ":memory:")

app = FastAPI(title="intake")
_conn = LocalConnection(DB_PATH)
_conn.execute("CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, case_id TEXT NOT NULL)")
_lock = threading.Lock()          # sqlite allows one writer; PostgreSQL would not need this
_accepted = {"count": 0}


class ClaimIn(BaseModel):
    claim_id: str
    amount: float = Field(gt=0)
    channel: str = "app"
    intake_reason: str
    narrative: str = ""
    retry_twice: bool = False


@app.post("/api/claims", status_code=202)
def file_claim(claim: ClaimIn, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    with _lock:
        row = _conn.query("SELECT case_id FROM idempotency WHERE key = %s", (idempotency_key,))
        if row:
            return {"case_id": row[0][0], "status": "received", "duplicate": True}
        case_id = f"C-{uuid.uuid4().hex[:12]}"
        event = Event("claim.received", case_id, claim.model_dump(), producer="intake")
        try:
            with _conn.transaction():
                _conn.execute("INSERT INTO idempotency (key, case_id) VALUES (%s, %s)", (idempotency_key, case_id))
                _conn.execute("INSERT INTO cases (case_id, state) VALUES (%s, %s)", (case_id, "RECEIVED"))
                _conn.execute("INSERT INTO outbox (event_id, case_id, type, payload) VALUES (%s, %s, %s, %s)",
                              (event.event_id, case_id, event.type, json.dumps(asdict(event))))
        except Exception as exc:  # pragma: no cover - surfaced to the client
            raise HTTPException(status_code=503, detail=repr(exc))
        _accepted["count"] += 1
        return {"case_id": case_id, "status": "received", "duplicate": False}


@app.get("/api/reconcile")
def reconcile():
    with _lock:
        cases = _conn.query("SELECT COUNT(*) FROM cases")[0][0]
        events = _conn.query("SELECT COUNT(*) FROM outbox WHERE type = 'claim.received'")[0][0]
    return {"claims_accepted": _accepted["count"], "cases_created": cases,
            "claim_received_events": events,
            "reconciled": _accepted["count"] == cases == events}


@app.get("/healthz")
def healthz():
    return {"ok": True}
