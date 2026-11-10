"""Drive the card dispute state machine through three paths and one illegal event (Listing 3.2)."""
from datetime import date
from card_state_machine import CardDispute

paths = {
    "deflected": [("inquiry_received", date(2026, 3, 2)), ("refund_issued", date(2026, 3, 4))],
    "contested": [("chargeback_received", date(2026, 3, 20)), ("represent", date(2026, 4, 10)),
                  ("issuer_accepts", date(2026, 4, 28))],
    "missed": [("chargeback_received", date(2026, 3, 20)), ("represent", date(2026, 4, 25))],
}
for name, events in paths.items():
    case = CardDispute(case_id=name, amount=186.00)
    for event, on in events:
        case.apply(event, on)
    print(f"{name:10s} -> {case.state:10s} due={case.due}")
try:
    CardDispute("bad", 186.0).apply("represent", date(2026, 3, 2))
except ValueError as err:
    print("rejected:", err)
