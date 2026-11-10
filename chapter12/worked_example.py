"""Run the service on the $249 claim (Table 12.8).

Three documents: the case summary, the customer letter and, for illustration
from the merchant's seat, the representment narrative. The stand-in is set to
replay the run the book describes: the first letter repeats the opening
example's error ('you received your parcel') and the checker stops it; the
second passes, and the analyst approves it with one edit.

Run: python worked_example.py      (writes generation_log.jsonl)
"""
from pathlib import Path

import llm_client
from context import context_pack
from draft import chronology
from llm_standin import CLEAN_RATES, StandIn
from records import worked_case
from service import (JsonlLog, approve, letter_writer, produce, representment_writer,
                     summary_writer)

HERE = Path(__file__).resolve().parent
MAILROOM = ("If your building has a shared mailroom or a front desk, please check there and "
            "with your neighbours as well.")


def main():
    if llm_client.provider() == "offline":
        llm_client.use_offline(StandIn(rates=CLEAN_RATES, script={"letter": [["overclaim"], []]}))
    case, evidence, decision = worked_case()
    log = JsonlLog(HERE / "generation_log.jsonl")
    rows = []

    summary = produce("summary", case, evidence, decision, summary_writer, log)
    print("CASE SUMMARY", f"({summary['status']})")
    print(summary["draft"].text, "\n")
    rows.append(("Case summary", f"{len(summary['draft'].sentences)} sentences, "
                 f"flags {summary['flags'] or 'none'}", summary["status"]))

    letter = produce("letter", case, evidence, decision, letter_writer, log)
    attempts = [e for e in log_entries(log) if e.get("kind") == "letter"]
    for entry in attempts:
        print(f"LETTER attempt {entry['attempt']}: flags {entry['flags'] or 'none'}")
    final = letter["draft"].customer_text.replace(
        "You may ask us", MAILROOM + "\nYou may ask us")
    approved = approve(case, letter, "analyst.j.okafor", final, log)
    print("\nLETTER AS APPROVED (one sentence added by the analyst):")
    print(approved, "\n")
    rows.append(("Customer letter", "; ".join(f"attempt {e['attempt']}: "
                                              f"{[k for k, _ in e['flags']] or 'passed'}"
                                              for e in attempts),
                 f"{letter['status']}, approved with one edit"))

    narrative = produce("representment", case, evidence, decision, representment_writer, log)
    draft = narrative["draft"]
    print("REPRESENTMENT NARRATIVE (merchant's seat; illustration only)")
    print("Template written by the model:")
    print(draft.template)
    print("\nRendered from the record:")
    print(draft.text)
    placeholders = draft.template.count("{{")
    print("\nChronology built by code:")
    for value, name in chronology(context_pack(case, evidence, decision)):
        print(f"  {value:28s} {name}")
    rows.append(("Representment narrative", f"{placeholders} placeholders rendered, "
                 f"flags {narrative['flags'] or 'none'}", "illustration only"))

    print("\nTable 12.8: the service on the $249 claim")
    for doc, what, outcome in rows:
        print(f"  {doc:24s} | {what:58s} | {outcome}")
    print(f"\nGeneration log: {HERE / 'generation_log.jsonl'}")


def log_entries(log):
    import json
    with open(log.path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


if __name__ == "__main__":
    main()
