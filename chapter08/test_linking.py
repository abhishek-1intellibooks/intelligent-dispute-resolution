"""Tests for the linking rules and the case schema.  Run: python -m pytest -q"""
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from linking import link_claim, match, norm, similar

HERE = Path(__file__).resolve().parent
T = pd.Timestamp


def test_norm_strips_digits_and_punctuation():
    assert norm("GRANITETOYS*5274") == "granitetoys"


def test_worked_example_similarity():
    assert round(similar("Granite", "GRANITETOYS*5274"), 2) == 0.78


def clearing_frame(rows):
    return pd.DataFrame(rows, columns=["arn", "card_token", "merchant_id", "descriptor",
                                       "amount", "auth_code", "cleared_at"])


def claim(**kw):
    base = dict(card_token="tok1", claimed_amount=50.0, merchant_stated="Granite",
                claim_received_at=T("2025-03-20 11:31"))
    base.update(kw)
    return SimpleNamespace(**base)


def test_name_match_and_window():
    clr = clearing_frame([
        ("1", "tok1", "M1", "GRANITETOYS*5274", 50.0, "AAAAAA", T("2025-03-03")),
        ("2", "tok1", "M2", "HARBORBOOKS*1111", 51.0, "BBBBBB", T("2025-03-05")),
        ("3", "tok1", "M1", "GRANITETOYS*5274", 50.0, "CCCCCC", T("2024-10-01")),  # outside 120 days
    ])
    arn, how, conf, close = link_claim(claim(), clr)
    assert (arn, how, close) == ("1", "name", False)
    assert conf == 0.78


def test_subscription_is_flagged_ambiguous():
    clr = clearing_frame([
        ("1", "tok1", "M1", "BLOOMBOX*1234", 20.0, "A", T("2025-02-03")),
        ("2", "tok1", "M1", "BLOOMBOX*1234", 20.0, "B", T("2025-03-03")),
    ])
    arn, how, _, close = link_claim(claim(claimed_amount=20.0, merchant_stated="Bloom Box"), clr)
    assert how == "name" and close and arn == "2"      # latest charge, sent to review


def test_amount_only_and_none():
    clr = clearing_frame([("1", "tok1", "M1", "GRANITETOYS*5274", 50.0, "A", T("2025-03-03"))])
    assert link_claim(claim(merchant_stated="web shop"), clr)[1] == "amount_only"
    assert link_claim(claim(claimed_amount=90.0), clr)[1] == "none"


def test_match_never_joins_on_null_key():
    pool = pd.DataFrame({"order_id": ["O1", "O2"], "merchant_id": ["M1", "M1"],
                         "auth_code": [None, None], "order_total": [10.0, 99.0],
                         "ordered_at": [T("2025-03-01"), T("2025-03-02")]})
    clr = SimpleNamespace(auth_code=None, merchant_id="M1", amount=99.0,
                          cleared_at=T("2025-03-03"), card_token="tok1")
    # a null code must not "match" the null-coded order O1; the fallback finds O2 by amount
    assert match(clr, pool, "order_id", "order_total", "ordered_at") == ("O2", "fuzzy", 0.7)


def test_unique_index_allows_duplicates_only_when_marked():
    con = sqlite3.connect(":memory:")
    con.executescript((HERE / "dispute_schema.sql").read_text(encoding="utf-8"))
    ins = ("INSERT INTO case_record (case_id, claim_id, arn, claim_received_at, completeness,"
           " duplicate_of, rule_version) VALUES (?, 'C1', 'ARN1', '2025-03-20', 1, ?, 'v')")
    con.execute(ins, ("CASE1", None))
    con.execute(ins, ("CASE2", "CASE1"))                 # a duplicate claim: allowed
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins, ("CASE3", None))                # a second live case: refused


@pytest.mark.skipif(not (HERE / "dispute.db").exists(), reason="run assemble_case.py first")
def test_assembled_counts():
    con = sqlite3.connect(HERE / "dispute.db")
    total, full, linked = con.execute(
        "SELECT COUNT(*), SUM(completeness = 3), SUM(arn IS NOT NULL) FROM case_record").fetchone()
    assert (total, full, linked) == (435, 408, 420)
    case = con.execute("SELECT case_id FROM case_record WHERE claim_id = 'C00001'").fetchone()[0]
    assert case == "CASE00103"
