"""Replay September to December under competing policies (Listing 10.5).

Because the data are synthetic, the simulator knows the outcome of every case
(won_if_contested), so any policy's choices can be scored. A real institution
cannot do this; the last column estimates each policy's value from the random
exploration sample alone, which needs no simulator.

Prints Table 10.6, the ranking curve of Figure 10.6 and the segment monitoring
of Figure 10.7, and writes figures 10.4 to 10.7 to figures/.
"""
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from fight_or_accept import CONTEST_COST, MODEL, fight_or_accept
from outcome_features import decision_view

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
FIGURES = HERE / "figures"


def replay(window, decided, p_raw):
    policies = {
        "Historical practice": window.contested.to_numpy(),
        "Contest everything": np.ones(len(window), bool),
        "Average win rate (42%)": (0.42 * window.amount > CONTEST_COST).to_numpy(),
        "Model, uncalibrated": (p_raw * window.amount > CONTEST_COST).to_numpy(),
        "Model, calibrated (fight_or_accept)":
            ((decided.decision != "accept") & (decided.expected_value > 0)).to_numpy(),
        "Perfect foresight": window.won_if_contested.to_numpy(),
    }
    x = window.exploration.to_numpy()
    gain = np.where(window.won_if_contested, window.amount, 0.0) - CONTEST_COST
    rows = []
    for name, contest in policies.items():
        won = contest & window.won_if_contested.to_numpy()
        recovered = window.amount.to_numpy()[won].sum()
        cost = contest.sum() * CONTEST_COST
        estimate = (contest[x] * gain[x]).mean() * len(window)   # exploration only
        if name == "Historical practice":       # exploration cases were part of it
            estimate = float("nan")
        rows.append({"policy": name, "contested": int(contest.sum()),
                     "win_rate": float(won.sum() / max(contest.sum(), 1)),
                     "recovered": float(recovered), "cost": float(cost),
                     "net": float(recovered - cost),
                     "explore_estimate": float(estimate)})
    return pd.DataFrame(rows).set_index("policy"), policies


def money(v):
    return "n/a" if np.isnan(v) else f"${v:,.0f}"


def main():
    df = pd.read_csv(HERE / "contest_history.csv", parse_dates=["decided_at"])
    window = df[df.decided_at >= "2025-09-01"]
    decided = fight_or_accept(window)
    p_raw = MODEL.model.predict_proba(decision_view(window))[:, 1]

    table, policies = replay(window, decided, p_raw)
    print(f"Table 10.6: four months of recovery decisions under six policies "
          f"({len(window):,} cases)")
    shown = table.copy()
    shown["win_rate"] = shown.win_rate.map("{:.1%}".format)
    for c in ("recovered", "cost", "net", "explore_estimate"):
        shown[c] = shown[c].map(money)
    shown["contested"] = shown.contested.map("{:,}".format)
    print(shown.to_string())

    hist = table.loc["Historical practice"]
    cal = table.loc["Model, calibrated (fight_or_accept)"]
    raw = table.loc["Model, uncalibrated"]
    print(f"\nCalibrated vs uncalibrated: net {cal.net - raw.net:+,.0f}, "
          f"contests {int(cal.contested - raw.contested):+,} "
          f"({(cal.contested - raw.contested) / raw.contested:+.0%}); "
          f"calibrated net is {cal.net / hist.net:.2f}x historical practice")

    review = (decided.decision == "review").sum()
    late = (decided.reason == "past the time limit").sum()
    print(f"Review band: {review:,} of {len(window):,} cases ({review / len(window):.1%}); "
          f"past the time limit: {late}")

    # Figure 10.6: the ranking curve (cases in order of expected value)
    ev = decided.expected_value.to_numpy()
    gain = np.where(window.won_if_contested, window.amount, 0.0) - CONTEST_COST
    order = np.argsort(-ev)
    exp_cum, real_cum = np.cumsum(ev[order]), np.cumsum(gain[order])
    n_pos = int((ev > 0).sum())
    print(f"\nRanking curve: {n_pos:,} positive-value cases; net from all of them "
          f"${real_cum[n_pos - 1]:,.0f} (expected ${exp_cum[n_pos - 1]:,.0f}, "
          f"gap ${exp_cum[n_pos - 1] - real_cum[n_pos - 1]:,.0f})")
    for k in (2000, 2500, 3000):
        print(f"  best {k:,} cases return ${real_cum[k - 1]:,.0f} "
              f"({real_cum[k - 1] / real_cum[n_pos - 1]:.0%} of the positive-value net)")

    # Figure 10.7: monitoring by segment, for the cases the calibrated policy contested
    chosen = policies["Model, calibrated (fight_or_accept)"]
    mon = pd.DataFrame({"month": window.decided_at.dt.to_period("M").astype(str),
                        "segment": np.where(window.reason == "fraud_cnp",
                                            "Card-not-present fraud", "All other reasons"),
                        "p": decided.p_win.to_numpy(),
                        "won": window.won_if_contested.to_numpy(),
                        "amount": window.amount.to_numpy()})[chosen]
    by = mon.groupby(["segment", "month"]).agg(cases=("won", "size"),
                                               predicted=("p", "mean"),
                                               observed=("won", "mean"))
    print("\nFigure 10.7: predicted and observed win rates of contested cases")
    print(by.to_string(formatters={"predicted": "{:.1%}".format,
                                   "observed": "{:.1%}".format}))
    shortfall = (mon.p - mon.won) * mon.amount
    after = mon.month >= "2025-10"
    fraud_after = after & (mon.segment == "Card-not-present fraud")
    print(f"Fraud cases contested after the rule change: {fraud_after.sum():,} "
          f"({fraud_after.sum() / len(mon):.0%} of contests)")
    print(f"Realized recovery short of expectation: ${shortfall.sum():,.0f} in all; "
          f"${shortfall[fraud_after].sum():,.0f} from fraud cases after the change, "
          f"${shortfall[~fraud_after].sum():,.0f} from all other contests")

    figures(window, decided, table, exp_cum, real_cum, n_pos, by)


