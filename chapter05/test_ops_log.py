"""Sanity checks on the synthetic operations log."""

from pathlib import Path

import pandas as pd

import make_ops_log

HERE = Path(__file__).resolve().parent
TIMES = ["claim_received_at", "case_created_at", "first_touch_at", "decision_at", "closed_at"]


def test_log_shape_and_order():
    log = pd.read_csv(HERE / "ops_log.csv", parse_dates=TIMES)
    assert len(log) == 5_000
    assert set(log["channel"]) == {"app", "web", "phone", "branch"}
    for a, b in zip(TIMES, TIMES[1:]):
        assert (log[b] >= log[a]).all(), (a, b)
    # analysts touch, decide and close on weekdays only
    for col in TIMES[2:]:
        assert (log[col].dt.weekday < 5).all()


def test_generator_is_deterministic():
    a = make_ops_log.make_log()
    b = make_ops_log.make_log()
    pd.testing.assert_frame_equal(a, b)
