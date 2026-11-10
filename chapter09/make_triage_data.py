"""Generate claims_closed.csv: a synthetic year (2025) of 24,000 closed card claims.

Each row holds the fields known at intake (Table 9.3), the queue depth the
router reported when the case was created, and the outcomes recorded at
closure: first touch, effort in business days, decision day, the family at
closure and whether the ten-business-day clock was breached.

How it is built:
  * a latent family is drawn (38% first-party, 34% unauthorized, 28% defective)
    and the intake fields and narrative are drawn given the family;
  * effort follows Table 9.8 (family x delivery record missing x review flag);
  * the year is run through queue_sim.py first in, first out, as it historically
    was, which sets first_touch_on, decided_on, queue_depth and breached;
  * finally the recorded family label is reassigned at random for one claim in
    twenty, to reflect analyst disagreement.
All data are synthetic.
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import queue_sim as qs

warnings.filterwarnings("ignore", category=DeprecationWarning)   # numpy 2 / pandas timedelta notice
HERE = Path(__file__).resolve().parent
rng = np.random.default_rng(9)

PERIODS = [("2025-01-01", "2025-08-31", 15731),     # training months
           ("2025-09-01", "2025-10-31", 3961),      # validation months
           ("2025-11-01", "2025-12-31", 4308)]      # test months (holiday surge)
WARMUP = ("2024-11-15", "2024-12-31", 3000)         # simulated only, to fill the queue
COOLDOWN = ("2026-01-01", "2026-01-31", 2000)       # simulated only, so the queue does not run dry
FAMILIES = ["unauthorized", "defective", "first_party"]
FAMILY_P = [0.335, 0.275, 0.39]
LABEL_NOISE = 0.05

# ----------------------------------------------------------------- intake fields given family
REASONS = ["fraud", "not_recognized", "not_received", "defective", "cancelled", "other"]
MCC = ["electronics", "retail", "travel", "digital", "food", "subscription", "other"]
MCC_P = {
    "unauthorized": [0.24, 0.20, 0.14, 0.18, 0.08, 0.06, 0.10],
    "defective":    [0.22, 0.32, 0.08, 0.08, 0.06, 0.14, 0.10],
    "first_party":  [0.26, 0.28, 0.06, 0.14, 0.10, 0.08, 0.08],
}
FLAGS_P = {  # card_present, three_ds, device_known, recurring, security_alert_7d
    "unauthorized": [0.12, 0.25, 0.28, 0.05, 0.16],
    "defective":    [0.18, 0.45, 0.72, 0.16, 0.02],
    "first_party":  [0.12, 0.74, 0.92, 0.08, 0.03],
}
DELIVERY = ["confirmed", "not_found", "no_link"]
DELIVERY_P = {
    "unauthorized": [0.35, 0.10, 0.55],
    "defective":    [0.40, 0.25, 0.35],
    "first_party":  [0.76, 0.08, 0.16],
}
REVIEW_P = 0.10
PRIOR_RATE = {"unauthorized": 0.25, "defective": 0.30, "first_party": 1.0}
DAYS_MEAN = {"unauthorized": 12, "defective": 24, "first_party": 28}
AMOUNT_MU = {"unauthorized": 5.0, "defective": 4.6, "first_party": 4.7}

# ----------------------------------------------------------------- narratives
PHRASES = {
    # phrase: (weight for unauthorized, defective, first_party), menu reason it suggests
    "I did not make this purchase": ((8, 0, 2.5), "fraud"),
    "someone used my card without permission": ((6, 0, 0.5), "fraud"),
    "my card was stolen": ((4, 0, 0.3), "fraud"),
    "I lost my card last week": ((3, 0, 0.3), "fraud"),
    "I never shared my card details with anyone": ((4, 0, 0.3), "fraud"),
    "I got a text about a login I did not make": ((4, 0, 0), "fraud"),
    "my card is still in my wallet": ((4, 0, 0.5), "fraud"),
    "there are several charges I do not recognise": ((5, 0, 0.5), "not_recognized"),
    "I have never heard of this merchant": ((4, 0, 1), "not_recognized"),
    "I do not recognise the name on my statement": ((4, 3, 2.5), "not_recognized"),
    "I do not recognise this charge": ((5, 2, 3), "not_recognized"),
    "I did not authorise this payment": ((5, 1, 2), "fraud"),
    "the item arrived broken": ((0, 6, 0.3), "defective"),
    "the product stopped working after two days": ((0, 5, 0.3), "defective"),
    "it was not as described": ((0, 6, 0.8), "defective"),
    "I returned the item but have no refund": ((0, 6, 1), "cancelled"),
    "I cancelled the order and was still charged": ((0.2, 5, 0.8), "cancelled"),
    "the merchant will not respond": ((0, 6, 1.5), "not_received"),
    "the merchant refused a refund": ((0, 5, 0.8), "cancelled"),
    "they sent the wrong size": ((0, 4, 0.3), "defective"),
    "the seller sent a fake item": ((0, 3, 0.2), "defective"),
    "I was charged twice for one order": ((0.5, 4, 0.3), "other"),
    "the order never arrived": ((0, 6, 5), "not_received"),
    "I did not receive the item": ((0, 2.5, 5), "not_received"),
    "the package was never delivered": ((0, 2, 5), "not_received"),
    "nothing arrived at my address": ((0, 1, 5), "not_received"),
    "I want my money back": ((0.3, 1, 6), "other"),
    "please refund this charge now": ((0.3, 0.8, 5), "other"),
    "I do not remember making this purchase": ((0.8, 0, 5), "not_recognized"),
    "the tracking says delivered but I have nothing": ((0, 0.8, 5), "not_received"),
    "my family member may have used it": ((0.3, 0, 3), "fraud"),
    "I think the delivery driver kept it": ((0, 0.5, 3), "not_received"),
}
FILLER = ["Please help.", "This is urgent.", "I have called twice already.",
          "I am very upset about this.", "Please sort this out.", ""]
PHRASE_LIST = list(PHRASES)
PHRASE_W = np.array([PHRASES[p][0] for p in PHRASE_LIST], dtype=float)
REASON_OTHER, REASON_RANDOM = 0.13, 0.10   # menu: "Other", or a choice unrelated to the text

# ----------------------------------------------------------------- effort (Table 9.8)
EFFORT = {  # (contact needed, flagged for review) -> mean business days
    "defective":    {(False, False): 1.5, (False, True): 3.5, (True, False): 4.5, (True, True): 6.5},
    "first_party":  {(False, False): 2.5, (False, True): 4.5, (True, False): 2.5, (True, True): 4.4},
    "unauthorized": {(False, False): 2.5, (False, True): 4.5, (True, False): 2.5, (True, True): 4.5},
}
ASSEMBLY_DELAY_P = 0.12     # share of cases created hours or days after the claim
EXTRA_DELAY = 0.45          # mean of unpredictable extra days (waiting on merchants, customers)
MAX_WORK = 9


def arrivals(start, end, n):
    days = pd.date_range(start, end, freq="D")
    w = np.where(days.dayofweek >= 5, 0.6, 1.0)
    w *= np.where((days.month == 12) & (days.day.isin(range(1, 24))), 1.08, 1.0)  # holiday shopping
    counts = rng.multinomial(n, w / w.sum())
    day = np.repeat(days.to_numpy(), counts)
    hour_w = np.array([1, 2, 4, 6, 7, 8, 8, 8, 8, 8, 8, 7, 6, 6, 5, 4, 3, 2], float)
    hour = rng.choice(np.arange(6, 24), size=n, p=hour_w / hour_w.sum())
    minute = rng.integers(0, 60, n)
    return pd.to_datetime(day) + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m")


def narrative(fam_idx):
    """The customer's words, and the menu reason they then pick."""
    k = rng.choice([1, 2, 3], p=[0.10, 0.50, 0.40])
    p = PHRASE_W[:, fam_idx] / PHRASE_W[:, fam_idx].sum()
    picks = rng.choice(len(PHRASE_LIST), size=k, replace=False, p=p)
    text = ", and ".join(PHRASE_LIST[i] for i in picks)
    text = text[0].upper() + text[1:] + "."
    filler = rng.choice(FILLER)
    u = rng.random()
    reason = ("other" if u < REASON_OTHER else rng.choice(REASONS[:5]) if u < REASON_OTHER + REASON_RANDOM
              else PHRASES[PHRASE_LIST[picks[0]]][1])
    return f"{text} {filler}".strip(), reason


