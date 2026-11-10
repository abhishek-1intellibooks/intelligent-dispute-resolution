import sys
from datetime import datetime as dt
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rail_adapters.base import RailCase  # noqa: E402
from rail_adapters.profiles import ACH_DEBIT, INSTANT, WIRE, p2p_profile  # noqa: E402
from recovery_curve import recoverable_share  # noqa: E402

SETTLED, REPORTED = dt(2026, 3, 9, 10), dt(2026, 3, 9, 14)


def test_ach_due_counts_from_settlement():
    case = RailCase("a", ACH_DEBIT, 420.0, dt(2026, 2, 2), dt(2026, 3, 20, 9))
    assert case.due == dt(2026, 4, 3)
    case.apply("return_sent", dt(2026, 3, 23, 11))
    assert case.state == "RETURNED" and case.history[-1][4] == "on_time"


def test_instant_clock_counts_from_entry():
    case = RailCase("r", INSTANT, 64000.0, SETTLED, REPORTED)
    assert case.due == dt(2026, 3, 9, 14, 30)
    case.apply("recall_sent", dt(2026, 3, 9, 14, 20))
    assert case.due == dt(2026, 3, 10, 14, 20)


def test_late_recall_is_recorded_not_blocked():
    case = RailCase("w", WIRE, 64000.0, SETTLED, REPORTED)
    case.apply("recall_sent", dt(2026, 3, 10, 9))
    case.apply("request_refused", dt(2026, 3, 11, 12))
    assert case.state == "LOSS_REVIEW"
    assert [h[4] for h in case.history] == ["late", "on_time"]


def test_card_event_rejected_on_push_rail():
    case = RailCase("p", INSTANT, 64000.0, SETTLED, REPORTED)
    with pytest.raises(ValueError, match="not allowed in REPORTED on rail 'instant'"):
        case.apply("chargeback_received", dt(2026, 3, 9, 15))


def test_missing_evidence():
    case = RailCase("p", INSTANT, 64000.0, SETTLED, REPORTED)
    record = {"end_to_end_id": "E2E-77", "receiving_bank": "RB-021"}
    assert case.missing_evidence(record) == ["beneficiary_account", "payer_statement"]


def test_profiles_are_frozen():
    with pytest.raises(Exception):
        INSTANT.name = "other"


def test_p2p_is_an_exercise():
    with pytest.raises(NotImplementedError):
        p2p_profile()


def test_recovery_curve_matches_chapter():
    assert round(recoverable_share(1), 2) == 0.89
    assert round(recoverable_share(24), 2) == 0.06
    assert round(64000 * recoverable_share(4), -2) == 40300
