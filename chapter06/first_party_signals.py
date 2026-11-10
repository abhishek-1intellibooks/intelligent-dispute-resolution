"""First-party signals, a tier with reasons and the contest threshold (Chapter 6).

build_signals   per-cardholder signals over a window anchored to an as-of date
score_signals   explicit points with readable reasons, mapped to a tier
contest_threshold  the claim amount above which contesting is worth considering:
                   contest only if p*A > c + q*V, i.e. A > (c + q*V) / p

A tier routes a claim to a queue. It never closes a claim, denies credit or
restricts an account (Table 6.4).

Run:  python first_party_signals.py
"""
import warnings
from pathlib import Path

import pandas as pd

# A cardholder with one claim has no gap; its median is NaN, which is intended.
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
DATA = HERE / "disputes_extended.csv"
AS_OF = "2026-09-30 23:59:59"


def build_signals(disputes, as_of, window_days=90):
    end = pd.Timestamp(as_of)
    start = end - pd.Timedelta(window_days, unit="D")
    mask = (disputes["opened_at"] > start) & (disputes["opened_at"] <= end)
    g = disputes[mask].groupby("card_id")
    share = lambda s: s.value_counts(normalize=True).iloc[0]
    gap = lambda s: s.sort_values().diff().dt.days.median()
    return pd.DataFrame({
        "claims": g.size(),
        "not_received_share": g["reason"].apply(
            lambda s: (s == "not_received").mean()),
        "top_merchant_share": g["merchant_id"].agg(share),
        "proof_rate": g["delivery_confirmed"].mean(),
        "median_gap_days": g["opened_at"].apply(gap),
    })


def score_signals(f):
    rows = []
    for card, r in f.iterrows():
        pts, why = 0, []
        if r.claims >= 4:
            pts += 3; why.append("4+ claims in window")
        elif r.claims >= 3:
            pts += 2; why.append("3 claims in window")
        if r.claims >= 3 and r.not_received_share >= 0.75:
            pts += 1; why.append("mostly not-received")
        if r.proof_rate >= 0.6:
            pts += 2; why.append("delivery confirmed on most")
        if r.median_gap_days <= 14:
            pts += 1; why.append("claims close together")
        if r.top_merchant_share > 0.5:
            pts -= 2; why.append("concentrated at one merchant")
        rows.append((max(pts, 0), "; ".join(why)))
    out = f.assign(points=[p for p, _ in rows],
                   reasons=[w for _, w in rows])
    out["tier"] = pd.cut(out["points"], [-1, 2, 4, 99],
                         labels=["standard", "clarify", "review"])
    return out


def contest_threshold(p_win, cost, attrition, value):
    return (cost + attrition * value) / p_win


# ---------------------------------------------------------------- helpers
def load(path=DATA) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["opened_at", "closed_at"])


def first_party_only(disputes: pd.DataFrame) -> pd.DataFrame:
    """The score is computed only for claims classified as first-party (Chapter 9 label)."""
    return disputes[disputes["family"] == "first_party"]


def concentration(disputes: pd.DataFrame, top_share: float = 0.03) -> float:
    """Share of all disputes raised by the top `top_share` of disputing cardholders."""
    counts = disputes["card_id"].value_counts()
    k = max(1, round(top_share * len(counts)))
    return counts.iloc[:k].sum() / counts.sum()


def threshold_table(cost=40.0, attrition=0.05) -> pd.DataFrame:
    """Table 6.3: three cardholders against the contest threshold."""
    rows = [("A: new, low margin", 240, 150), ("B: long-tenured, high margin", 95, 2000),
            ("C: established, mid margin", 186, 600)]
    out = []
    for name, amount, value in rows:
        t42 = contest_threshold(0.42, cost, attrition, value)
        t70 = contest_threshold(0.70, cost, attrition, value)
        if amount > t42 and amount > t70 and amount - t42 > 0.25 * t42:
            treatment = "Above both lines: review, then contest"
        elif amount < t42 and amount < t70:
            treatment = "Below both lines: accept and clarify"
        else:
            treatment = "Close to the line: analyst decides"
        out.append((name, amount, value, round(t42), round(t70), treatment))
    return pd.DataFrame(out, columns=["Cardholder", "Claim A", "V", "Threshold p=0.42",
                                      "Threshold p=0.70", "Treatment"])


def main() -> None:
    pd.set_option("display.width", 140)
    disputes = load()
    print(f"Disputes: {len(disputes):,}; disputing cardholders: {disputes['card_id'].nunique():,}")
    print(f"Top 3% of disputing cardholders raise {concentration(disputes):.1%} of all disputes (12 months)")
    print()

    signals = build_signals(first_party_only(disputes), AS_OF)
    scored = score_signals(signals)
    print(f"Signals as of {AS_OF[:10]} (90-day window, first-party claims): {len(scored):,} cardholders")
    print("Tier counts:", scored["tier"].value_counts().reindex(["standard", "clarify", "review"]).to_dict())
    print()

    ungated = score_signals(build_signals(disputes, AS_OF))
    extra = ungated[ungated["tier"] != "standard"].index.difference(scored[scored["tier"] != "standard"].index)
    burst = disputes[disputes["card_id"].isin(extra)].groupby("card_id")["family"].agg(
        lambda s: (s == "unauthorized").mean() > 0.5).sum()
    print(f"Without the family gate, {len(extra)} more cardholders would leave the standard tier; "
          f"{burst} of them are mostly unauthorized claims (compromise bursts, not misuse)")
    print()

    cols = ["claims", "not_received_share", "top_merchant_share", "proof_rate",
            "median_gap_days", "points", "tier"]
    print("Table 6.5: sample output of the signal pipeline")
    print(scored.loc[["c741", "c2677", "c3578"], cols].round(2).to_string())
    print()
    print("Worked example (four not-received claims, four merchants):")
    print(scored.loc[["c1024"], cols + ["reasons"]].round(2).to_string())
    print()
    print("Highest-scoring cardholders:")
    print(scored.sort_values(["points", "claims"], ascending=False)
          .head(8)[cols + ["reasons"]].round(2).to_string())
    print()
    print(f"Contest threshold with no relationship value: ${contest_threshold(0.42, 40, 0.05, 0):,.0f}")
    print("Table 6.3: contest thresholds (c = $40, q = 0.05)")
    print(threshold_table().to_string(index=False))


if __name__ == "__main__":
    main()
