from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
SCALE = 144


def load():
    return pd.read_csv(HERE / "disputes_sample.csv", parse_dates=["opened_at", "closed_at"])


def test_table_1_2_headline_figures():
    d = load()
    assert len(d) * SCALE == 720_000
    assert (d["family"] == "first_party").mean() == 0.38
    assert d["represented"].mean() == 0.31
    assert round(d.loc[d["represented"], "outcome"].eq("won").mean(), 2) == 0.42
    assert round(d["amount"].mean(), 2) == 186.00
    assert round(d["handling_cost"].mean(), 2) == 28.00
    assert round(d["net_loss"].sum() * SCALE / 1e6) == 61
    assert round(d["handling_cost"].sum() * SCALE / 1e6) == 20


def test_money_reconciles():
    d = load()
    assert ((d["net_loss"] + d["recovered"] <= d["amount"] + 0.005)).all()
    assert (d["closed_at"] > d["opened_at"]).all()
    assert set(d["outcome"]) == {"won", "lost", "accepted", "written_off", "denied"}
    assert set(d.loc[d["represented"], "outcome"]) == {"won", "lost"}


def test_generator_is_deterministic():
    import sys
    sys.path.insert(0, str(HERE))
    from make_data import build
    a, b = build(), build()
    pd.testing.assert_frame_equal(a, b)
