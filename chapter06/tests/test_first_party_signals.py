import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from first_party_signals import (AS_OF, build_signals, concentration,  # noqa: E402
                                 contest_threshold, first_party_only, load,
                                 score_signals)


@pytest.fixture(scope="module")
def disputes():
    return load()


@pytest.fixture(scope="module")
def scored(disputes):
    return score_signals(build_signals(first_party_only(disputes), AS_OF))


def test_extension_adds_four_columns_to_chapter01(disputes):
    base = pd.read_csv(HERE.parent / "chapter01" / "disputes_sample.csv")
    assert list(disputes.columns) == list(base.columns) + [
        "card_id", "merchant_id", "reason", "delivery_confirmed"]
    assert len(disputes) == len(base) == 5000
    assert (disputes["case_id"] == base["case_id"]).all()
    assert disputes["delivery_confirmed"].dtype == bool


def test_concentration_close_to_chapter(disputes):
    assert 0.10 <= concentration(disputes) <= 0.12


@pytest.mark.parametrize("card,claims,nr,top,proof,gap,points,tier", [
    ("c741", 6, 0.83, 0.17, 0.67, 6.0, 7, "review"),
    ("c2677", 3, 1.00, 0.33, 0.33, 6.5, 4, "clarify"),
    ("c3578", 2, 0.50, 0.50, 1.00, 57.0, 2, "standard"),
])
def test_table_6_5(scored, card, claims, nr, top, proof, gap, points, tier):
    r = scored.loc[card]
    assert r.claims == claims
    assert round(r.not_received_share, 2) == nr
    assert round(r.top_merchant_share, 2) == top
    assert round(r.proof_rate, 2) == proof
    assert r.median_gap_days == gap
    assert r.points == points and r.tier == tier


def test_worked_example_goes_to_review(scored):
    r = scored.loc["c1024"]
    assert (r.claims, r.not_received_share, r.top_merchant_share, r.proof_rate) == (4, 1.0, 0.25, 0.75)
    assert r.tier == "review"
    assert "delivery confirmed on most" in r.reasons


def test_concentration_at_one_merchant_subtracts_points():
    t = pd.Timestamp("2026-09-01")
    df = pd.DataFrame({
        "card_id": ["x"] * 4,
        "opened_at": [t + pd.Timedelta(i * 3, unit="D") for i in range(4)],
        "reason": ["not_received"] * 4,
        "merchant_id": ["m1"] * 4,
        "delivery_confirmed": [False] * 4,
    })
    r = score_signals(build_signals(df, "2026-09-30")).loc["x"]
    assert r.points == 3 and r.tier == "clarify"
    assert "concentrated at one merchant" in r.reasons


def test_as_of_anchor_prevents_leakage(disputes):
    early = build_signals(first_party_only(disputes), "2026-09-10")
    # c741's claims after 10 September are not visible on 10 September
    assert early.loc["c741", "claims"] < 6


@pytest.mark.parametrize("value,p,expected", [
    (0, 0.42, 95), (150, 0.42, 113), (150, 0.70, 68), (2000, 0.42, 333),
    (2000, 0.70, 200), (600, 0.42, 167), (600, 0.70, 100),
])
def test_contest_threshold_table_6_3(value, p, expected):
    assert round(contest_threshold(p, 40, 0.05, value)) == expected
