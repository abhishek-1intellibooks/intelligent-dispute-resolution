"""The evidence pipeline (Listing 11.5) and its evaluation on 4,000 packets.

build_evidence chooses a reading for each fact through the fallback chain,
asks a person when no reading passes the confidence gate, keeps a trail of
where every value came from, and scores the result against the rule set in
force when the case was opened.

Run as a script, it reads evidence_packets/ and prints Figure 11.2 (fields
read correctly by channel), Figure 11.5 (accuracy against coverage), Table
11.6 (naive vs gated pipeline), Figure 11.4 (does the score mean anything?)
and Table 11.7 (analyst time).
"""
from collections import namedtuple
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from extract import Fact, facts_from_readings, read_value
from requirements import RULE_SETS, rules_for
from sufficiency import sufficiency

HERE = Path(__file__).resolve().parent
PACKETS = HERE / "evidence_packets"

TRUST = {"api": 0, "native": 1, "screenshot": 2, "clean_scan": 3, "photo": 4}
GATE = 0.80
VERSION = "evidence-1.0"


def choose(readings, gate=GATE):
    """Best channel first; the first reading above the gate wins."""
    for f in sorted(readings, key=lambda f: TRUST[f.channel]):
        if f.value is not None and f.confidence >= gate:
            return f, "auto"
    return None, "review"


def build_evidence(case, readings_by_fact, review, gate=GATE):
    rules = rules_for(case.reason, case.opened_on, RULE_SETS)
    chosen, trail = {}, []
    for name, readings in readings_by_fact.items():
        fact, how = choose(readings, gate)
        if how == "review":
            fact = review(case, name, readings)        # a person confirms the value
        chosen[name] = fact.value
        trail.append({"fact": name, "value": fact.value, "doc": fact.doc_id,
                      "page": fact.page, "channel": fact.channel,
                      "confidence": fact.confidence, "how": how})
        if name == "delivered_to":
            chosen["delivered_to_channel"] = fact.channel
    score, gaps, verdict = sufficiency(chosen, case, rules)
    return {"case_id": case.case_id, "facts": trail, "score": score,
            "verdict": verdict, "gaps": gaps, "rules": rules["version"],
            "needs_review": verdict == "borderline", "pipeline": VERSION}


# ------------------------------------------------------------- data loading
Case = namedtuple("Case", "case_id reason opened_on claimed_on expected_on "
                          "amount_cents currency")


def load_cases(cases):
    return {r.case_id: Case(r.case_id, r.reason, date.fromisoformat(r.opened_on),
                            date.fromisoformat(r.claimed_on),
                            date.fromisoformat(r.expected_on),
                            int(r.amount_cents), r.currency)
            for r in cases.itertuples(index=False)}


def true_values(readings):
    """{(doc_id, field): canonical value of the true text} - the perfect reading."""
    return {(r.doc_id, r.field): read_value(r.field, r.true_text,
                                             r.date_format if isinstance(r.date_format, str) else "")
            for r in readings.itertuples(index=False)}


def person(truth):
    """A review callback: the person reads the most trusted document correctly."""
    def review(case, name, readings):
        best = sorted(readings, key=lambda f: TRUST[f.channel])[0]
        return Fact(name, truth[(best.doc_id, name)], 1.0, best.doc_id, best.page,
                    best.channel, extractor="person")
    return review


def perfect_scores(cases, readings, truth_frame=None):
    """Sufficiency score of every packet read perfectly (used by the generator)."""
    by_case = load_cases(cases)
    facts = facts_from_readings(readings)
    review = person(true_values(readings))
    out = []
    for cid, case in by_case.items():
        rec = build_evidence(case, facts.get(cid, {}), review, gate=1.01)  # all by person
        out.append(rec["score"])
    return np.array(out)


