"""Three-year scenarios and one-at-a-time sensitivity (Tables 7.5-7.6, Figure 7.4).

Reuses run_levers() from business_case.py. Program costs and the adoption
ramp mirror the Costs and Inputs sheets of business_case.xlsx. All figures
are illustrative.

    python sensitivity.py            # prints scenarios and the tornado table
    python sensitivity.py --plot     # also writes sensitivity.png (matplotlib)
"""

import sys
from pathlib import Path

from business_case import run_levers

HERE = Path(__file__).resolve().parent
COSTS = (7.0e6, 4.0e6, 3.5e6)          # Costs sheet totals by year (assumption)
RAMP = (0.35, 0.75, 1.00)              # adoption by year (assumption)
SLOW_RAMP = (0.20, 0.50, 0.85)         # sensitivity case (assumption)
RATE = 0.10                            # discount rate (assumption)
SCENARIOS = {"Conservative": (0.60, 1.25), "Base": (1.00, 1.00), "Upside": (1.20, 1.00)}


def npv(rate, flows):
    """Excel NPV convention: the first flow is discounted one full period."""
    return sum(v / (1 + rate) ** (i + 1) for i, v in enumerate(flows))


def three_year(run_rate, ramp=RAMP, benefit_x=1.0, cost_x=1.0):
    benefit = [run_rate * a * benefit_x for a in ramp]
    cost = [c * cost_x for c in COSTS]
    net = [b - c for b, c in zip(benefit, cost)]
    cum, total = [], 0.0
    for v in net:
        total += v
        cum.append(total)
    if cum[0] >= 0:
        payback = 0.0
    elif cum[1] >= 0:
        payback = 12 + 12 * -cum[0] / net[1]
    elif cum[2] >= 0:
        payback = 24 + 12 * -cum[1] / net[2]
    else:
        payback = None
    return {"benefit": benefit, "cost": cost, "net": net, "cumulative": cum,
            "total_net": cum[-1], "npv": npv(RATE, net), "payback_months": payback}


def scenarios(run_rate):
    return {name: three_year(run_rate, RAMP, b, c) for name, (b, c) in SCENARIOS.items()}


# one assumption at a time: (label, low kwargs, high kwargs, low ramp, high ramp)
SWINGS = [
    ("Adoption ramp (20/50/85% vs 50/90/100%)", {}, {}, SLOW_RAMP, (0.50, 0.90, 1.00)),
    ("Target win rate (46% vs 54%)", {"win_to": 0.46}, {"win_to": 0.54}, RAMP, RAMP),
    ("Decide handling saving ($6 vs $12)", {"decide_saving": 6.0}, {"decide_saving": 12.0}, RAMP, RAMP),
    ("Prevent: cases avoided (2% vs 6%)", {"avoid": 0.02}, {"avoid": 0.06}, RAMP, RAMP),
    ("Deflect: resolved early (3% vs 9%)", {"deflect": 0.03}, {"deflect": 0.09}, RAMP, RAMP),
]


def tornado():
    base = three_year(sum(run_levers().values()))["npv"]
    rows = []
    for label, lo, hi, lo_ramp, hi_ramp in SWINGS:
        low = three_year(sum(run_levers(**lo).values()), lo_ramp)["npv"] - base
        high = three_year(sum(run_levers(**hi).values()), hi_ramp)["npv"] - base
        rows.append((label, low, high))
    return base, sorted(rows, key=lambda r: -abs(r[1]))


def main():
    run_rate = sum(run_levers().values())
    print(f"Run-rate benefit: ${run_rate / 1e6:.2f}M")
    for name, s in scenarios(run_rate).items():
        pb = "beyond year 3" if s["payback_months"] is None else f"{s['payback_months']:.1f} months"
        print(f"{name:12s} net by year {[round(v / 1e6, 2) for v in s['net']]}  "
              f"3-yr net ${s['total_net'] / 1e6:6.2f}M  NPV ${s['npv'] / 1e6:6.2f}M  payback {pb}")
    base, rows = tornado()
    print(f"\nSensitivity of three-year NPV (base ${base / 1e6:.2f}M), change in $M:")
    for label, low, high in rows:
        print(f"  {label:42s} {low / 1e6:+6.2f}  {high / 1e6:+6.2f}")
    if "--plot" in sys.argv:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 3.5))
        labels = [r[0] for r in rows][::-1]
        ax.barh(labels, [r[1] / 1e6 for r in rows][::-1], color="#c0504d", label="low")
        ax.barh(labels, [r[2] / 1e6 for r in rows][::-1], color="#4f81bd", label="high")
        ax.axvline(0, color="black", lw=0.8)
        ax.set_xlabel("Change in three-year NPV ($M, illustrative)")
        ax.legend(loc="lower right")
        fig.tight_layout()
        fig.savefig(HERE / "sensitivity.png", dpi=120)
        print("wrote sensitivity.png")


if __name__ == "__main__":
    main()
