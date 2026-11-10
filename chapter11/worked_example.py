"""Run the evidence pipeline on the $249 claim (Table 11.8).

The merchant's response holds three files: an order confirmation exported as a
native PDF, an email with the carrier tracking number typed into its body, and
a phone photograph of the proof-of-delivery slip. The photograph appears to
say Apartment 2; the ship-to address is Apartment 12. The pipeline rejects the
low-confidence reading and uses the tracking number to retrieve the carrier's
own record.
"""
from datetime import date

from evidence_pipeline import Case, GATE, build_evidence, choose
from extract import Fact, normalize_tracking, read_fact

CASE = Case(case_id="WX-249", reason="not_received", opened_on=date(2025, 12, 8),
            claimed_on=date(2025, 12, 8), expected_on=date(2025, 11, 29),
            amount_cents=24900, currency="USD")


def conf(text, weak=None, at=1.0):
    """Per-character confidence (0-100), with one weak span if given."""
    c = [round(at * 100)] * len(text)
    if weak:
        start = text.index(weak)
        c[start:start + len(weak)] = [58] * len(weak)
    return c


def merchant_files():
    order = "WX-249-D1"                          # order confirmation, native PDF
    pod = "WX-249-D3"                            # proof of delivery, phone photo
    ship = "41 Harlow Street, Apt 12, Cleveland, OH 44107"
    slip = "41 HARLOW ST APT 2, CLEVELAND, OH 44107"
    slip_date = "11/28/2025 14:12"
    return {
        "ship_to": [read_fact("ship_to", ship, conf(ship), order, 1, "native")],
        "amount": [read_fact("amount", "$249.00", conf("$249.00"), order, 1, "native")],
        "delivered_to": [read_fact("delivered_to", slip, conf(slip, weak="2,", at=0.93),
                                   pod, 1, "photo")],
        "delivered_on": [read_fact("delivered_on", slip_date, [93, 91, 72, 88, 90, 93,
                                   92, 70, 91, 90, 93, 92, 90, 91, 93, 92],
                                   pod, 1, "photo", "us")],
        "attested": [read_fact("attested", "Photo on file", conf("Photo on file", at=0.95),
                               pod, 1, "photo")],
    }


def retrieve_carrier_record(tracking):
    """The carrier's own record, fetched by tracking number (simulated API)."""
    doc = f"carrier:{tracking}"
    to = "41 HARLOW ST #12, CLEVELAND, OH 44107"
    on = "2025-11-28T14:12"
    return {"delivered_to": read_fact("delivered_to", to, conf(to), doc, 1, "api"),
            "delivered_on": read_fact("delivered_on", on, conf(on), doc, 1, "api", "iso")}


def no_review(case, name, readings):
    raise AssertionError(f"{name} should not need a person in this example")


def show_address(a):
    return f"{a['number']} {a['street']}, unit {a['unit']}, {a['zip']}"


def main():
    readings = merchant_files()
    email = "Hi, your parcel was delivered. Tracking number NP 7731 0429 8815."
    tracking = normalize_tracking(email.split("Tracking number")[1])
    print(f"Tracking number read from the email: {tracking}")
    for name, fact in retrieve_carrier_record(tracking).items():
        readings[name].append(fact)

    first = readings["delivered_to"][0]
    _, how = choose([first])
    print(f"First reading of delivered_to: {show_address(first.value)} from the "
          f"phone photograph, confidence {first.confidence:.2f} -> "
          f"{'accepted' if how == 'auto' else 'below the gate of %.2f; not used' % GATE}")

    record = build_evidence(CASE, readings, no_review)
    print("\nTable 11.8: the evidence record for the $249 claim")
    for t in record["facts"]:
        v = t["value"]
        v = show_address(v) if isinstance(v, dict) else (
            f"${v / 100:,.2f}" if t["fact"] == "amount" else v)
        print(f"  {t['fact']:<13} {str(v):<30} {t['channel']:<6} doc {t['doc']:<24} "
              f"confidence {t['confidence']:.2f}  ({t['how']})")
    print(f"  Judgment: score {record['score']:.2f}, {record['verdict']}; "
          f"rule set {record['rules']}; gaps: {record['gaps'] or 'none'}")

    # Had the photograph been trusted, with no carrier record to fall back on
    naive = build_evidence(CASE, merchant_files(), no_review, gate=0.0)
    print(f"\nHad the photograph been trusted: score {naive['score']:.2f}, "
          f"{naive['verdict']}; gaps: {naive['gaps']}")


if __name__ == "__main__":
    main()
