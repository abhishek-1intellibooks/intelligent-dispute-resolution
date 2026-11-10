import sys
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from card_state_machine import CLOCK_DAYS, TRANSITIONS, CardDispute  # noqa: E402
from lifecycle_economics import (annual_volumes, break_even_p,  # noqa: E402
                                 clock_days_from_catalogue, outcome_costs)


def run(events):
    case = CardDispute("t", 186.0)
    for e, on in events:
        case.apply(e, on)
    return case


def test_deflected_path():
    c = run([("inquiry_received", date(2026, 3, 2)), ("refund_issued", date(2026, 3, 4))])
    assert c.state == "DEFLECTED" and c.due is None


def test_contested_path_wins_inside_window():
    c = run([("chargeback_received", date(2026, 3, 20)), ("represent", date(2026, 4, 10)),
             ("issuer_accepts", date(2026, 4, 28))])
    assert c.state == "WON"
    assert [h[2] for h in c.history] == ["chargeback_received", "represent", "issuer_accepts"]


def test_missed_window_defaults_to_loss_and_is_recorded():
    c = run([("chargeback_received", date(2026, 3, 20)), ("represent", date(2026, 4, 25))])
    assert c.state == "LOST"
    assert c.history[-1] == (date(2026, 4, 25), "CHARGEBACK", "window_missed", "LOST")


def test_last_day_of_window_is_still_open():
    c = run([("chargeback_received", date(2026, 3, 20)), ("represent", date(2026, 4, 19))])
    assert c.state == "REPRESENTED"


def test_illegal_event_rejected():
    with pytest.raises(ValueError, match="'represent' is not allowed in SETTLED"):
        CardDispute("bad", 186.0).apply("represent", date(2026, 3, 2))


def test_no_refund_after_chargeback():
    c = run([("chargeback_received", date(2026, 3, 20))])
    with pytest.raises(ValueError):
        c.apply("refund_issued", date(2026, 3, 21))
    assert ("CHARGEBACK", "refund_issued") not in TRANSITIONS


def test_arbitration_path_and_clock():
    c = run([("chargeback_received", date(2026, 3, 1)), ("represent", date(2026, 3, 10)),
             ("issuer_escalates", date(2026, 3, 20))])
    assert c.state == "PRE_ARBITRATION"
    assert c.due == date(2026, 4, 19)
    c.apply("contest", date(2026, 4, 1)).apply("ruling_merchant", date(2026, 6, 1))
    assert c.state == "WON"


def test_break_even_and_outcome_costs():
    assert round(break_even_p(), 3) == 0.209
    assert outcome_costs()["Cost to the merchant"].tolist() == [191, 206, 28, 234]


def test_annual_volumes_from_chapter01():
    v = annual_volumes()
    assert (v["cases"], v["contested"], v["won"], v["lost"]) == (720_000, 223_200, 93_744, 129_456)


def test_catalogue_exercise_is_a_stub():
    assert CLOCK_DAYS == {"CHARGEBACK": 30, "PRE_ARBITRATION": 30}
    with pytest.raises(NotImplementedError):
        clock_days_from_catalogue()
