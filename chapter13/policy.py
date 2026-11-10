"""The policy gate (Listing 13.1).

check() decides whether a proposed action may run. It reads the action's
name, the case, the state of the systems of record and the tool registry. It
never reads the model's reasoning, so no reasoning changes its answer.

VERSION is written on every log entry. The refund precondition in gate 1.1
matches a refund on the acquirer reference number (state.refund_in_clearing);
gate 1.0 matched on merchant and amount, which let three look-alike refunds
through in the evaluation (see evaluate.py and the lookalike_refund scenario).
"""
from dataclasses import dataclass

VERSION = "gate-1.1"

NEVER = {"deny_claim", "reverse_provisional_credit", "close_merchant_favour",
         "send_customer_data"}
LIMITS = {"grant_final_credit": 100.00, "file_chargeback": 500.00}
BUDGET = {"tool_calls": 14, "merchant_inquiries": 2, "elapsed_days": 10}


@dataclass
class Verdict:
    allowed: bool
    reason: str
    escalate: bool = False      # end the run and hand the case to a person
    alert: bool = False         # someone should know this was attempted


def check(action, case, state, tools):
    """Decide whether a proposed action may run. Never consults the model."""
    if action.name in NEVER or action.name not in tools:
        return Verdict(False, "boundary", alert=True)
    if state.calls >= BUDGET["tool_calls"] or state.days >= BUDGET["elapsed_days"]:
        return Verdict(False, "budget", escalate=True)
    if (action.name == "send_merchant_inquiry"
            and state.inquiries >= BUDGET["merchant_inquiries"]):
        return Verdict(False, "budget")
    if action.name == "close_refunded" and not state.refund_in_clearing(case.arn,
                                                                    case.amount):
        return Verdict(False, "precondition")
    if action.name in LIMITS:
        if action.name != case.recovery_decision:            # Chapter 10
            return Verdict(False, "decision_mismatch", escalate=True)
        if case.amount > LIMITS[action.name]:
            return Verdict(False, "limit", escalate=True)
    return Verdict(True, "ok")


def allow_all(action, case, state, tools):
    """No gate: the 'rules in the prompt' configuration of evaluate.py."""
    if action.name not in tools:
        return Verdict(False, "unknown tool")
    return Verdict(True, "ok (no gate)")
