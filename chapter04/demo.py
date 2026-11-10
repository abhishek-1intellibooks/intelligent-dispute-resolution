"""Listing 4.3: chapter04/demo.py: three claims and two checks."""

from datetime import datetime as dt
from rail_adapters.base import RailCase
from rail_adapters.profiles import ACH_DEBIT, INSTANT, WIRE

SETTLED, REPORTED = dt(2026, 3, 9, 10), dt(2026, 3, 9, 14)

runs = {
    "ach-1": (ACH_DEBIT, 420.0, dt(2026, 2, 2), dt(2026, 3, 20, 9),
              [("return_sent", dt(2026, 3, 23, 11))]),
    "rtp-1": (INSTANT, 64000.0, SETTLED, REPORTED,
              [("recall_sent", dt(2026, 3, 9, 14, 20)),
               ("partial_return", dt(2026, 3, 10, 9)),
               ("close_loss", dt(2026, 3, 12, 12))]),
    "wire-1": (WIRE, 64000.0, SETTLED, REPORTED,
               [("recall_sent", dt(2026, 3, 10, 9)),
                ("request_refused", dt(2026, 3, 11, 12))]),
}

for case_id, (profile, amount, settled, reported, events) in runs.items():
    case = RailCase(case_id, profile, amount, settled, reported)
    for event, at in events:
        case.apply(event, at)
    timing = [h[4] for h in case.history]
    print(f"{case_id:7s} {profile.direction:5s} -> {case.state:12s} {timing}")

probe = RailCase("rtp-2", INSTANT, 64000.0, SETTLED, REPORTED)
print("missing:", probe.missing_evidence(
    {"end_to_end_id": "E2E-77", "receiving_bank": "RB-021"}))
try:
    probe.apply("chargeback_received", dt(2026, 3, 9, 15))
except ValueError as err:
    print("rejected:", err)
