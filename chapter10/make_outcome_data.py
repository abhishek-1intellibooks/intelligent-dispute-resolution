"""Generate contest_history.csv: a synthetic year of 30,000 recovery decisions.

Each row is a worked card dispute at the moment the issuer decides whether to
contest it (pursue the merchant through the network process) or accept the
loss. About 31 percent of cases were contested: most were chosen by analysts,
and a random exploration sample of about 6 percent of all cases was contested
regardless of anyone's judgment.

The simulator also writes two columns that a real institution never has:
p_true, the true probability of winning if contested, and won_if_contested,
the outcome each case would have had if contested. They exist so that any
policy can be scored (policy_eval.py) and must never be used as features.

Selection bias is built in on purpose. Analysts see something the data do not
record (a hidden factor, such as how diligent the merchant's back office is
this month) and prefer cases where it favors the issuer. Their contested cases
therefore win more often than randomly chosen ones.

On 1 October 2025 the synthetic network changes a rule that strengthens
merchants' defenses against card-not-present fraud claims. No feature captures
the change (Figure 10.7).

All data are synthetic and every amount is illustrative.
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "contest_history.csv"
SEED = 10

# Exact monthly volumes: 19,828 decisions from January to August and
# 10,172 from September to December (30,000 in all).
MONTHS = [2450, 2380, 2490, 2470, 2500, 2480, 2520, 2538,   # Jan-Aug
          2460, 2500, 2560, 2652]                           # Sep-Dec
EXPLORE = {"early": 1171, "late": 663}       # random exploration contests
ANALYST = {"early": 4906, "late": 2455}      # contests chosen by analysts
RULE_CHANGE = pd.Timestamp("2025-10-01")

REASONS = ["not_received", "fraud_cnp", "not_as_described", "duplicate",
           "credit_not_processed", "cancelled_recurring"]
REASON_P = [0.24, 0.27, 0.17, 0.09, 0.13, 0.10]
REASON_P_Q4 = [0.22, 0.36, 0.15, 0.08, 0.11, 0.08]
REASON_BASE = {"not_received": 0.55, "fraud_cnp": 0.45, "not_as_described": -0.95,
               "duplicate": 1.75, "credit_not_processed": 0.95,
               "cancelled_recurring": -0.15}
MCC = ["retail", "electronics", "travel", "digital", "subscription"]
MCC_EFFECT = {"retail": 0.0, "electronics": -0.15, "travel": 0.10,
              "digital": -0.25, "subscription": -0.05}
NETWORKS = ["visa", "mastercard"]

INTERCEPT = -1.12        # sets the year's random-contest win rate (about 37%)
HIDDEN_SD = 1.35         # what the issuer never sees; limits AUC to about 0.75
FRAUD_SHIFT = -1.2       # card-not-present fraud after the 1 October rule change
ANALYST_HIDDEN = 0.35    # analysts' preference for the hidden factor
ANALYST_AMOUNT = 0.8     # ... for large claims
ANALYST_OBSERVED = 0.0   # ... for what the record shows
OBS_SCALE = 0.75         # strength of the recorded features
AMOUNT_COEF = -0.50      # larger claims are harder to win
MEDIAN = 92.0            # median claim outside travel and electronics


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def decision_dates(rng):
    days = []
    for m, n in enumerate(MONTHS, start=1):
        start = pd.Timestamp(2025, m, 1)
        length = start.days_in_month
        days.append(start + pd.to_timedelta(rng.integers(0, length, n), unit="D"))
    return pd.DatetimeIndex(np.concatenate([d.values for d in days]))


def generate(seed=SEED):
    rng = np.random.default_rng(seed)
    decided_at = decision_dates(rng)
    n = len(decided_at)

    # Merchants, each with a history of answering and winning chargebacks
    n_merch = 2500
    m_mcc = rng.choice(MCC, n_merch, p=[0.38, 0.17, 0.13, 0.17, 0.15])
    m_rep = rng.beta(6, 4, n_merch)
    m_win = rng.beta(5, 5.5, n_merch)
    merchant = rng.integers(0, n_merch, n)

    # Card-not-present fraud claims rise in the holiday quarter
    reason = rng.choice(REASONS, n, p=REASON_P)
    holiday = decided_at >= RULE_CHANGE
    reason[holiday] = rng.choice(REASONS, holiday.sum(), p=REASON_P_Q4)
    mcc_group = m_mcc[merchant]
    network = rng.choice(NETWORKS, n, p=[0.62, 0.38])

    median = np.where(mcc_group == "travel", 240.0,
                      np.where(mcc_group == "electronics", 160.0, MEDIAN))
    amount = np.round(np.exp(np.log(median) + rng.normal(0, 0.9, n)), 2)
    amount = np.clip(amount, 5.0, 6000.0)

    rep_rate = np.clip(m_rep[merchant] + rng.normal(0, 0.03, n), 0.02, 0.99).round(3)
    win_rate = np.clip(m_win[merchant] + rng.normal(0, 0.03, n), 0.02, 0.98).round(3)
    responded = rng.random(n) < rep_rate

    fraud = reason == "fraud_cnp"
    liability_shift = fraud & (rng.random(n) < 0.30)
    ce3_eligible = fraud & ~liability_shift & (rng.random(n) < 0.15)

    tracking = np.full(n, "none", dtype=object)
    goods = np.isin(reason, ["not_received", "not_as_described"]) & responded
    draw = rng.random(n)
    tracking[goods & (draw < 0.50)] = "tracking"
    tracking[goods & (draw >= 0.50) & (draw < 0.75)] = "signature"

    days_to_file = np.maximum(1, np.round(rng.gamma(2.5, 12.0, n))).astype(int)
    evidence = rng.beta(4, 2, n).round(3)
    fp_score = np.clip(rng.beta(1.5, 6, n) + 0.08 * fraud, 0, 1).round(3)
    prior = rng.poisson(0.4 + 2.0 * fp_score)

    hidden = rng.normal(0, HIDDEN_SD, n)
    observed = INTERCEPT + OBS_SCALE * (
                pd.Series(reason).map(REASON_BASE).to_numpy()
                + pd.Series(mcc_group).map(MCC_EFFECT).to_numpy()
                + 0.05 * (network == "mastercard")
                + 1.9 * ~responded
                - 1.45 * (tracking == "tracking") - 2.8 * (tracking == "signature")
                - 1.7 * liability_shift - 1.3 * ce3_eligible
                - 2.2 * (win_rate - 0.48) - 0.8 * (rep_rate - 0.6)
                - 0.012 * (days_to_file - 30)
                + 1.2 * (evidence - 0.67)
                - 2.0 * (fp_score - 0.2) - 0.12 * prior
                + AMOUNT_COEF * np.log(amount / 120) * (reason != "duplicate"))
    shift = FRAUD_SHIFT * (fraud & (decided_at >= RULE_CHANGE))
    p_true = sigmoid(observed + hidden + shift)
    p_true = np.where(days_to_file > 120, 0.01, p_true)     # missed deadline loses
    won_if_contested = rng.random(n) < p_true

    df = pd.DataFrame({
        "case_id": [f"R{i:06d}" for i in range(1, n + 1)],
        "decided_at": decided_at.strftime("%Y-%m-%d"),
        "amount": amount, "network": network, "reason": reason,
        "mcc_group": mcc_group, "liability_shift": liability_shift,
        "ce3_eligible": ce3_eligible, "merchant_tracking": tracking,
        "merchant_responded": responded, "merchant_rep_rate": rep_rate,
        "merchant_win_rate": win_rate, "days_to_file": days_to_file,
        "evidence_completeness": evidence, "first_party_score": fp_score,
        "prior_disputes_12m": prior,
    })

    # Who gets a label: a random exploration sample, then the analysts' picks
    early = (decided_at < "2025-09-01")
    exploration = np.zeros(n, bool)
    contested = np.zeros(n, bool)
    taste = (ANALYST_HIDDEN * hidden + ANALYST_AMOUNT * np.log(amount / 120)
             + ANALYST_OBSERVED * observed + rng.gumbel(0, 1, n))
    for period, mask in (("early", early), ("late", ~early)):
        idx = np.flatnonzero(mask)
        pick = rng.choice(idx, EXPLORE[period], replace=False)
        exploration[pick] = True
        pool = idx[~exploration[idx] & (days_to_file[idx] <= 120)]
        chosen = pool[np.argsort(-taste[pool])[:ANALYST[period]]]
        contested[chosen] = True
    contested |= exploration

    df["contested"] = contested
    df["exploration"] = exploration
    df["won"] = np.where(contested, won_if_contested.astype(float), np.nan)
    df["outcome_stage"] = outcome_stage(rng, contested, won_if_contested,
                                        responded, days_to_file)
    df["won_if_contested"] = won_if_contested
    df["p_true"] = p_true.round(4)
    return df


def outcome_stage(rng, contested, won, responded, days):
    """Where each contested case ended (Table 10.1); blank if accepted."""
    stage = np.full(len(won), "", dtype=object)
    r = rng.random(len(won))
    stage[contested & won & ~responded] = "chargeback_stands"
    stage[contested & won & responded & (r < 0.7)] = "pre_arbitration_won"
    stage[contested & won & responded & (r >= 0.7)] = "arbitration_won"
    stage[contested & ~won & (r < 0.8)] = "representment_accepted"
    stage[contested & ~won & (r >= 0.8)] = "arbitration_lost"
    stage[contested & ~won & (days > 120)] = "missed_deadline"
    return stage


def main():
    df = generate()
    df.to_csv(OUT, index=False)
    c, x = df[df.contested & ~df.exploration], df[df.exploration]
    gain = np.where(x.won_if_contested, x.amount, 0.0) - 40.0
    print(f"wrote {OUT.name}: {len(df):,} decisions")
    print(f"  contested: {df.contested.sum():,} ({df.contested.mean():.1%}); "
          f"exploration: {len(x):,} ({len(x) / len(df):.1%})")
    print(f"  win rate, all contested: {df.won.mean():.1%}")
    print(f"  win rate, analysts' choices: {c.won.mean():.1%}")
    print(f"  win rate, exploration sample: {x.won.mean():.1%}")
    print(f"  exploration net per case after $40 cost: ${gain.mean():.2f}")
    print(f"  average claim: ${df.amount.mean():.2f}")


if __name__ == "__main__":
    main()
