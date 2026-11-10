"""Assemble the context pack: every statement the model may make, each with an ID.

Listing 12.1 of the book.
"""
import re

from rules import search_rules

REDACT = [(re.compile(r"\b\d{12,19}\b"), "[card number]"),
          (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[email]"),
          (re.compile(r"\+?\d[\d\s().-]{8,}\d"), "[phone]")]


def redact(text):
    for pattern, label in REDACT:
        text = pattern.sub(label, text)
    return text


def context_pack(case, evidence, decision, k=3):
    """Every statement the model may make, each with an ID it must cite."""
    items = {
        "C1": ("claim", f"{case.card_type} card, {case.amount_display}, "
                        f"filed {case.claimed_on:%d %B %Y}"),
        "C2": ("merchant", case.merchant_name),
        "C3": ("clock", f"day {case.days_elapsed} of {case.days_allowed}"),
        "N1": ("narrative (customer's words)", redact(case.narrative)),
    }
    for i, fact in enumerate(evidence["facts"], start=1):
        items[f"F{i}"] = (fact["fact"], fact["display"])
    items["D1"] = ("sufficiency", f"{evidence['score']:.2f} {evidence['verdict']}")
    items["D2"] = ("recovery", f"{decision['decision']}: {decision['reason']}")
    for rule in search_rules(case.reason_text, reason=case.reason_family,
                             network=case.network, on=case.opened_on, k=k):
        items[rule.id] = ("rule", rule.text)
    return items


def render_pack(items):
    return "\n".join(f"[{key}] {name}: {value}" for key, (name, value) in items.items())


def render_notes(items):
    """The same facts as plain case notes, with no IDs and no rules.

    This is what the prompt-only configuration of evaluate.py gives the model.
    """
    return "\n".join(f"{name}: {value}" for key, (name, value) in items.items()
                     if name != "rule")
