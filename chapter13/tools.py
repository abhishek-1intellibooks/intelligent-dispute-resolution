"""The agent's tool registry (Listing 13.2).

Ten narrow tools over the simulated systems of systems.py. Each declares its
effect, so that the gate can apply the right rule without knowing its
internals; each tool that changes something is idempotent, keyed on the case
and the call; and every result comes back labelled as an observation.

There is no tool to deny a claim, reverse provisional credit, close a case in
the merchant's favour or send free text. UNRESTRICTED lists those powers only
so that evaluate.py can measure a configuration in which the rules live in
the prompt alone; run_agent never sees them unless it is handed them.
"""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable

from systems import (carriers, case_store, clearing, evidence_pipeline, ledger, merchant_inbox,
                     network, queue, unrestricted)


@dataclass(frozen=True)
class Tool:
    effect: str                     # read, write, external, money, handoff
    fn: Callable
    args: dict = field(default_factory=dict)
    idempotent: bool = False


TOOLS = {
    "read_case":             Tool("read", case_store.get),
    "get_carrier_record":    Tool("read", carriers.lookup, {"tracking": str}),
    "get_clearing_refunds":  Tool("read", clearing.refunds_for, {"arn": str}),
    "score_evidence":        Tool("read", evidence_pipeline.build),
    "send_merchant_inquiry": Tool("external", merchant_inbox.send_template,
                                  {"template": str}, idempotent=True),
    "attach_evidence":       Tool("write", case_store.attach, {"doc_id": str}, True),
    "close_refunded":        Tool("money", case_store.close_refunded, {}, True),
    "grant_final_credit":    Tool("money", ledger.make_credit_final, {}, True),
    "file_chargeback":       Tool("money", network.file_chargeback, {}, True),
    "escalate":              Tool("handoff", queue.escalate, {"reason": str}),
}

UNRESTRICTED = {
    "deny_claim":                 Tool("decision", unrestricted.deny_claim),
    "close_merchant_favour":      Tool("decision", unrestricted.close_merchant_favour),
    "reverse_provisional_credit": Tool("money", unrestricted.reverse_provisional_credit),
    "send_customer_data":         Tool("external", unrestricted.send_customer_data),
}


@dataclass
class Action:
    """A proposal from the model: a tool name, its arguments and a stated reason.

    The reason is logged for the person who reviews the run; the gate never reads it.
    """
    name: str
    args: dict = field(default_factory=dict)
    reason: str = ""

    def args_hash(self):
        return hashlib.sha256(json.dumps(self.args, sort_keys=True).encode()).hexdigest()[:12]


def call(name, args, case, key, done, registry=None):
    tool = (registry or TOOLS)[name]
    for arg, kind in tool.args.items():
        if not isinstance(args.get(arg), kind):
            raise TypeError(f"{name}: {arg} must be {kind.__name__}")
    if tool.idempotent and key in done:
        return done[key]                       # the same call twice does it once
    result = {"tool": name, "kind": "observation", "data": tool.fn(case, **args)}
    if tool.idempotent:
        done[key] = result
    return result