def make_claims(received):
    n = len(received)
    fam = rng.choice(3, size=n, p=FAMILY_P)
    rows = []
    for f_idx in fam:
        f = FAMILIES[f_idx]
        flags = rng.random(5) < FLAGS_P[f]
        delivery = rng.choice(DELIVERY, p=DELIVERY_P[f])
        review = rng.random() < REVIEW_P
        text, reason = narrative(f_idx)
        completeness = 3 if delivery != "no_link" else 2
        if review and rng.random() < 0.4:
            completeness, delivery = int(rng.choice([0, 1])), "no_link"
        rows.append(dict(
            channel=rng.choice(["app", "web", "phone", "branch"], p=[0.46, 0.22, 0.27, 0.05]),
            product=rng.choice(["debit", "credit"], p=[0.55, 0.45]),
            amount=float(np.round(np.clip(np.exp(rng.normal(AMOUNT_MU[f], 0.9)), 5, 9000), 2)),
            intake_reason=reason,
            narrative=text,
            mcc_group=rng.choice(MCC, p=MCC_P[f]),
            card_present=bool(flags[0]), three_ds=bool(flags[1] and not flags[0]),
            device_known=bool(flags[2]), recurring=bool(flags[3]), security_alert_7d=bool(flags[4]),
            days_since_txn=int(min(rng.exponential(DAYS_MEAN[f]) + 1, 120)),
            tenure_months=int(rng.gamma(2.0, 30 if f != "first_party" else 22)) + 1,
            prior_disputes_12m=int(rng.poisson(PRIOR_RATE[f])),
            delivery_status=delivery, link_completeness=completeness, needs_review=bool(review),
            true_family=f))
    df = pd.DataFrame(rows)
    contact = df.delivery_status.isin(["not_found", "no_link"])
    mean = [EFFORT[f][(c, r)] for f, c, r in zip(df.true_family, contact, df.needs_review)]
    base = np.asarray(mean) - EXTRA_DELAY
    whole = np.floor(base)
    work = whole + (rng.random(n) < base - whole) + rng.poisson(EXTRA_DELAY, n)
    df["work_days"] = np.clip(work, 1, MAX_WORK).astype(int)
    df.insert(0, "claim_received_at", received)
    # most cases are assembled within minutes; some wait for a manual step or a late feed
    lag = np.where(rng.random(n) < ASSEMBLY_DELAY_P, rng.uniform(240, 3000, n), rng.integers(1, 30, n))
    df.insert(1, "case_created_at", (received + pd.to_timedelta(lag.round(), unit="m")))
    return df


