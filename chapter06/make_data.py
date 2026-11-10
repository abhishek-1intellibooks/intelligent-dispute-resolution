"""Extend the Chapter 1 dataset with card_id, merchant_id, reason and delivery_confirmed.

Reads  ../chapter01/disputes_sample.csv  (unchanged)
Writes chapter06/disputes_extended.csv   (same 5,000 rows, four extra columns)

The extension is seeded. It adds the structure Chapter 6 needs:

* most disputing cardholders raise one claim, a small group raises many
  (target: about 3% of disputing cardholders hold about 11% of disputes);
* the heavy group mixes three causes that look alike by count:
  first-party patterns (not-received claims, delivery proof held, many
  merchants, short gaps), third-party compromise bursts (unauthorized claims
  within days) and customers of one failing merchant (m0042, not-received,
  little proof);
* four planted cardholders reproduce the chapter's worked example (c1024) and
  the three rows of Table 6.5 (c741, c2677, c3578) as of 2026-09-30.

All data are synthetic. Run:  python make_data.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "chapter01" / "disputes_sample.csv"
OUT = HERE / "disputes_extended.csv"

SEED = 6
AS_OF = pd.Timestamp("2026-09-30 23:59:59")
N_MERCHANTS = 900
FAILING_MERCHANT = "m0042"

N_ABUSERS = 50          # first-party pattern cards
N_COMPROMISED = 48      # third-party compromise bursts
N_PAIRS = 300           # cards with two unrelated claims

# Planted cardholders: (card number, reasons, proof flags, gaps in whole days)
PLANTED = {
    741:  (["not_received"] * 5 + ["not_as_described"],
           [True, True, False, True, False, True], [4, 6, 9, 6, 5]),
    2677: (["not_received"] * 3, [True, False, False], [6, 7]),
    3578: (["not_received", "unrecognized"], [True, True], [57]),
    1024: (["not_received"] * 4, [True, True, False, True], [5, 8, 7]),   # worked example
}
# Last claim date of each planted card (inside the 90-day window ending AS_OF)
PLANTED_END = {741: "2026-09-27", 2677: "2026-09-22", 3578: "2026-09-18", 1024: "2026-09-25"}

REASONS_BY_FAMILY = {
    "unauthorized": (["unauthorized"], [1.0]),
    "defective": (["not_received", "not_as_described", "cancelled_recurring", "incorrect_amount"],
                  [0.40, 0.30, 0.20, 0.10]),
    "first_party": (["not_received", "unrecognized", "not_as_described", "cancelled_recurring"],
                    [0.45, 0.25, 0.15, 0.15]),
}
PROOF_RATE = {("first_party", "not_received"): 0.70, ("first_party", "not_as_described"): 0.60,
              ("defective", "not_received"): 0.25, ("defective", "not_as_described"): 0.40}


def build(seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    d = pd.read_csv(SOURCE, parse_dates=["opened_at", "closed_at"])
    n = len(d)
    fam = d["family"].to_numpy()
    t = d["opened_at"]

    # --- reason and delivery confirmation from the family ---------------------
    reason = np.empty(n, dtype=object)
    for f, (labels, p) in REASONS_BY_FAMILY.items():
        idx = np.flatnonzero(fam == f)
        reason[idx] = rng.choice(labels, len(idx), p=p)
    proof_p = np.array([PROOF_RATE.get((f, r), 0.0) for f, r in zip(fam, reason)])
    delivery = rng.random(n) < proof_p

    # --- merchants: long-tailed popularity -------------------------------------
    ranks = np.arange(1, N_MERCHANTS + 1)
    w = 1 / ranks ** 0.9
    merchant_ids = np.array([f"m{i:04d}" for i in ranks])
    rng.shuffle(merchant_ids)
    merchant_ids = merchant_ids[merchant_ids != FAILING_MERCHANT][: N_MERCHANTS - 1]
    w = w[: N_MERCHANTS - 1] / w[: N_MERCHANTS - 1].sum()
    merchant = rng.choice(merchant_ids, n, p=w)

    free = np.ones(n, dtype=bool)
    groups: list[list[int]] = []

    def take_near(target: pd.Timestamp, family: str | None, exact_days_from=None, gap=None):
        """Nearest free row at or after target (optionally with an exact whole-day gap)."""
        cand = free.copy()
        if family is not None:
            cand &= fam == family
        if exact_days_from is not None:
            cand &= ((t - exact_days_from).dt.days == gap).to_numpy()
        cand &= (t >= target).to_numpy() if exact_days_from is None else cand
        idx = np.flatnonzero(cand)
        if len(idx) == 0:
            return None
        return int(idx[np.argmin(np.abs((t.iloc[idx] - target).dt.total_seconds()))])

    # --- planted cardholders (exact gaps, first-party rows) --------------------
    planted_groups = {}
    for card, (reasons, proofs, gaps) in PLANTED.items():
        end = pd.Timestamp(PLANTED_END[card]) + pd.Timedelta(12, unit="h")
        start = end - pd.Timedelta(sum(gaps), unit="D") - pd.Timedelta(12, unit="h")
        for shift_h in range(0, 24 * 5, 3):        # slide the start until every gap fits
            first = take_near(start + pd.Timedelta(shift_h, unit="h"), "first_party")
            rows = [first]
            free[first] = False
            for g in gaps:
                r = take_near(t.iloc[rows[-1]] + pd.Timedelta(g, unit="D"), "first_party",
                              exact_days_from=t.iloc[rows[-1]], gap=g)
                if r is None:
                    break
                rows.append(r)
                free[r] = False
            if len(rows) == len(gaps) + 1:
                break
            free[rows] = True                       # release and retry
        else:
            raise RuntimeError(f"could not plant card c{card}")
        ms = rng.choice(merchant_ids[:300], len(rows), replace=False)
        for r, rs, pf, m in zip(rows, reasons, proofs, ms):
            reason[r], delivery[r], merchant[r] = rs, pf, m
        planted_groups[card] = rows

    # --- failing merchant: many customers, same problem, little proof ---------
    fm = np.flatnonzero(free & (fam == "defective") & (t >= "2026-06-01").to_numpy()
                        & (t < "2026-08-15").to_numpy())
    fm = rng.choice(fm, 45, replace=False)
    merchant[fm], reason[fm] = FAILING_MERCHANT, "not_received"
    delivery[fm] = rng.random(len(fm)) < 0.10
    # failing-merchant claims stay single-claim cards; leave them free for singles

    def cluster(family, k, mean_gap, n_days_span):
        t0 = t.min() + pd.Timedelta(float(rng.uniform(0, n_days_span)), unit="D")
        rows, cur = [], t0
        for _ in range(k):
            r = take_near(cur, family)
            if r is None:
                break
            assert r is not None, (card, g, t.iloc[rows[-1]])
            rows.append(r)
            free[r] = False
            cur = t.iloc[r] + pd.Timedelta(float(rng.exponential(mean_gap)) + 0.5, unit="D")
        return rows

    # --- first-party pattern cards -------------------------------------------
    for _ in range(N_ABUSERS):
        rows = cluster("first_party", int(rng.integers(4, 9)), 9.0, 330)
        for r in rows:
            if rng.random() < 0.8:
                reason[r] = "not_received"
            delivery[r] = reason[r] in ("not_received", "not_as_described") and rng.random() < 0.72
        groups.append(rows)

    # --- third-party compromise bursts ----------------------------------------
    for _ in range(N_COMPROMISED):
        groups.append(cluster("unauthorized", int(rng.integers(3, 6)), 1.2, 355))

    # --- remaining cards: pairs and singles ----------------------------------
    rest = np.flatnonzero(free)
    rng.shuffle(rest)
    rest = list(rest)
    pair_pool = [i for i in rest if merchant[i] != FAILING_MERCHANT]
    pairs = pair_pool[: 2 * N_PAIRS]
    for a, b in zip(pairs[0::2], pairs[1::2]):
        groups.append([a, b])
    paired = set(pairs)
    groups.extend([[i] for i in rest if i not in paired])

    # --- card numbers: planted ids fixed, others shuffled ---------------------
    n_cards = len(groups) + len(planted_groups)
    numbers = [k for k in range(1, n_cards + 1) if k not in PLANTED]
    numbers = list(rng.permutation(numbers))
    if max(PLANTED) > n_cards:     # keep planted numbers inside the id range
        numbers = numbers[: len(groups)]
    card = np.empty(n, dtype=object)
    for g, num in zip(groups, numbers):
        card[g] = f"c{num}"
    for num, rows in planted_groups.items():
        card[rows] = f"c{num}"
    assert all(c is not None for c in card)

    return d.assign(card_id=card, merchant_id=merchant, reason=reason,
                    delivery_confirmed=delivery)


def concentration(df: pd.DataFrame, top_share: float = 0.03) -> tuple[int, float]:
    counts = df["card_id"].value_counts()
    k = max(1, round(top_share * len(counts)))
    return k, counts.iloc[:k].sum() / counts.sum()


def main() -> None:
    df = build()
    df.to_csv(OUT, index=False, date_format="%Y-%m-%d %H:%M:%S")
    counts = df["card_id"].value_counts()
    k, share = concentration(df)
    print(f"wrote {OUT.name}: {len(df):,} rows, {len(counts):,} disputing cardholders, "
          f"{df['merchant_id'].nunique():,} merchants")
    print(f"  top 3% of cardholders ({k}) hold {share:.1%} of disputes")
    print(f"  cardholders with one claim: {(counts == 1).mean():.1%}")
    print(f"  reason mix: {df['reason'].value_counts(normalize=True).round(3).to_dict()}")
    print(f"  delivery confirmed on {df['delivery_confirmed'].mean():.1%} of claims")


if __name__ == "__main__":
    main()
