"""Expected effort, SLA-risk inputs and the triage policy (Listing 9.4).

expected_work and sla_frame compute the inputs of the SLA-risk model; band
and route are the policy: plain functions with named thresholds that can be
changed without retraining anything.
"""
import numpy as np
import pandas as pd

from queue_sim import CLOCK_DAYS, DAILY_STARTS, as_day

FAMILIES = ["unauthorized", "defective", "first_party"]
SLA_FEATURES = ["slack_days", "queue_days", "expected_work"]
QUEUE = {"unauthorized": "fraud_claims", "defective": "merchant_disputes",
         "first_party": "first_party_review"}
MIN_CONFIDENCE = 0.70          # below this the claim goes to triage_review


def expected_work(d, p, effort):
    """Business days of effort, averaged over the family probabilities."""
    contact = d.delivery_status.isin(["not_found", "no_link"])
    keys = list(zip(contact, d.needs_review.astype(bool)))
    return sum(p[f].to_numpy() * effort[f].reindex(keys).to_numpy()
               for f in FAMILIES)


def sla_frame(d, p, effort):
    created = d.case_created_at
    late = (created.dt.hour >= 17).astype(int)      # after 17:00: next day
    avail = np.busday_offset(as_day(created), late, roll="forward")
    due = np.busday_offset(as_day(d.claim_received_at), CLOCK_DAYS,
                           roll="backward")
    return pd.DataFrame({"slack_days": np.busday_count(avail, due),
                         "queue_days": d.queue_depth / DAILY_STARTS,
                         "expected_work": expected_work(d, p, effort)},
                        index=d.index)


def band(risk, family, amount, security_alert):
    if risk >= 0.5 or (family == "unauthorized" and security_alert):
        return "P1"
    if risk >= 0.2 or (family == "unauthorized" and amount >= 1000):
        return "P2"
    return "P3"


def route(family, confidence):
    return QUEUE[family] if confidence >= MIN_CONFIDENCE else "triage_review"
