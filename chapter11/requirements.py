"""Evidence requirements as data: a versioned rule set with an effective date.

Listing 11.1. Each requirement names the fact it concerns, its weight in the
sufficiency score, the function in match.py that tests it and the request to
make when the test fails. rules_for picks the rule set in force when the case
was opened, not today's.
"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Requirement:
    fact: str       # the fact that must be shown
    weight: float   # its share of the sufficiency score
    check: str      # the function in match.py that tests it
    gap: str        # what to ask for when the check fails


NOT_RECEIVED = {
    "version": "nr-2025.2",
    "effective": date(2025, 4, 1),
    "requirements": [
        Requirement("delivered_to", 0.45, "address_match",
                    "proof of delivery to the address the cardholder gave"),
        Requirement("amount", 0.10, "amount_match",
                    "order record showing the disputed amount"),
        Requirement("delivered_on", 0.20, "on_time",
                    "carrier record with a delivery date"),
        Requirement("attested", 0.15, "signature_or_photo",
                    "signature or delivery photograph"),
        Requirement("independent", 0.10, "from_carrier",
                    "the carrier's own record, not a copy"),
    ],
    "veto": {"address_contradicted": 0.20},   # caps the score
    "verdict": {"sufficient": 0.70, "borderline": 0.45},
}

# The rule set it replaced, kept so that older cases are judged by the rules
# that applied to them (illustrative: a stricter borderline line, no veto).
NOT_RECEIVED_2024 = {
    "version": "nr-2024.1",
    "effective": date(2024, 4, 1),
    "requirements": NOT_RECEIVED["requirements"],
    "veto": {"address_contradicted": 1.00},
    "verdict": {"sufficient": 0.70, "borderline": 0.50},
}

RULE_SETS = {"not_received": [NOT_RECEIVED_2024, NOT_RECEIVED]}


def rules_for(reason, opened_on, rule_sets):
    """The rule set in force when the case was opened, not today's."""
    live = [r for r in rule_sets[reason] if r["effective"] <= opened_on]
    return max(live, key=lambda r: r["effective"])
