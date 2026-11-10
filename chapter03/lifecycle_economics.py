"""Measuring the lifecycle: break-even, cost per outcome and annual volumes.

Reproduces the numbers in the chapter's final section from the formulas and
from chapter01/disputes_sample.csv, and shows the Chapter 2 catalogue entries
that the exercises wire into the state machine. All amounts are illustrative.

Contesting costs H + (1 - p)(A + F) in expectation; refunding early costs
A + F_a. Contesting is cheaper when p > 1 - (A + F_a - H) / (A + F).

Run:  python lifecycle_economics.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
DISPUTES = HERE.parent / "chapter01" / "disputes_sample.csv"
TIMELINES = HERE.parent / "chapter02" / "timelines.yaml"
SCALE = 144   # 5,000 sample cases -> 720,000 cases a year (Chapter 1)

# Illustrative parameters (A from Table 1.2; F, F_a and H illustrative)
A, F, F_A, H = 186.0, 20.0, 5.0, 28.0
PLACEHOLDER_P = 0.42   # until the Chapter 10 model supplies p per case


def break_even_p(amount=A, fee=F, alert_fee=F_A, effort=H) -> float:
    return 1 - (amount + alert_fee - effort) / (amount + fee)


def expected_cost_contest(p, amount=A, fee=F, effort=H) -> float:
    return effort + (1 - p) * (amount + fee)


def cost_refund_early(amount=A, alert_fee=F_A) -> float:
    return amount + alert_fee


def contest_or_refund(amount, p=PLACEHOLDER_P, fee=F, alert_fee=F_A, effort=H) -> str:
    """The Recover decision rule; p is a placeholder until Chapter 10."""
    return "contest" if p > break_even_p(amount, fee, alert_fee, effort) else "refund_early"


def outcome_costs(amount=A, fee=F, alert_fee=F_A, effort=H) -> pd.DataFrame:
    rows = [
        ("Refunded at a pre-dispute alert", amount + alert_fee, f"${amount:.0f} refund plus ${alert_fee:.0f} alert fee"),
        ("Chargeback accepted", amount + fee, f"${amount:.0f} loss plus ${fee:.0f} fee"),
        ("Contested and won", effort, "Effort only; the sale is retained"),
        ("Contested and lost", effort + amount + fee, f"${effort:.0f} effort plus ${amount:.0f} loss plus ${fee:.0f} fee"),
    ]
    return pd.DataFrame(rows, columns=["Outcome for one claim", "Cost to the merchant", "Composition"])


def annual_volumes(path=DISPUTES) -> dict:
    d = pd.read_csv(path, parse_dates=["opened_at", "closed_at"])
    contested = int(d["represented"].sum()) * SCALE
    won = int(d.loc[d["represented"], "outcome"].eq("won").sum()) * SCALE
    return {"cases": len(d) * SCALE, "contested": contested, "won": won,
            "lost": contested - won, "win_rate": won / contested}


def catalogue_clocks(path=TIMELINES) -> dict[str, int]:
    """Visa response windows from the Chapter 2 catalogue, keyed by rule id."""
    with open(path, encoding="utf-8") as fh:
        rules = yaml.safe_load(fh)["rules"]
    wanted = {"visa_dispute_response", "visa_pre_arbitration_response"}
    return {r["id"]: r["amount"] for r in rules if r["id"] in wanted}


def clock_days_from_catalogue(path=TIMELINES) -> dict[str, int]:
    """EXERCISE (Question 4): build CLOCK_DAYS from chapter02/timelines.yaml.

    Map each clocked state (CHARGEBACK, PRE_ARBITRATION) to the catalogue rule
    whose starts_on event opens it, and decide what happens when the catalogue
    has no entry for a state. Left unimplemented on purpose.
    """
    raise NotImplementedError("Exercise: see Chapter 3, Question 4")


def main() -> None:
    p_star = break_even_p()
    print(f"Break-even win probability: {p_star:.1%}  (A=${A:.0f}, F=${F:.0f}, F_a=${F_A:.0f}, H=${H:.0f})")
    print()
    print("Table 3.6: cost of each outcome (illustrative)")
    print(outcome_costs().to_string(index=False))
    print()
    print("Expected cost of contesting vs refunding early:")
    for p in (0.10, p_star, 0.42, 0.70):
        print(f"  p={p:.2f}: contest ${expected_cost_contest(p):7.2f}   refund early ${cost_refund_early():7.2f}"
              f"   -> {contest_or_refund(A, p)}")
    print()
    v = annual_volumes()
    print("Annual volumes at the representative issuer (chapter01/disputes_sample.csv x 144):")
    print(f"  cases {v['cases']:,}  contested {v['contested']:,}  won {v['won']:,}  lost {v['lost']:,}"
          f"  win rate {v['win_rate']:.0%}")
    print()
    print("Chapter 2 catalogue windows the exercises wire in:", catalogue_clocks())


if __name__ == "__main__":
    main()
