"""Listing 4.2: chapter04/rail_adapters/profiles.py

Three rails declared with one class. ACH_DEBIT is a pull profile; INSTANT and
WIRE share the push-rail transitions PUSH_RECOVERY and differ only in their
clocks and evidence. Durations are illustrative fixed values that mirror the
rules recorded in chapter02/timelines.yaml.

A P2P profile is left as an exercise (Question 3): see p2p_profile() below.
"""

from datetime import timedelta as td

from .base import RailProfile

ACH_DEBIT = RailProfile(
    name="ach_debit", direction="pull",
    transitions={
        ("REPORTED", "return_sent"): "RETURNED",
        ("REPORTED", "claim_denied"): "CLOSED_NO_ERROR",
    },
    clocks={"REPORTED": ("settled", td(days=60))},   # consumer R10/R11
    evidence=("trace_number", "sec_code", "settlement_date",
              "written_statement"),
)

PUSH_RECOVERY = {
    ("REPORTED", "recall_sent"): "RECALL_SENT",
    ("RECALL_SENT", "funds_returned"): "RECOVERED",
    ("RECALL_SENT", "partial_return"): "LOSS_REVIEW",
    ("RECALL_SENT", "request_refused"): "LOSS_REVIEW",
    ("LOSS_REVIEW", "reimburse"): "REIMBURSED",
    ("LOSS_REVIEW", "close_loss"): "CLOSED_LOSS",
}

INSTANT = RailProfile(
    name="instant", direction="push", transitions=PUSH_RECOVERY,
    clocks={"REPORTED": ("entered", td(minutes=30)),
            "RECALL_SENT": ("entered", td(hours=24))},
    evidence=("end_to_end_id", "receiving_bank", "beneficiary_account",
              "payer_statement"),
)

WIRE = RailProfile(
    name="wire", direction="push", transitions=PUSH_RECOVERY,
    clocks={"REPORTED": ("entered", td(minutes=30)),
            "RECALL_SENT": ("entered", td(days=2))},
    evidence=("uetr", "beneficiary_bank", "beneficiary_account",
              "payer_statement"),
)


# ---------------------------------------------------------------------------
# EXERCISE (Chapter 4, Question 3): the P2P profile.
#
# Write a P2P profile for a network that reimburses certain impersonation
# scams. Start from PUSH_RECOVERY (a P2P send is a push payment), add the
# transition(s) the network's reimbursement policy needs, for example a
# scheme-reimbursement path out of LOSS_REVIEW, choose its clocks and list
# the evidence fields the profile requires (transfer id, funding rail,
# recipient handle, payer statement, ...).
#
# This stub is deliberately NOT implemented; demo.py does not use it.
# ---------------------------------------------------------------------------
def p2p_profile() -> RailProfile:
    """EXERCISE: return a RailProfile for a P2P network. Not implemented."""
    raise NotImplementedError(
        "Exercise (Chapter 4, Question 3): declare the P2P profile here.")
