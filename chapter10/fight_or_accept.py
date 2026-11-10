"""Contest, accept or review each case, with the numbers behind it (Listing 10.4).

Loads the calibrated model written by train_outcome.py. Rules are applied in
the order of Table 10.5: the sign of the expected value, then the review band,
then the network time limit, then the capacity cut.
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from outcome_features import decision_view

HERE = Path(__file__).resolve().parent

CONTEST_COST = 40.0       # handling plus network fees, as in Chapter 6
REVIEW_MARGIN = 5.0       # |expected value| below this goes to an analyst
TIME_LIMIT_DAYS = 120     # network time limit for filing (illustrative)
MODEL = joblib.load(HERE / "outcome_logistic_platt.joblib")
VERSION = "outcome-1.0"


def contest_threshold(p_win, cost, attrition=0.0, value=0.0):
    """Chapter 6: contesting pays when A > (c + qV) / p."""
    return (cost + attrition * value) / max(p_win, 1e-6)


def fight_or_accept(cases, attrition=0.0, value=0.0, capacity=None):
    """Contest, accept or review each case, with the numbers behind it.

    attrition and value apply only when contesting challenges the
    cardholder (Chapter 6); recovery from a merchant leaves them at 0.
    """
    p = MODEL.predict_proba(decision_view(cases))
    ev = p * cases.amount - CONTEST_COST - attrition * value
    out = pd.DataFrame({
        "p_win": p.round(3),
        "expected_value": ev.round(2),
        "threshold": [round(contest_threshold(x, CONTEST_COST, attrition,
                                              value), 2) for x in p],
    }, index=cases.index)
    out["decision"] = np.where(ev > 0, "contest", "accept")
    out["reason"] = out.expected_value.map("expected value ${:,.2f}".format)
    close = ev.abs() < REVIEW_MARGIN
    out.loc[close, ["decision", "reason"]] = ["review", "too close to call"]
    late = cases.days_to_file > TIME_LIMIT_DAYS
    out.loc[late, ["decision", "reason"]] = ["accept", "past the time limit"]
    if capacity is not None:                  # best expected value first
        best = out[out.decision == "contest"].expected_value
        cut = best.rank(ascending=False) > capacity
        out.loc[cut[cut].index, ["decision", "reason"]] = [
            "accept", "below the capacity cut"]
    out["model_version"] = VERSION
    return out


if __name__ == "__main__":
    df = pd.read_csv(HERE / "contest_history.csv", parse_dates=["decided_at"])
    window = df[df.decided_at >= "2025-09-01"]
    decided = fight_or_accept(window)
    print(f"fight_or_accept on {len(window):,} cases, September to December")
    print(decided.decision.value_counts().to_string())
    print(decided.reason.where(~decided.reason.str.startswith("expected"),
                               "expected value").value_counts().to_string())
