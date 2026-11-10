"""Generate chapter01/disputes_sample.csv: 5,000 synthetic card disputes.

The sample is one year of disputes at a representative mid-sized US issuer
(about 4 million active cards), scaled down by a factor of 144 so that
5,000 sample cases correspond to 720,000 cases a year (Table 1.2).

All data are synthetic and all amounts illustrative. The generator is seeded
and calibrated so that the sample reproduces the headline figures of Table 1.2
exactly:

    first-party share 38%, contested share 31%, win rate on contested 42%,
    average amount $186, average handling cost $28,
    net unrecovered loss $61 million a year (after scaling by 144).

Run:  python make_data.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "disputes_sample.csv"

SEED = 20260101
N_CASES = 5_000
SCALE = 144                      # 5,000 sample cases x 144 = 720,000 per year
TARGET_AVG_AMOUNT = 186.00
TARGET_AVG_HANDLING = 28.00
TARGET_NET_LOSS_ANNUAL = 61_000_000

FAMILY_COUNTS = {"first_party": 1_900, "unauthorized": 1_550, "defective": 1_550}
N_REPRESENTED = 1_550            # 31% of cases contested through representment
N_WON = 651                      # 42% of contested cases won

START = pd.Timestamp("2025-10-01")
END = pd.Timestamp("2026-10-01")  # exclusive: one year of opened cases


def _rescale_to_mean(x: np.ndarray, target: float) -> np.ndarray:
    """Round to cents and nudge so that the mean is exactly `target`."""
    x = np.round(x * target / x.mean(), 2)
    diff = round(target * len(x) - x.sum(), 2)
    x[np.argmax(x)] += diff          # absorb rounding residue in the largest value
    return np.round(x, 2)


def build(seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # --- family, product, network -------------------------------------------
    family = np.concatenate([[f] * n for f, n in FAMILY_COUNTS.items()])
    rng.shuffle(family)
    product = rng.choice(["credit_card", "debit_card"], N_CASES, p=[0.55, 0.45])
    network = rng.choice(["visa", "mastercard"], N_CASES, p=[0.6, 0.4])

    # --- opened_at: uniform over the year, business-hours weighted -----------
    span_s = int((END - START).total_seconds())
    secs = np.sort(rng.integers(0, span_s, N_CASES))
    opened_at = START + pd.to_timedelta(secs, unit="s")

    # --- amount: right-skewed; unauthorized claims slightly larger -----------
    fam_mult = pd.Series(family).map(
        {"unauthorized": 1.25, "defective": 0.95, "first_party": 0.85}).to_numpy()
    raw = rng.lognormal(mean=4.75, sigma=0.85, size=N_CASES) * fam_mult
    amount = _rescale_to_mean(raw, TARGET_AVG_AMOUNT)

    # --- represented: exactly 1,550, weighted toward first-party claims ------
    w_rep = pd.Series(family).map(
        {"first_party": 0.45, "defective": 0.33, "unauthorized": 0.22}).to_numpy()
    rep_idx = rng.choice(N_CASES, N_REPRESENTED, replace=False, p=w_rep / w_rep.sum())
    represented = np.zeros(N_CASES, dtype=bool)
    represented[rep_idx] = True

    # --- representment outcome: exactly 651 won ------------------------------
    w_won = pd.Series(family[rep_idx]).map(
        {"first_party": 0.55, "defective": 0.35, "unauthorized": 0.25}).to_numpy()
    won_idx = rng.choice(rep_idx, N_WON, replace=False, p=w_won / w_won.sum())
    outcome = np.array([""] * N_CASES, dtype=object)
    outcome[rep_idx] = "lost"
    outcome[won_idx] = "won"

    # --- outcomes of uncontested cases, calibrated to the net-loss target ----
    # net_loss: "won" (representment succeeded, issuer keeps the credit it gave)
    #           and "written_off" (issuer absorbs: no chargeback right, below
    #           threshold or goodwill) carry the full amount; "accepted" (merchant
    #           accepted the chargeback), "lost" (representment failed) and
    #           "denied" (claim denied, cardholder re-billed) carry none.
    target_sample_loss = TARGET_NET_LOSS_ANNUAL / SCALE
    loss_so_far = amount[outcome == "won"].sum()
    remaining = target_sample_loss - loss_so_far
    open_idx = np.flatnonzero(~represented)
    w_wo = pd.Series(family[open_idx]).map(
        {"unauthorized": 0.50, "first_party": 0.30, "defective": 0.20}).to_numpy()
    order = rng.choice(open_idx, len(open_idx), replace=False, p=w_wo / w_wo.sum())
    acc = 0.0
    written = []
    for i in order:
        if acc + amount[i] > remaining:
            continue
        written.append(i)
        acc += amount[i]
        if remaining - acc < 1.0:
            break
    outcome[written] = "written_off"
    rest = np.array([i for i in open_idx if outcome[i] == ""])
    denied = rng.random(len(rest)) < np.where(family[rest] == "first_party", 0.35, 0.15)
    outcome[rest[denied]] = "denied"
    outcome[rest[~denied]] = "accepted"

    net_loss = np.where(np.isin(outcome, ["won", "written_off"]), amount, 0.0)
    recovered = np.where(np.isin(outcome, ["accepted", "lost"]), amount, 0.0)

    # --- handling cost: depends on path, averaged to exactly $28 -------------
    base = pd.Series(outcome).map({"written_off": 14, "denied": 22, "accepted": 20,
                                   "won": 48, "lost": 52}).to_numpy(dtype=float)
    handling = _rescale_to_mean(base * rng.gamma(9.0, 1 / 9.0, N_CASES),
                                TARGET_AVG_HANDLING)

    # --- closed_at: cycle time by path ----------------------------------------
    lo_hi = {"written_off": (2, 15), "denied": (8, 40), "accepted": (15, 50),
             "won": (45, 110), "lost": (45, 120)}
    days = np.array([rng.uniform(*lo_hi[o]) for o in outcome])
    closed_at = opened_at + pd.to_timedelta(np.round(days * 86_400), unit="s")

    df = pd.DataFrame({
        "case_id": [f"D{i:05d}" for i in range(1, N_CASES + 1)],
        "opened_at": opened_at,
        "closed_at": closed_at,
        "product": product,
        "network": network,
        "family": family,
        "amount": amount,
        "represented": represented,
        "outcome": outcome,
        "recovered": np.round(recovered, 2),
        "net_loss": np.round(net_loss, 2),
        "handling_cost": handling,
    })
    return df


def main() -> None:
    df = build()
    df.to_csv(OUT, index=False, date_format="%Y-%m-%d %H:%M:%S")
    rep = df["represented"]
    print(f"wrote {OUT.name}: {len(df):,} rows")
    print(f"  first-party share   {(df['family'] == 'first_party').mean():.1%}")
    print(f"  contested share     {rep.mean():.1%}")
    print(f"  win rate contested  {df.loc[rep, 'outcome'].eq('won').mean():.1%}")
    print(f"  average amount      ${df['amount'].mean():,.2f}")
    print(f"  average handling    ${df['handling_cost'].mean():,.2f}")
    print(f"  annual net loss     ${df['net_loss'].sum() * SCALE / 1e6:,.1f}M")
    print(f"  annual operating    ${df['handling_cost'].sum() * SCALE / 1e6:,.1f}M")


if __name__ == "__main__":
    main()
