import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from audit import AuditLog, MemoryStore, WriteOnceCheckpoints, verify  # noqa: E402
from fairness import fairness_report  # noqa: E402
from reasons import reason_codes  # noqa: E402
from redact import luhn_ok, redact, redact_v1, redact_v2  # noqa: E402


def test_luhn():
    assert luhn_ok("4111111111111111") and not luhn_ok("4111111111111112")


@pytest.mark.parametrize("text", ["card 4111 1111 1111 1111 please", "card 4111-1111-1111-1111.",
                                  "card 4111111111111111", "amex 3782 822463 10005"])
def test_v3_removes_card_numbers_with_separators(text):
    assert "[card number]" in redact(text)


def test_v3_keeps_labelled_order_numbers_and_v1_destroys_them():
    text = "Order #4111111111111111 arrived late"     # passes the checksum but is labelled
    assert redact(text) == text
    assert "[card number]" in redact_v1(text) and "[card number]" in redact_v2(text)


def test_v1_misses_spaced_cards():
    assert redact_v1("card 4111 1111 1111 1111") == "card 4111 1111 1111 1111"


def test_contacts_are_removed():
    out = redact("mail sam1@example.com or call (415) 555-0134")
    assert "[email]" in out and "[phone]" in out and "555" not in out


def _log(n=250, every=100):
    store, cps = MemoryStore(), WriteOnceCheckpoints()
    log = AuditLog(store, cps, every=every)
    for i in range(n):
        log.append({"case_id": f"C-{i}", "score": i / n})
    return store, cps


def test_audit_chain_verifies_and_locates_an_edit():
    store, cps = _log()
    assert verify(store.entries, cps) is None
    store.entries[137]["record"]["score"] = 0.999
    assert verify(store.entries, cps) == 137


def test_checkpoints_are_write_once():
    store, cps = _log()
    with pytest.raises(PermissionError):
        cps.put(100, "0" * 64)


def test_audit_log_resumes_from_store():
    store, cps = _log(n=50)
    log = AuditLog(store, cps, every=100)
    log.append({"case_id": "C-50"})
    assert verify(store.entries, cps) is None and store.count() == 51


def test_fairness_report_ratios():
    df = pd.DataFrame({"seg": ["a"] * 300 + ["b"] * 300,
                       "misuse": [True] * 30 + [False] * 270 + [True] * 30 + [False] * 270,
                       "flag": [True] * 20 + [False] * 10 + [True] * 10 + [False] * 260
                               + [True] * 20 + [False] * 10 + [True] * 20 + [False] * 250})
    rep = fairness_report(df, "seg", "a")
    assert rep.loc["b", "error_ratio"] == 2.0 and rep.loc["a", "flag_ratio"] == 1.0
    assert rep.enough_data.all()


def test_reason_codes_only_report_upward_factors():
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"days_to_file": rng.gamma(2, 10, 2000), "prior_disputes_12m": rng.poisson(0.3, 2000),
                      "amount": rng.lognormal(4, 1, 2000), "new_device": rng.integers(0, 2, 2000)})
    y = (X.days_to_file + 20 * X.prior_disputes_12m + rng.normal(0, 10, 2000)) > 45
    feats = list(X.columns)
    sc = StandardScaler().fit(X.to_numpy(float))
    m = LogisticRegression().fit(sc.transform(X.to_numpy(float)), y)
    row = pd.Series({"days_to_file": 58, "prior_disputes_12m": 1, "amount": 50.0, "new_device": 0})
    reasons = reason_codes(m, sc, feats, row)
    assert reasons[0]["feature"] == "days_to_file"
    assert all(r["contribution"] >= 0.10 for r in reasons)
    assert reasons[0]["text"] == "The claim was made 58 days after the purchase"


def test_model_card_has_every_section():
    import governance_demo
    card, missing = governance_demo.check_model_card()
    assert not missing and card["tier"] == 2
    assert card["decision_settings"] == {"contest_cost": 40, "review_margin": 5, "time_limit_days": 120}


def test_synthetic_misuse_is_equal_across_segments():
    import governance_demo
    df = governance_demo.make_claims()
    assert len(df) == 20_000
    rates = df.groupby("age_band").misuse.mean()
    assert rates.max() - rates.min() < 0.02
