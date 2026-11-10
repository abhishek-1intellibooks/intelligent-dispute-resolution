"""The card dispute lifecycle as a table-driven state machine (Listing 3.1).

TRANSITIONS is the lifecycle: each key pairs a state with an event and each
value is the next state. Any pair absent from the table is not allowed, so a
refund out of CHARGEBACK (the double-refund failure in the chapter's case
study) is rejected at the point of entry. CLOCK_DAYS lists the states that
carry a response window; the lengths are illustrative.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

TRANSITIONS = {
    ("SETTLED", "inquiry_received"): "INQUIRY",
    ("SETTLED", "chargeback_received"): "CHARGEBACK",
    ("INQUIRY", "inquiry_answered"): "DEFLECTED",
    ("INQUIRY", "refund_issued"): "DEFLECTED",
    ("INQUIRY", "chargeback_received"): "CHARGEBACK",
    ("CHARGEBACK", "accept"): "LOST",
    ("CHARGEBACK", "represent"): "REPRESENTED",
    ("REPRESENTED", "issuer_accepts"): "WON",
    ("REPRESENTED", "issuer_escalates"): "PRE_ARBITRATION",
    ("PRE_ARBITRATION", "accept"): "LOST",
    ("PRE_ARBITRATION", "contest"): "ARBITRATION",
    ("ARBITRATION", "ruling_merchant"): "WON",
    ("ARBITRATION", "ruling_issuer"): "LOST",
}

CLOCK_DAYS = {"CHARGEBACK": 30, "PRE_ARBITRATION": 30}   # illustrative


@dataclass
class CardDispute:
    case_id: str
    amount: float
    state: str = "SETTLED"
    due: date | None = None
    history: list = field(default_factory=list)

    def apply(self, event, on):
        if self.due and on > self.due:            # window missed: default loss
            self.history.append((on, self.state, "window_missed", "LOST"))
            self.state, self.due = "LOST", None
            return self
        nxt = TRANSITIONS.get((self.state, event))
        if nxt is None:
            raise ValueError(f"{event!r} is not allowed in {self.state}")
        self.history.append((on, self.state, event, nxt))
        self.state = nxt
        days = CLOCK_DAYS.get(nxt)
        self.due = on + timedelta(days=days) if days else None
        return self
