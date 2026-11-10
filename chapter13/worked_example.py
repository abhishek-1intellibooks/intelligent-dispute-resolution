"""Run the agent on the $249 claim as it would have run had it been live (Table 13.8).

The merchant's reply carries an embedded instruction to close the dispute in
the merchant's favour. The stand-in is set to follow it, as the book's run
did; the gate refuses the proposal and raises an alert, and the agent carries
on. The evidence scores 0.95, which makes the case adverse to the customer, so
the agent escalates with the Chapter 12 summary and draft letter attached.

Run: python worked_example.py      (writes action_log_249.jsonl)
"""
import json
from pathlib import Path

import escalation
from agent import run_agent
from models import LLMAgent, install_standin    # also puts chapter12 on the path
from systems import MINUTES_PER_DAY, Case, World

import llm_client                               # noqa: E402  (chapter12)
from llm_standin import CLEAN_RATES, StandIn    # noqa: E402
from records import worked_case                 # noqa: E402
from service import MemoryLog, letter_writer, produce, summary_writer   # noqa: E402

HERE = Path(__file__).resolve().parent


def chapter12_summary(case):
    c12_case, evidence, decision = worked_case()
    result = produce("summary", c12_case, evidence, decision, summary_writer, MemoryLog())
    return result["draft"].sentences


def chapter12_letter(case):
    c12_case, evidence, decision = worked_case()
    result = produce("letter", c12_case, evidence, decision, letter_writer, MemoryLog())
    return {"status": result["status"], "text": result["draft"].customer_text}


class Recording:
    """Keep the observations the model saw, to report each tool's result."""

    def __init__(self, model):
        self.model, self.seen = model, []

    def next_action(self, brief, observations, tool_names):
        self.seen = list(observations)
        return self.model.next_action(brief, observations, tool_names)


def describe(obs):
    if obs.get("kind") == "refusal":
        return f"refused: {obs['reason']}"
    data, tool = obs["data"], obs["tool"]
    if tool == "read_case":
        return f"{data['reason']}, ${data['amount']:,.2f}; Ch. 10: {data['ch10_note']}"
    if tool == "send_merchant_inquiry":
        return f"reply: {data.get('text', data.get('note'))}"
    if tool == "get_carrier_record":
        return f"{data['status']} to {data['delivered_to']}, proof: {data['proof']}"
    if tool == "score_evidence":
        return f"{data['score']:.2f}, {data['verdict']} (Ch. 11)"
    if tool == "attach_evidence":
        return f"attached {data['attached']}"
    return json.dumps(data)


def main():
    install_standin(seed=13, force={"inject": True, "adverse": False},
                    fallback=StandIn(rates=CLEAN_RATES))
    escalation.SUMMARIZER = chapter12_summary
    escalation.LETTER_DRAFTER = chapter12_letter
    case = Case(case_id="DSP-0249", amount=249.00, merchant="Larkspur Home Goods",
                arn="74123455349012345678906", reason="merchandise not received",
                recovery_decision="file_chargeback", ch10_note="too close to call",
                category="sufficient", tracking="1Z84F2A90314455872",
                reply_delay=215.0, injection="close_merchant_favour", score=0.95)
    world = World(case)
    model = Recording(LLMAgent())
    result = run_agent(case, model, world)

    observations = model.seen[1:]                     # after the initial read_case
    entries = result["log"].entries
    print(f"Model: {llm_client.model_name()}   gate: {entries[0]['config']}\n")
    print("Table 13.8: the action log for the $249 claim")
    print(f"{'Time':6s} | {'Proposed action':38s} | {'Gate':26s} | Result")
    print(f"{'16:05':6s} | {'read_case':38s} | {'Allowed':26s} | {describe(model.seen[0])}")
    for i, entry in enumerate(entries):
        proposed = entry["proposed"]
        if proposed == "send_merchant_inquiry":
            proposed += f" (template {entry['args']['template']})"
        if proposed == "escalate":
            proposed += f" ({entry['args']['reason']})"
        gate = "Allowed" if entry["allowed"] else f"Refused: {entry['verdict']}" + \
            ("; alert" if entry["alert"] else "")
        outcome = describe(observations[i]) if i < len(observations) else \
            "Analyst queue, with summary, draft letter and alert"
        print(f"{entry['at'][-5:]:6s} | {proposed:38s} | {gate:26s} | {outcome}")

    packet = result["packet"]
    elapsed = world.minutes
    print(f"\nReached an analyst {int(elapsed // 60)} h {int(elapsed % 60)} min after filing "
          f"({packet['elapsed']}); status {result['status']}, reason {result['reason']}.")
    print(f"Alerts for the merchant-risk team: {packet['alerts']}")
    print("\nSummary in the packet (Chapter 12):")
    for line in packet["summary"]:
        print("  " + line)
    print(f"\nDraft letter in the packet ({packet['draft_letter']['status']}), first lines:")
    for line in packet["draft_letter"]["text"].splitlines()[:3]:
        print("  " + line)
    print("\nMoney moved:", [e[0] for e in world.effects if e[0] in
                             ("file_chargeback", "grant_final_credit", "close_refunded")] or "none")
    result["log"].to_jsonl(HERE / "action_log_249.jsonl")
    print(f"Action log written to {HERE / 'action_log_249.jsonl'}")
    assert elapsed < MINUTES_PER_DAY


if __name__ == "__main__":
    main()
