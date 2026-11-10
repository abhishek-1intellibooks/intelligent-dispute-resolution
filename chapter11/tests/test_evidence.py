"""Unit tests for the normalizers, matching, scoring and the fallback chain.

Run from chapter11/:  python -m pytest -q
Test the normalizers on clean data before measuring anything on noisy data.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evidence_pipeline import Case, build_evidence, choose  # noqa: E402
from extract import (Fact, normalize_address, read_amount, read_attestation,  # noqa: E402
                     read_date, repair_date_digits)
from match import address_match, fuzz, on_time  # noqa: E402
from requirements import RULE_SETS, rules_for  # noqa: E402
from sufficiency import sufficiency  # noqa: E402

CASE = Case("T1", "not_received", date(2025, 12, 8), date(2025, 12, 8),
            date(2025, 11, 29), 24900, "USD")


def test_same_address_in_three_styles():
    styles = ["41 Harlow Street, Apt 12, Cleveland, OH 44107",
              "41 HARLOW ST #12, CLEVELAND, OH 44107",
              "41 Harlow St, Unit 12, Cleveland, OH 44107"]
    parsed = [normalize_address(s) for s in styles]
    assert all(p == {"number": "41", "street": "HARLOW ST", "unit": "12",
                     "zip": "44107"} for p in parsed)


@pytest.mark.parametrize("street", ["Sterling Lane", "Unity Road", "Aptos Drive",
                                    "Stewart Avenue"])
def test_unit_words_inside_street_names_are_not_units(street):
    a = normalize_address(f"7 {street}, Cleveland, OH 44107")
    assert a["unit"] == "" and a["street"].split()[0] == street.split()[0].upper()


def test_amounts_in_cents_with_ocr_repair():
    assert read_amount("Total: $249.00") == 24900
    assert read_amount("$1,2S9.O0") == 125900
    assert read_amount("249,00 USD") is None


def test_dates_keep_month_names_and_parse_by_source():
    assert repair_date_digits("Oct 3, 2O25") == "Oct 3, 2025"
    assert read_date("Oct 3, 2025", "mon") == "2025-10-03"
    assert read_date("1l/28/2025 14:12", "us") == "2025-11-28"
    assert read_date("03/04/2025", "us") == "2025-03-04"
    assert read_date("2025-11-28T14:12", "iso") == "2025-11-28"


def test_not_required_is_not_a_signature():
    assert read_attestation("Signed by J. OKAFOR") == "signed"
    assert read_attestation("Signature not required") == "none"
    assert read_attestation("Not required") == "none"
    assert read_attestation("Photo on file") == "photo"


def test_address_verdicts():
    given = normalize_address("41 Harlow Street, Apt 12, Cleveland, OH 44107")
    assert address_match(normalize_address("41 HARLOW ST #12, CLEVELAND, OH 44107"),
                         given)[1] == "match"
    assert address_match(normalize_address("41 HARLOW ST #2, CLEVELAND, OH 44107"),
                         given)[1] == "unit_differs"
    assert address_match(normalize_address("14 HARLOW ST #12, CLEVELAND, OH 44107"),
                         given)[1] == "no_match"
    assert address_match(None, given) == (0.0, "missing")


def test_fuzz_ratio():
    assert fuzz.ratio("HARLOW ST", "HARLOW ST") == 100
    assert fuzz.ratio("HARLOW ST", "HARL0W ST") == pytest.approx(100 * 16 / 18)


def test_on_time_with_grace_and_claim():
    assert on_time(date(2025, 12, 2), date(2025, 11, 29), date(2025, 12, 8))
    assert not on_time(date(2025, 12, 3), date(2025, 11, 29), date(2025, 12, 8))
    assert not on_time("2025-12-01", "2025-11-29", "2025-12-01")


def facts(unit="12", channel="screenshot", attested="photo", amount=24900):
    return {"ship_to": normalize_address("41 Harlow Street, Apt 12, Cleveland, OH 44107"),
            "delivered_to": normalize_address(f"41 HARLOW ST #{unit}, CLEVELAND, OH 44107"),
            "delivered_to_channel": channel, "amount": amount,
            "delivered_on": "2025-11-29", "attested": attested}


def test_question_one_scores():
    assert sufficiency(facts(unit="2"), CASE)[::2] == (0.5, "borderline")
    assert sufficiency(facts(), CASE)[::2] == (0.85, "sufficient")
    assert sufficiency(facts(channel="api", attested="signed"), CASE)[0] == 1.0


def test_contradiction_vetoes_the_score():
    f = facts(channel="api", attested="signed")
    f["delivered_to"] = normalize_address("900 OAK AVE, CLEVELAND, OH 44101")
    score, gaps, verdict = sufficiency(f, CASE)
    assert score == 0.2 and verdict == "insufficient"
    assert "delivery address does not match" in gaps


def test_no_delivery_confirmation():
    assert sufficiency({"amount": 24900}, CASE) == (0.0, ["no delivery confirmation"],
                                                     "insufficient")


def test_rules_in_force_when_opened():
    assert rules_for("not_received", date(2025, 3, 1), RULE_SETS)["version"] == "nr-2024.1"
    assert rules_for("not_received", date(2025, 4, 1), RULE_SETS)["version"] == "nr-2025.2"


def test_fallback_chain_prefers_trusted_confident_readings():
    photo = Fact("delivered_to", {"unit": "2"}, 0.58, "D3", 1, "photo")
    scan = Fact("delivered_to", {"unit": "12"}, 0.91, "D4", 1, "clean_scan")
    api = Fact("delivered_to", {"unit": "12"}, 1.0, "D5", 1, "api")
    assert choose([photo, scan, api])[0] is api
    assert choose([photo, scan])[0] is scan
    assert choose([photo]) == (None, "review")


def test_review_callback_is_used_below_the_gate():
    ship = normalize_address("41 Harlow Street, Apt 12, Cleveland, OH 44107")
    readings = {"ship_to": [Fact("ship_to", ship, 1.0, "D1", 1, "native")],
                "delivered_to": [Fact("delivered_to", ship, 0.4, "D3", 1, "photo")]}
    asked = []

    def review(case, name, rs):
        asked.append(name)
        return Fact(name, ship, 1.0, "D3", 1, "photo", extractor="person")

    rec = build_evidence(CASE, readings, review)
    assert asked == ["delivered_to"]
    assert rec["rules"] == "nr-2025.2" and rec["pipeline"] == "evidence-1.0"
    assert [t["how"] for t in rec["facts"]] == ["auto", "review"]
