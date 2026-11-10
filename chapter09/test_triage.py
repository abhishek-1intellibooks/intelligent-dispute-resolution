"""Tests for the feature guard, the policy and the service.  Run: python -m pytest -q
The service tests need triage_model.joblib and sla_model.joblib
(python train_classifier.py && python sla_risk.py)."""
import warnings
from pathlib import Path

import pandas as pd
import pytest

from features import intake_view
from priority import band, route

warnings.filterwarnings("ignore", message=".*httpx.*")
HERE = Path(__file__).resolve().parent
MODELS = (HERE / "triage_model.joblib").exists() and (HERE / "sla_model.joblib").exists()


def test_intake_view_refuses_late_columns():
    df = pd.DataFrame({"amount": [10.0], "first_touch_on": ["2025-01-02"]})
    with pytest.raises(ValueError, match="first_touch_on"):
        intake_view(df, ["amount", "first_touch_on"])
    assert list(intake_view(df, ["amount"]).columns) == ["amount"]


@pytest.mark.parametrize("risk,family,amount,alert,expected", [
    (0.55, "defective", 50, False, "P1"),
    (0.05, "unauthorized", 50, True, "P1"),
    (0.25, "first_party", 50, False, "P2"),
    (0.05, "unauthorized", 1500, False, "P2"),
    (0.05, "defective", 5000, False, "P3"),
])
def test_band(risk, family, amount, alert, expected):
    assert band(risk, family, amount, alert) == expected


def test_route_abstains_below_threshold():
    assert route("defective", 0.71) == "merchant_disputes"
    assert route("unauthorized", 0.69) == "triage_review"


@pytest.mark.skipif(not MODELS, reason="train the models first")
def test_service_worked_example():
    from fastapi.testclient import TestClient

    from demo_request import CLAIM
    from triage_service import app
    client = TestClient(app)
    out = client.post("/triage", json=CLAIM).json()
    assert out["family"] == "defective"
    assert abs(sum(out["probabilities"].values()) - 1) < 0.02
    assert "narrative" in out["reasons"]
    assert out["priority"] in {"P1", "P2", "P3"}
    assert out["queue"] in {"merchant_disputes", "triage_review"}
    assert out["model_versions"] == ["triage-family-1.0", "triage-sla-1.0"]
    bad = {k: v for k, v in CLAIM.items() if k != "narrative"}
    assert client.post("/triage", json=bad).status_code == 422     # rejected before any model runs