def main():
    warm = make_claims(arrivals(*WARMUP))
    year = pd.concat([make_claims(arrivals(*p)) for p in PERIODS], ignore_index=True)
    cool = make_claims(arrivals(*COOLDOWN))
    allc = pd.concat([warm.assign(warm=True), year.assign(warm=False), cool.assign(warm=True)],
                     ignore_index=True)
    allc = allc.sort_values("case_created_at", kind="stable").reset_index(drop=True)

    avail = qs.available_day(allc.case_created_at)
    key = allc.case_created_at.astype("int64").to_numpy().astype(float)
    start, depth, used = qs.run(avail, key)                     # first in, first out
    due = qs.due_day(allc.claim_received_at)
    decided = qs.decided_day(start, allc.work_days)
    allc["queue_depth"] = depth
    allc["first_touch_on"] = pd.to_datetime(start)
    allc["decided_on"] = pd.to_datetime(decided)
    allc["due_on"] = pd.to_datetime(due)
    allc["breached"] = decided > due

    df = allc[~allc.warm].drop(columns="warm").reset_index(drop=True)
    df.insert(0, "claim_id", [f"CL{n:06d}" for n in range(1, len(df) + 1)])
    noisy = rng.random(len(df)) < LABEL_NOISE
    shift = rng.integers(1, 3, len(df))
    idx = df.true_family.map(FAMILIES.index).to_numpy()
    df["family"] = np.array(FAMILIES)[np.where(noisy, (idx + shift) % 3, idx)]
    df = df.drop(columns="true_family")
    for c in ["first_touch_on", "decided_on", "due_on"]:
        df[c] = df[c].dt.strftime("%Y-%m-%d")
    for c in ["claim_received_at", "case_created_at"]:
        df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M")
    df.to_csv(HERE / "claims_closed.csv", index=False)
    cap = pd.Series(used, name="starts")
    cap.index = pd.to_datetime(cap.index).strftime("%Y-%m-%d")
    cap.rename_axis("day").to_csv(HERE / "capacity.csv")

    when = pd.to_datetime(df.claim_received_at)
    print(f"claims_closed.csv: {len(df):,} claims; family shares "
          f"{df.family.value_counts(normalize=True).round(3).to_dict()}")
    for name, lo, hi in [("train", "2025-01-01", "2025-09-01"), ("valid", "2025-09-01", "2025-11-01"),
                         ("test", "2025-11-01", "2026-01-01")]:
        part = df[(when >= lo) & (when < hi)]
        print(f"  {name:5s} {len(part):6,d} claims, breach rate {part.breached.mean():.1%}, "
              f"mean queue depth {part.queue_depth.mean():.0f}")
    print(f"  intake reason 'other': {(df.intake_reason == 'other').mean():.1%}")


if __name__ == "__main__":
    main()
