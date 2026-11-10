import sys
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from clocks import add_time, deadlines, load_rules, stale_rules  # noqa: E402

EVENTS = {"notice_received": date(2026, 1, 5), "processing_date": date(2025, 12, 20)}


def test_credit_card_matches_chapter():
    assert deadlines("credit_card", EVENTS) == [
        ("reg_z_acknowledge", "12 CFR 1026.13(c)(1)", date(2026, 2, 4)),
        ("reg_z_resolve", "12 CFR 1026.13(c)(2)", date(2026, 4, 5)),
        ("visa_13_1_filing", "Visa Core Rules, 11.10.2", date(2026, 4, 19)),
    ]


def test_debit_card_matches_chapter():
    assert deadlines("debit_card", EVENTS) == [
        ("reg_e_determine", "12 CFR 1005.11(c)(1)", date(2026, 1, 20)),
        ("reg_e_extended", "12 CFR 1005.11(c)(2)", date(2026, 2, 19)),
        ("visa_13_1_filing", "Visa Core Rules, 11.10.2", date(2026, 4, 19)),
    ]


def test_mlk_day_is_not_a_business_day():
    # 10 business days from Mon 5 Jan 2026 skip Mon 19 Jan (MLK Day)
    assert add_time(date(2026, 1, 5), 10, "business_days") == date(2026, 1, 20)
    assert add_time(date(2026, 1, 5), 10, "calendar_days") == date(2026, 1, 15)


def test_missing_start_event_is_skipped_not_guessed():
    ids = [r for r, _, _ in deadlines("debit_card", {"processing_date": date(2025, 12, 20)})]
    assert ids == ["visa_13_1_filing"]


def test_pos_flag_swaps_extended_period():
    ids = {r: d for r, _, d in deadlines("debit_card", EVENTS, flags={"pos_or_foreign"})}
    assert "reg_e_extended" not in ids
    assert ids["reg_e_extended_90"] == date(2026, 4, 5)


def test_new_account_flag_uses_20_business_days():
    ids = {r: d for r, _, d in deadlines("debit_card", EVENTS, flags={"new_account"})}
    assert "reg_e_determine" not in ids
    assert ids["reg_e_determine_new_account"] == date(2026, 2, 3)


@pytest.mark.parametrize("rule", load_rules(), ids=lambda r: r["id"])
def test_every_entry_carries_source_edition_and_verification(rule):
    for key in ("id", "layer", "source", "edition", "applies_to", "starts_on",
                "amount", "unit", "consequence", "effective_from", "last_verified"):
        assert key in rule, key
    assert rule["layer"] in {"law", "network", "policy"}
    assert rule["unit"] in {"business_days", "calendar_days"}
    date.fromisoformat(rule["last_verified"])
    date.fromisoformat(rule["effective_from"])


def test_rule_ids_unique():
    ids = [r["id"] for r in load_rules()]
    assert len(ids) == len(set(ids))


def test_stale_rules_flags_old_entries():
    assert stale_rules(date(2026, 10, 31)) == []
    assert len(stale_rules(date(2027, 10, 31))) == len(load_rules())
