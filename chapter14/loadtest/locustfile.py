"""Peak-day replay for the intake service (Listing 14.5).

Requires locust (see ../requirements.txt); it is not needed for the rest of the
chapter. Against the local intake service:

    uvicorn intake_service:app --port 8080          # from chapter14/
    locust -f loadtest/locustfile.py --host http://localhost:8080 --headless

Afterwards, GET /api/reconcile must report claims accepted = cases created =
claim.received events (the reconciliation row of Table 14.7).
"""
import random
import uuid

from locust import HttpUser, LoadTestShape, between, task

FAMILIES = ["fraud_cnp", "not_received", "not_as_described", "duplicate", "credit_not_processed"]
DUPLICATE_STORM_SHARE = 0.0     # set to 1.0 for the duplicate-storm test


def synthetic_claim():
    """A synthetic claim in the shape of the Chapter 8 generator's CRM claims.

    Kept local so the load test has no dependency on another chapter's code.
    """
    return {
        "claim_id": f"CLM-{uuid.uuid4().hex[:10]}",
        "amount": round(random.lognormvariate(4.3, 0.9), 2),
        "channel": random.choice(["app", "web", "phone"]),
        "intake_reason": random.choice(FAMILIES),
        "narrative": "I did not receive the item I paid for.",
        "retry_twice": random.random() < DUPLICATE_STORM_SHARE,
    }


class Claimant(HttpUser):
    wait_time = between(1, 3)

    @task
    def file_claim(self):
        claim = synthetic_claim()                 # from the Chapter 8 generator
        key = str(uuid.uuid4())
        with self.client.post("/api/claims", json=claim, name="file_claim",
                              headers={"Idempotency-Key": key},
                              catch_response=True) as response:
            if response.elapsed.total_seconds() > 0.5:
                response.failure("acknowledgement slower than 0.5 s")
        if claim.get("retry_twice"):              # the duplicate-storm test
            self.client.post("/api/claims", json=claim, name="file_claim_retry",
                             headers={"Idempotency-Key": key})


class PeakDay(LoadTestShape):
    """Users over time, compressed from the recorded peak day."""
    stages = [(300, 50), (900, 400), (1500, 1200), (1800, 1200), (2100, 50)]

    def tick(self):
        run_time = self.get_run_time()
        for end, users in self.stages:
            if run_time < end:
                return users, 20
        return None