def auc(y, s):
    """Area under the ROC curve (ties count half)."""
    y, s = np.asarray(y, bool), np.asarray(s, float)
    ranks = pd.Series(s).rank().to_numpy()
    n1, n0 = y.sum(), (~y).sum()
    return (ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


# --------------------------------------------------------------- evaluation
def run(gate, cases, facts, review, truth):
    rows = []
    for cid, case in cases.items():
        rec = build_evidence(case, facts.get(cid, {}), review, gate=gate)
        wrong = sum(1 for t in rec["facts"]
                    if t["how"] == "auto" and t["value"] != truth[(t["doc"], t["fact"])])
        rows.append({"case_id": cid, "score": rec["score"], "verdict": rec["verdict"],
                     "wrong": wrong,
                     "reviewed": sum(t["how"] == "review" for t in rec["facts"])})
    return pd.DataFrame(rows).set_index("case_id")


def field_accuracy(readings, facts, truth):
    rows = []
    for f_list in facts.values():
        for name, fl in f_list.items():
            for f in fl:
                rows.append({"field": name, "channel": f.channel,
                             "confidence": f.confidence,
                             "correct": f.value is not None
                             and f.value == truth[(f.doc_id, name)]})
    return pd.DataFrame(rows)


def main():
    cases_df = pd.read_csv(PACKETS / "cases.csv")
    readings = pd.read_csv(PACKETS / "readings.csv", keep_default_na=False)
    outcome = pd.read_csv(PACKETS / "truth.csv").set_index("case_id")
    cases = load_cases(cases_df)
    facts = facts_from_readings(readings)
    truth = true_values(readings)
    review = person(truth)

    acc = field_accuracy(readings, facts, truth)
    print(f"Figure 11.2: {len(acc):,} field readings, {acc.correct.mean():.1%} read correctly")
    by = acc.pivot_table(index="channel", columns="field", values="correct",
                         aggfunc="mean").reindex(list(TRUST))
    by["all fields"] = acc.groupby("channel").correct.mean()
    by["readings"] = acc.groupby("channel").size()
    print(by.to_string(float_format="{:.1%}".format))

    print(f"\nFigure 11.5: accuracy against coverage (gate on field confidence)")
    for g in (0.5, 0.6, 0.7, 0.8, 0.9):
        line = []
        for ch in ("screenshot", "clean_scan", "photo"):
            a = acc[acc.channel == ch]
            kept = a[a.confidence >= g]
            line.append(f"{ch} {len(kept) / len(a):.0%} at "
                        f"{kept.correct.mean() if len(kept) else float('nan'):.1%}")
        print(f"  gate {g:.2f}: " + "; ".join(line))
    kept = acc[acc.confidence >= GATE]
    print(f"  all channels at {GATE}: {len(kept) / len(acc):.1%} of readings accepted "
          f"at {kept.correct.mean():.1%} accuracy")

    perfect = outcome.perfect_score
    naive = run(0.0, cases, facts, review, truth)
    gated = run(GATE, cases, facts, review, truth)
    n = len(cases)

    def row(r):
        p_suff = perfect.reindex(r.index) >= 0.70
        return {
            "Cases with at least one wrong fact":
                f"{(r.wrong > 0).sum():,} ({(r.wrong > 0).mean():.1%})",
            "Wrong facts used in scoring": f"{r.wrong.sum():,}",
            "Cases sent to a person":
                f"{(r.reviewed > 0).sum():,} ({(r.reviewed > 0).mean():.1%})",
            "Facts reviewed by a person": f"{r.reviewed.sum():,}",
            "Cases scored without a person":
                f"{(r.reviewed == 0).sum():,} ({(r.reviewed == 0).mean():.1%})",
            "Sufficient evidence judged not sufficient":
                f"{(p_suff & (r.verdict != 'sufficient')).sum():,}",
            "Insufficient evidence judged sufficient":
                f"{(~p_suff & (r.verdict == 'sufficient')).sum():,}",
            "Score identical to a perfect reading":
                f"{(r.score == perfect.reindex(r.index)).mean():.1%}",
        }
    table = pd.DataFrame({"Accept every reading": row(naive),
                          f"Confidence gate at {GATE:.2f}": row(gated)})
    print(f"\nTable 11.6: two pipelines on {n:,} not-received packets")
    print(table.to_string())

    # Figure 11.4: does the score mean anything?
    won = outcome.prevailed.reindex(gated.index)
    print(f"\nFigure 11.4: merchant's evidence prevailed in {won.mean():.1%} of cases")
    bands = pd.cut(gated.score, [-0.01, 0.20, 0.45, 0.70, 0.85, 1.0],
                   labels=["< 0.20", "0.20-0.45", "0.45-0.70", "0.70-0.85", "> 0.85"])
    print(won.groupby(bands, observed=True).agg(["size", "mean"])
          .rename(columns={"size": "cases", "mean": "prevailed"})
          .to_string(formatters={"prevailed": "{:.0%}".format}))
    ndocs = cases_df.set_index("case_id").n_documents.reindex(gated.index)
    print(won.groupby(ndocs).agg(["size", "mean"]).rename(
        columns={"size": "cases", "mean": "prevailed"}).rename_axis("documents")
        .to_string(formatters={"prevailed": "{:.0%}".format}))
    print(f"AUC: sufficiency score {auc(won, gated.score):.2f}; "
          f"number of documents {auc(won, ndocs):.2f}")

    # Table 11.7: analyst time (illustrative assumptions)
    auto = (gated.reviewed == 0).sum()
    flagged = gated.reviewed.sum()
    border = (gated.verdict == "borderline").sum()
    manual = n * 20 / 60
    pipe = auto * 1 / 60 + flagged * 3 / 60 + border * 10 / 60
    print(f"\nTable 11.7: analyst time for {n:,} packets")
    print(f"  manual reading: {n:,} x 20 min = {manual:,.1f} h")
    print(f"  pipeline: {auto:,} x 1 min + {flagged:,} x 3 min + {border:,} borderline "
          f"x 10 min = {pipe:,.1f} h ({1 - pipe / manual:.0%} less)")


if __name__ == "__main__":
    main()
