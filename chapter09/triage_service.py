"""The triage service (Listing 9.5).

Run:  uvicorn triage_service:app        (from inside chapter09/)
POST /triage with a claim's intake fields; the response gives the family with
its probabilities and reasons, the SLA risk, the priority band, the queue and
the versions of the models that produced them. The service routes; it never
decides a claim.
"""
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel

from features import intake_view
from priority import band, route, sla_frame

HERE = Path(__file__).resolve().parent
FAMILY = joblib.load(HERE / "triage_model.joblib")
SLA = joblib.load(HERE / "sla_model.joblib")
app = FastAPI(title="triage")


class Claim(BaseModel):
    claim_id: str
    claim_received_at: datetime
    case_created_at: datetime
    channel: str
    product: str
    amount: float
    intake_reason: str
    narrative: str
    mcc_group: str
    card_present: bool
    three_ds: bool
    device_known: bool
    recurring: bool
    security_alert_7d: bool
    days_since_txn: int
    tenure_months: int
    prior_disputes_12m: int
    delivery_status: str
    link_completeness: int
    needs_review: bool
    queue_depth: int


def reasons(model, row, family, k=3):
    """The k input columns that pushed hardest towards the chosen family."""
    pre, clf = model.steps[0][1], model.steps[-1][1]
    weights = clf.coef_[list(clf.classes_).index(family)]
    contrib = pre.transform(row).toarray()[0] * weights
    total = {}
    for name, c in zip(pre.get_feature_names_out(), contrib):
        group, value = name.split("__")
        column = "narrative" if group == "text" else next(
            col for col in row.columns if value.startswith(col))
        total[column] = total.get(column, 0.0) + c
    top = sorted(total, key=total.get, reverse=True)[:k]
    return {col: round(total[col], 2) for col in top if total[col] > 0}


@app.post("/triage")
def triage(claim: Claim):
    row = pd.DataFrame([claim.model_dump()])
    model = FAMILY["family"]
    p = pd.DataFrame(model.predict_proba(intake_view(row)), columns=model.classes_)
    family, confidence = p.iloc[0].idxmax(), float(p.iloc[0].max())
    risk = float(SLA["sla"].predict_proba(sla_frame(row, p, SLA["effort"]))[0, 1])
    return {"claim_id": claim.claim_id,
            "family": family, "confidence": round(confidence, 2),
            "probabilities": p.iloc[0].round(2).to_dict(),
            "reasons": reasons(model, intake_view(row), family),
            "sla_risk": round(risk, 2),
            "priority": band(risk, family, claim.amount, claim.security_alert_7d),
            "queue": route(family, confidence),
            "model_versions": [FAMILY["version"], SLA["version"]]}
