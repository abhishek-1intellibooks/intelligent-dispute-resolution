"""Send the chapter's worked example to the triage service (Table 9.11).

    python demo_request.py                              # in-process, with FastAPI's TestClient
    python demo_request.py --url http://127.0.0.1:8000  # against a running uvicorn server

The claim: a debit cardholder files in the app at 16:05 on a Thursday in
December for a $249.00 purchase from an online electronics merchant made
nineteen days earlier, chooses Other and writes the narrative below. The
assembly links clearing and authorization but finds no merchant order, and
487 claims are already in the queue.
"""
import argparse
import json
import warnings

warnings.filterwarnings("ignore", message=".*httpx.*")   # Starlette's TestClient notice

CLAIM = {
    "claim_id": "CL-DEMO-0001",
    "claim_received_at": "2025-12-11T16:05:00",
    "case_created_at": "2025-12-11T16:05:30",
    "channel": "app",
    "product": "debit",
    "amount": 249.00,
    "intake_reason": "other",
    "narrative": ("The order never arrived, the merchant will not respond, "
                  "and I do not recognise the name on my statement."),
    "mcc_group": "electronics",
    "card_present": False,
    "three_ds": True,
    "device_known": True,
    "recurring": False,
    "security_alert_7d": False,
    "days_since_txn": 19,
    "tenure_months": 46,
    "prior_disputes_12m": 0,
    "delivery_status": "no_link",
    "link_completeness": 2,
    "needs_review": False,
    "queue_depth": 487,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="base URL of a running service, e.g. http://127.0.0.1:8000")
    args = parser.parse_args()
    if args.url:
        import httpx
        response = httpx.post(f"{args.url.rstrip('/')}/triage", json=CLAIM, timeout=30)
    else:
        from fastapi.testclient import TestClient

        from triage_service import app
        response = TestClient(app).post("/triage", json=CLAIM)
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
