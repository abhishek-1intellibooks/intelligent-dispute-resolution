"""Tests for the feature registry, calibration helpers and the decision rules.

Run from chapter10/:  python -m pytest -q
Requires outcome_logistic_platt.joblib (python train_outcome.py).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calibration import expected_calibration_error, logit  # noqa: E402
from fight_or_accept import (CONTEST_COST, REVIEW_MARGIN, TIME_LIMIT_DAYS,  # noqa: E402
                             contest_threshold, fight_or_accept)
from outcome_features import FEATURES, decision_view  # noqa: E402
from worked_example import CASES  # noqa: E402


@pytest.fixture
def cases():
    return pd.DataFrame.from_dict(CASES, orient="index")


def test_decision_view_refuses_outcome_and_simulator_columns(cases):
    assert list(decision_view(cases).columns) == FEATURES
    for late in ("won", "won_if_contested", "p_true"):
        with pytest.raises(ValueError):
            decision_view(cases.assign(**{late: 1}), FEATURES + [late])


def test_contest_threshold_matches_chapter6():
    assert contest_threshold(0.4, 40) == pytest.approx(100.0)
    assert contest_threshold(0.5, 40, attrition=0.05, value=600) == pytest.approx(140.0)


def test_logit_and_ece():
    assert logit(np.array([0.5]))[0, 0] == pytest.approx(0.0)
    y = np.array([0, 1] * 50)
    assert expected_calibration_error(y, np.full(100, 0.5)) == pytest.approx(0.0)
    assert expected_calibration_error(y, np.full(100, 0.7)) == pytest.approx(0.2)


def test_rules_in_order_of_precedence(cases):
    out = fight_or_accept(cases)
    ev = out.expected_value
    assert ((out.decision == "review") == (ev.abs() < REVIEW_MARGIN)).all()
    assert (out.decision[ev >= REVIEW_MARGIN] == "contest").all()
    assert (out.decision[ev <= -REVIEW_MARGIN] == "accept").all()
    assert np.allclose(out.expected_value,
                       (out.p_win * cases.amount - CONTEST_COST).round(2), atol=0.6)
    assert (out.model_version == "outcome-1.0").all()


def test_time_limit_overrides_everything(cases):
    out = fight_or_accept(cases.assign(days_to_file=TIME_LIMIT_DAYS + 1))
    assert (out.decision == "accept").all()
    assert (out.reason == "past the time limit").all()


def test_capacity_keeps_the_best(cases):
    free = fight_or_accept(cases)
    capped = fight_or_accept(cases, capacity=1)
    contested = free[free.decision == "contest"]
    best = contested.expected_value.idxmax()
    assert (capped.decision == "contest").sum() == 1
    assert capped.loc[best, "decision"] == "contest"
    cut = contested.index.drop(best)
    assert (capped.loc[cut, "reason"] == "below the capacity cut").all()


def test_relationship_term_lowers_expected_value(cases):
    base = fight_or_accept(cases)
    fp = fight_or_accept(cases, attrition=0.05, value=600)
    assert np.allclose(base.expected_value - fp.expected_value, 30.0, atol=0.02)
