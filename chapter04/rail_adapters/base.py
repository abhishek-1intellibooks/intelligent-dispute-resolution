"""Listing 4.1: chapter04/rail_adapters/base.py

The shared part of the rail adapter pattern. A RailProfile declares a rail's
direction, state machine, clocks and evidence schema (Table 4.5); a RailCase
holds one claim and can be driven by any profile.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RailProfile:
    name: str
    direction: str              # "pull" (debit) or "push" (credit)
    transitions: dict           # (state, event) -> next state
    clocks: dict                # state -> (anchor, timedelta)
    evidence: tuple             # fields a case must hold on this rail


@dataclass
class RailCase:
    case_id: str
    profile: RailProfile
    amount: float
    settled_at: datetime
    reported_at: datetime
    state: str = "REPORTED"
    due: datetime | None = None
    history: list = field(default_factory=list)

    def __post_init__(self):
        self._set_clock(self.reported_at)

    def _set_clock(self, entered):
        anchor, span = self.profile.clocks.get(self.state, (None, None))
        base = self.settled_at if anchor == "settled" else entered
        self.due = base + span if span else None

    def apply(self, event, at):
        nxt = self.profile.transitions.get((self.state, event))
        if nxt is None:
            raise ValueError(f"{event!r} not allowed in {self.state} "
                             f"on rail {self.profile.name!r}")
        timing = "late" if self.due and at > self.due else "on_time"
        self.history.append((at, self.state, event, nxt, timing))
        self.state = nxt
        self._set_clock(at)
        return self

    def missing_evidence(self, record):
        return [f for f in self.profile.evidence if not record.get(f)]
