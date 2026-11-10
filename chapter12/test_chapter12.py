"""Tests for the context pack, retrieval, slotting and the checker.

Run: python -m pytest -q
"""
from datetime import date

import pytest

from context import context_pack, redact
from draft import render
from guardrails import check
from normalize import dates, units
from records import worked_case
from rules import search_rules


@pytest.fixture(scope="module")
def items():
    return context_pack(*worked_case())


def test_redact_removes_contact_details_and_card_numbers():
    text = redact("Card 4111111111111111, mail me@example.com or call +1 555 201 7734.")
    assert "4111" not in text and "@" not in text and "7734" not in text


def test_pack_holds_the_worked_example_facts(items):
    assert items["F5"][1] == "41 Harlow Street, unit 12, 44107"
    assert items["C3"][1] == "day 9 of 45"
    assert "[phone]" in items["N1"][1]
    assert "R-A-NR1-E2025-2" in items


def test_retrieval_respects_the_edition_in_force():
    old = search_rules("proof of delivery tracking", reason="not_received",
                       network="Network A", on=date(2025, 9, 1), k=1)[0]
    new = search_rules("proof of delivery tracking", reason="not_received",
                       network="Network A", on=date(2025, 12, 1), k=1)[0]
    assert old.edition == "2024.2" and new.edition == "2025.2"


def test_render_refuses_an_invented_placeholder(items):
    assert render("Delivered on {{F6}}.", items) == "Delivered on 28 November 2025 at 14:12."
    with pytest.raises(KeyError):
        render("Delivered on {{F12}}.", items)


def test_prose_and_iso_dates_are_the_same_value():
    assert "2025-11-28" in dates("28 November 2025") & dates("2025-11-28")
    assert any(d.startswith("unverifiable") for d in dates("the 28th of November 2025"))
    assert units("41 Harlow Street, unit 12, 44107") == {"street:41", "unit:12", "zip:44107"}


SENTENCES = [
    "The order was placed on 22 November 2025 [F1].",
    "It was shipped to 41 Harlow Street, unit 12, 44107 [F3].",
    "The carrier records delivery to 41 Harlow Street, unit 12, 44107 on 28 November 2025 [F5][F6].",
]


def test_clean_sentences_pass(items):
    assert check(SENTENCES, items) == []


@pytest.mark.parametrize("sentence, flag", [
    ("The parcel was delivered [F12].", "bad_citation"),
    ("The parcel was delivered.", "no_citation"),
    ("It was delivered on 27 November 2025 [F6].", "unsupported_value"),
    ("It was delivered on the 28th of November 2025 [F6].", "unsupported_value"),
    ("It was delivered to unit 21 [F5].", "unsupported_value"),
    ("The parcel was left with a neighbour [F5].", "unsupported_claim"),
    ("The customer received the parcel [F5].", "tone"),
    ("Call the customer on +1 555 201 7734 [N1].", "privacy"),
])
def test_each_check_fires(items, sentence, flag):
    assert flag in {kind for kind, _ in check(SENTENCES + [sentence], items)}


def test_missing_required_fact(items):
    flags = check(SENTENCES[:2], items)
    assert ("missing_required", "F6") in flags


def test_word_level_wrong_fact_is_not_caught(items):
    """The checker's known blind spot (Table 12.7): words rather than values."""
    assert check(SENTENCES + ["Proof of delivery is a signature on delivery [F7]."], items) == []
