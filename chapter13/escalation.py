"""Build the packet a person receives when the agent hands a case over (Table 13.4).

Every escalation carries a case summary, the action log, the specific reason
and any alerts. SUMMARIZER and LETTER_DRAFTER can be set to a function that writes the Chapter 12
summary (worked_example.py does this); by default the summary is assembled
from the case record by code.
"""
import systems

SUMMARIZER = None
LETTER_DRAFTER = None       # set to attach the Chapter 12 draft letter to adverse escalations

TRIGGERS = {
    "adverse_to_customer": ("Outcome adverse to the customer",
                            "Summary, evidence record, draft letter"),
    "limit": ("Action over a limit", "The proposed action, ready to approve"),
    "decision_mismatch": ("Disagreement with Chapter 10", "Both choices and the expected value"),
    "budget": ("Budget exhausted", "The log, flagged as a possible loop"),
    "forbidden": ("Forbidden action proposed", "The log and a security alert"),
    "precondition_never_met": ("Precondition never met",
                               "The merchant's claim and the clearing check"),
}


def escalate(case, log, reason, alerts):
    """Hand the case to a person with everything they need to act on it."""
    world = systems.active()
    systems.queue.escalate(case, reason)
    trigger, receives = TRIGGERS.get(reason, ("Agent judgement", "The log and the summary"))
    entries = list(log)
    packet = {
        "case_id": case.case_id,
        "reason": reason,
        "trigger": trigger,
        "person_receives": receives,
        "summary": SUMMARIZER(case) if SUMMARIZER else case.summary_lines(),
        "action_log": entries,
        "alerts": list(alerts),
        "security_alert": bool(alerts),
        "elapsed": systems.clock_display(world.minutes),
    }
    if reason == "adverse_to_customer" and LETTER_DRAFTER:
        packet["draft_letter"] = LETTER_DRAFTER(case)
    if reason in ("limit", "decision_mismatch") and entries:
        packet["proposed_action"] = entries[-1]["proposed"]
        packet["chapter10_decision"] = case.recovery_decision
    return {"status": "escalated", "ending": "escalate", "reason": reason,
            "packet": packet, "log": log, "alerts": alerts}
