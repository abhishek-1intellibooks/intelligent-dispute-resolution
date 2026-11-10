"""Evaluate retrieval and the summarizer (Figure 12.3, Tables 12.6 and 12.7).

1. Retrieval: 138 questions, each a paraphrase of a passage in force, answered
   by similarity search over the whole library and by search after filtering
   on reason family, network and edition.
2. Summaries: 1,200 not-received cases in three configurations, prompt only,
   grounded with citations, and grounded with facts slotted. In the grounded
   configurations a flagged draft is regenerated once and, if flagged again,
   sent to a person, who corrects it.

The model is the deterministic stand-in (llm_standin.py), whose record of its
own mistakes is the ground truth; the retrieval, the checker and the service
are the real code. With a hosted model configured the checker still runs, but
there is no ground truth, so only the flag and hand-off rates are reported.

Run: python evaluate.py      (writes evaluation_results.json and figures/)
"""
import json
from collections import Counter
from pathlib import Path

import llm_client
from context import context_pack, render_notes
from guardrails import check
from llm_standin import ERROR_TYPES, StandIn
from records import load_cases
from rules import search_rules
from service import MemoryLog, produce, slotted_summary_writer, summary_writer
from summarize import sentences, summarize_notes

HERE = Path(__file__).resolve().parent


def evaluate_retrieval():
    questions = [json.loads(line) for line in open(HERE / "rules_questions.jsonl", encoding="utf-8")]
    hits = Counter()
    for q in questions:
        plain = [r.id for r in search_rules(q["question"], k=3)]
        keyed = [r.id for r in search_rules(q["question"], reason=q["reason_family"],
                                            network=q["network"], on=q["on"], k=3)]
        hits["similarity_top1"] += plain[0] == q["target"]
        hits["similarity_top3"] += q["target"] in plain
        hits["filtered_top1"] += keyed[0] == q["target"]
        hits["filtered_top3"] += q["target"] in keyed
    n = len(questions)
    return {"questions": n, **{k: round(v / n, 3) for k, v in hits.items()}}


def run_grounded(cases, writer):
    rows = []
    for case, evidence, decision in cases:
        drafts = []

        def recording_writer(items):
            draft = writer(items)
            drafts.append((draft, check(draft.sentences, items) + draft.structure_flags))
            return draft

        result = produce("summary", case, evidence, decision, recording_writer, MemoryLog())
        first, first_flags = drafts[0]
        truth_known = first.truth is not None
        final_errors = bool(drafts[-1][0].truth and drafts[-1][0].truth["errors"])
        rows.append({
            "error": truth_known and bool(first.truth["errors"]),
            "types": set(first.truth["errors"]) if truth_known else set(),
            "flagged": bool(first_flags),
            "to_person": result["status"] == "needs_person",
            # a person corrects every draft sent to them
            "released_error": result["status"] == "ready_for_approval" and final_errors,
        })
    return rows


def run_prompt_only(cases):
    rows = []
    for case, evidence, decision in cases:
        items = context_pack(case, evidence, decision)
        out = summarize_notes(render_notes(items))
        sentences(out)
        truth = llm_client.offline_model().last if llm_client.provider() == "offline" else None
        errors = bool(truth and truth["errors"])
        rows.append({"error": errors, "types": set(truth["errors"]) if truth else set(),
                     "flagged": None, "to_person": False, "released_error": errors})
    return rows


def rates(rows, checkable=True):
    n = len(rows)
    pct = lambda k: round(100 * sum(r[k] for r in rows) / n, 1)
    out = {"drafts": n, "with_error_pct": pct("error"), "released_with_error_pct": pct("released_error")}
    if checkable:
        out["flagged_pct"] = pct("flagged")
        out["false_alarm_pct"] = round(100 * sum(r["flagged"] and not r["error"] for r in rows) / n, 1)
        out["sent_to_person_pct"] = pct("to_person")
    return out


def by_type(rows):
    table = {}
    for kind in ERROR_TYPES:
        with_kind = [r for r in rows if kind in r["types"]]
        flagged = sum(r["flagged"] for r in with_kind)
        table[kind] = {"drafts": len(with_kind),
                       "flagged_pct": round(100 * flagged / len(with_kind), 1) if with_kind else None}
    return table


