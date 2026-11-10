"""Load the case, evidence and decision records from cases.jsonl.

The Case object carries the fields context.py reads: the case record of
Chapter 8, the regulatory clock position of Chapter 2 (days_elapsed and
days_allowed, computed when the record was assembled, never by the model),
and the network and reason family used to retrieve rules.
"""
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases.jsonl"
WORKED_CASE_ID = "DSP-0249"


@dataclass(frozen=True)
class Case:
    case_id: str
    card_type: str
    amount: float
    merchant_name: str
    claimed_on: date
    opened_on: date
    days_elapsed: int
    days_allowed: int
    narrative: str
    reason_text: str
    reason_family: str
    network: str

    @property
    def amount_display(self):
        return f"${self.amount:,.2f}"


def _case(row):
    return Case(row["case_id"], row["card_type"], float(row["amount"]), row["merchant_name"],
                date.fromisoformat(row["claimed_on"]), date.fromisoformat(row["opened_on"]),
                int(row["days_elapsed"]), int(row["days_allowed"]), row["narrative"],
                row["reason_text"], row["reason_family"], row["network"])


def load_cases(path=CASES):
    """Yield (case, evidence, decision) for every record in cases.jsonl."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            yield _case(row), row["evidence"], row["decision"]


def worked_case(path=CASES):
    """The $249 claim of the worked example."""
    for case, evidence, decision in load_cases(path):
        if case.case_id == WORKED_CASE_ID:
            return case, evidence, decision
    raise LookupError(f"{WORKED_CASE_ID} not in {path}; run make_data.py")