def figures(window, decided, table, exp_cum, real_cum, n_pos, by):
    FIGURES.mkdir(exist_ok=True)
    # Figure 10.4: the decision map
    fig, ax = plt.subplots(figsize=(6, 4.5))
    colors = {"contest": "tab:blue", "accept": "tab:grey", "review": "tab:orange"}
    for d, c in colors.items():
        s = decided.decision == d
        ax.scatter(decided.p_win[s], window.amount[s], s=3, alpha=0.4, c=c, label=d)
    p = np.linspace(0.03, 1, 200)
    ax.plot(p, CONTEST_COST / p, color="black", label="break-even A = c / p")
    ax.axhline(CONTEST_COST / 0.42, ls=":", color="black", label="average-rate rule")
    ax.set_yscale("log")
    ax.set_xlabel("Calibrated probability of winning")
    ax.set_ylabel("Amount ($)")
    ax.legend(markerscale=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig10_4_decision_map.png", dpi=120)
    plt.close(fig)

    # Figure 10.5: net recovery by policy
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.barh(table.index[::-1], table.net[::-1] / 1000, color="tab:blue")
    ax.set_xlabel("Net recovery, September to December ($ thousands)")
    fig.tight_layout()
    fig.savefig(FIGURES / "fig10_5_net_by_policy.png", dpi=120)
    plt.close(fig)

    # Figure 10.6: the ranking curve
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(exp_cum / 1000, label="Expected by the model")
    ax.plot(real_cum / 1000, label="Realized")
    ax.axvline(n_pos, ls=":", color="grey")
    ax.set_xlabel("Cases contested, best expected value first")
    ax.set_ylabel("Cumulative net ($ thousands)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "fig10_6_ranking_curve.png", dpi=120)
    plt.close(fig)

    # Figure 10.7: monitoring by segment
    fig, ax = plt.subplots(figsize=(6, 4))
    for seg, g in by.groupby(level="segment"):
        months = g.index.get_level_values("month")
        line, = ax.plot(months, g.observed, marker="o", label=f"{seg}, observed")
        ax.plot(months, g.predicted, ls="--", color=line.get_color(),
                label=f"{seg}, predicted")
    ax.set_ylabel("Win rate of contested cases")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig10_7_monitoring.png", dpi=120)
    plt.close(fig)
    print("\nsaved figures 10.4 to 10.7 to figures/")


if __name__ == "__main__":
    main()