def figures(results):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    out = HERE / "figures"
    out.mkdir(exist_ok=True)
    r = results["retrieval"]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    labels = ["Similarity only", "Filter, then search"]
    ax.bar([0, 1], [r["similarity_top1"] * 100, r["filtered_top1"] * 100], width=0.35, label="Top 1")
    ax.bar([0.38, 1.38], [r["similarity_top3"] * 100, r["filtered_top3"] * 100], width=0.35, label="Top 3")
    ax.set_xticks([0.19, 1.19], labels)
    ax.set_ylabel("Right passage found (%)")
    ax.set_ylim(0, 105)
    ax.legend(frameon=False)
    ax.set_title("Figure 12.3: Retrieving the right rule passage")
    fig.tight_layout()
    fig.savefig(out / "fig12_3_retrieval.png", dpi=150)
    plt.close(fig)

    s = results["summaries"]
    names = ["Prompt only", "Grounded, cited", "Grounded, slotted"]
    keys = ["prompt_only", "grounded_cited", "grounded_slotted"]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    for i, (metric, label) in enumerate([("with_error_pct", "Drafts with an error"),
                                         ("sent_to_person_pct", "Sent to a person"),
                                         ("released_with_error_pct", "Released with an error")]):
        ax.bar([j + 0.27 * i for j in range(3)], [s[k].get(metric, 0) for k in keys], width=0.26,
               label=label)
    ax.set_xticks([j + 0.27 for j in range(3)], names)
    ax.set_ylabel("% of 1,200 drafts")
    ax.legend(frameon=False)
    ax.set_title("Figure 12.5: Errors, human effort and residual errors")
    fig.tight_layout()
    fig.savefig(out / "fig12_5_configurations.png", dpi=150)
    plt.close(fig)


def main():
    if llm_client.provider() == "offline":
        llm_client.use_offline(StandIn(seed=12))
    cases = list(load_cases())
    retrieval = evaluate_retrieval()
    print(f"Retrieval on {retrieval['questions']} questions")
    print(f"  similarity only : top-1 {retrieval['similarity_top1']:.0%}, top-3 {retrieval['similarity_top3']:.0%}")
    print(f"  filter + search : top-1 {retrieval['filtered_top1']:.0%}, top-3 {retrieval['filtered_top3']:.0%}")

    prompt_rows = run_prompt_only(cases)
    cited_rows = run_grounded(cases, summary_writer)
    slotted_rows = run_grounded(cases, slotted_summary_writer)
    summaries = {"prompt_only": rates(prompt_rows, checkable=False),
                 "grounded_cited": rates(cited_rows), "grounded_slotted": rates(slotted_rows)}
    errors_by_type = by_type(cited_rows + slotted_rows)

    print(f"\nTable 12.6: three ways of producing {len(cases):,} case summaries")
    print(f"{'Measure':44s}{'Prompt only':>13s}{'Cited':>9s}{'Slotted':>9s}")
    rows = [("Drafts containing an error", "with_error_pct"),
            ("Drafts flagged by the checker", "flagged_pct"),
            ("Clean drafts flagged (false alarms)", "false_alarm_pct"),
            ("Drafts sent to a person after one regeneration", "sent_to_person_pct"),
            ("Drafts released with an error", "released_with_error_pct")]
    for label, key in rows:
        cells = []
        for config in ("prompt_only", "grounded_cited", "grounded_slotted"):
            v = summaries[config].get(key)
            cells.append("-" if v is None else f"{v:.1f}%")
        print(f"{label:44s}{cells[0]:>13s}{cells[1]:>9s}{cells[2]:>9s}")

    print(f"\nTable 12.7: drafts flagged by type of error "
          f"(grounded configurations, {len(cited_rows) + len(slotted_rows):,} drafts)")
    for kind, row in sorted(errors_by_type.items(), key=lambda kv: -(kv[1]["flagged_pct"] or 0)):
        print(f"  {kind:20s}{row['drafts']:6d}  flagged {row['flagged_pct']}%")

    results = {"model": llm_client.model_name(), "retrieval": retrieval,
               "summaries": summaries, "errors_by_type": errors_by_type}
    (HERE / "evaluation_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    figures(results)
    print("\nWrote evaluation_results.json and figures/")


if __name__ == "__main__":
    main()
