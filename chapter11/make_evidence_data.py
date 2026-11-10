"""Generate evidence_packets/: a synthetic year of 4,000 not-received disputes.

Every merchant in the data responded with documents. Each packet holds an order
record and, depending on the merchant, a carrier record, a proof of delivery
(POD), an invoice and some correspondence or policy pages. Documents arrive
through five channels, in order of trust:

    api         carrier API response or order-system export (structured, exact)
    native      native PDF (text carried as characters, exact)
    screenshot  image of rendered text, clean but sometimes cropped
    clean_scan  scanned paper
    photo       phone photograph: skew, glare, shadow, blur

No OCR engine is needed. The generator simulates OCR at the character level:
each image channel has its own rate of substitutions (mostly the classic
confusions such as 0/O, 1/l, 5/S, 8/B, 2/Z), deletions and insertions, and
every character gets a recognition confidence, lower on average for wrong
characters but sometimes confidently wrong.

Files written (all CSV, together a few megabytes):

    cases.csv      the case record the issuer holds (Chapter 8): amounts, dates
    documents.csv  one row per document: type, channel, pages, SHA-256 of content
    readings.csv   23,860 field readings: raw OCR text, per-character confidence
                   (0-100), the true text, document, page and channel
    pages.csv      the text of every image or PDF page, for classify_pages.py
    truth.csv      simulator only: what really happened and whether the
                   merchant's evidence prevailed. Never used by the pipeline
                   except to measure it.

All data are synthetic and every result is illustrative.
"""
import hashlib
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "evidence_packets"
SEED = 11
N_CASES = 4000
N_CARRIER, N_CARRIER_API = 3000, 1800   # API records also report the attestation
N_POD, N_INVOICE = 2000, 1030           # 8,000 + 7,800 + 6,000 + 2,060 = 23,860
START = date(2025, 4, 1)                           # a year of cases, Apr-Mar

CHANNEL_MIX = {
    "order_record": (["api", "native", "screenshot"], [0.35, 0.40, 0.25]),
    "carrier_record": (["api", "screenshot"], [0.60, 0.40]),   # exactly 1,800 / 1,200
    "proof_of_delivery": (["native", "clean_scan", "photo"], [0.50, 0.38, 0.12]),
    "invoice": (["native", "clean_scan"], [0.50, 0.50]),
    "correspondence": (["native", "screenshot"], [0.70, 0.30]),
    "policy": (["native", "screenshot"], [0.80, 0.20]),
}
# Per-character error rate, confidence spread of correct characters, share of
# errors read with high confidence, and the chance a screenshot crops a field.
OCR = {
    "api": dict(err=0.0, spread=0.0, confident=0.0),
    "native": dict(err=0.0, spread=0.0, confident=0.0),
    "screenshot": dict(err=0.0032, spread=0.022, confident=0.05),
    "clean_scan": dict(err=0.0150, spread=0.034, confident=0.04),
    "photo": dict(err=0.050, spread=0.16, confident=0.02),
}
CROP = 0.018
TO_LETTER = {"0": "O", "1": "l", "5": "S", "8": "B", "2": "Z", "6": "b"}
TO_DIGIT = {v: k for k, v in TO_LETTER.items()} | {"I": "1", "o": "0", "s": "5"}
LOOKALIKE = {"1": "7", "3": "8", "7": "1", "4": "A", "9": "g", "m": "rn", "e": "c",
             "a": "o", "r": "n", "h": "b", "c": "e", "n": "m", "T": "I", "E": "F",
             "A": "4", "R": "B", "M": "N", "N": "H", "D": "O", "C": "G"}

STREETS = ["Harlow", "Maple", "Sterling", "Unity", "Aptos", "Station", "Oak",
           "Lakeview", "Birch", "Cedar", "Highland", "Willow", "Juniper", "Elm",
           "Kingsley", "Orchard", "Riverside", "Summit", "Fairmont", "Ashby",
           "Stewart", "Granger", "Union", "Bellamy", "Crescent", "Hawthorne"]
SUFFIXES = [("Street", "St"), ("Avenue", "Ave"), ("Road", "Rd"), ("Lane", "Ln"),
            ("Drive", "Dr")]
CITIES = [("Cleveland", "OH", "441"), ("Columbus", "OH", "432"), ("Austin", "TX", "787"),
          ("Denver", "CO", "802"), ("Portland", "OR", "972"), ("Atlanta", "GA", "303"),
          ("Phoenix", "AZ", "850"), ("Madison", "WI", "537"), ("Raleigh", "NC", "276")]
SIGNERS = ["J. OKAFOR", "M. LOPEZ", "A. CHEN", "R. PATEL", "S. NOWAK", "K. DUBOIS"]
LOCATIONS = ["Front door", "Mailroom", "Reception", "Porch", "Side door"]


# ----------------------------------------------------------------- the truth
def make_address(rng):
    city, state, zip3 = CITIES[rng.integers(len(CITIES))]
    unit = ""
    if rng.random() < 0.55:
        unit = str(rng.integers(1, 40)) if rng.random() < 0.7 else \
            f"{rng.integers(1, 9)}{'ABCD'[rng.integers(4)]}"
    return {"number": str(rng.integers(1, 9999)),
            "street": STREETS[rng.integers(len(STREETS))],
            "suffix": SUFFIXES[rng.integers(len(SUFFIXES))],
            "unit": unit, "city": city, "state": state,
            "zip": f"{zip3}{rng.integers(0, 100):02d}"}


def other_unit(rng, unit):
    if unit and unit.isdigit() and len(unit) == 2 and rng.random() < 0.5:
        return unit[1]                          # 12 -> 2: the classic misdelivery
    while True:
        u = str(rng.integers(1, 40))
        if u != unit:
            return u


def render_address(a, style):
    """The same address as different systems print it."""
    full, short = a["suffix"]
    if style == "full":
        unit = f", Apt {a['unit']}" if a["unit"] else ""
        return f"{a['number']} {a['street']} {full}{unit}, {a['city']}, {a['state']} {a['zip']}"
    if style == "upper":
        unit = f" #{a['unit']}" if a["unit"] else ""
        return (f"{a['number']} {a['street'].upper()} {short.upper()}{unit}, "
                f"{a['city'].upper()}, {a['state']} {a['zip']}")
    unit = f", Unit {a['unit']}" if a["unit"] else ""
    return f"{a['number']} {a['street']} {short}{unit}, {a['city']}, {a['state']} {a['zip']}"


def render_date(d, fmt, rng):
    hh, mm = rng.integers(8, 20), rng.integers(0, 60)
    if fmt == "iso":
        return f"{d.isoformat()}T{hh:02d}:{mm:02d}"
    if fmt == "us":
        return f"{d.month:02d}/{d.day:02d}/{d.year} {hh:02d}:{mm:02d}"
    return f"{d.strftime('%b')} {d.day}, {d.year}"      # "mon": Nov 28, 2025


def render_attested(kind, rng):
    if kind == "signed":
        return f"Signed by {SIGNERS[rng.integers(len(SIGNERS))]}"
    if kind == "photo":
        return "Photo on file" if rng.random() < 0.5 else "Delivery photo taken"
    return "Not required" if rng.random() < 0.7 else "Signature not required"


# --------------------------------------------------------------- OCR channel
def ocr(text, channel, rng):
    """Return (read_text, char_confidences) for one field or line."""
    cfg = OCR[channel]
    if cfg["err"] == 0:
        return text, [100] * len(text)
    out, conf = [], []

    def good():
        return 1 - min(rng.exponential(cfg["spread"]), 0.75)

    def bad():
        return rng.uniform(0.82, 0.97) if rng.random() < cfg["confident"] \
            else rng.uniform(0.25, 0.80)

    for ch in text:
        if ch != " " and rng.random() < cfg["err"]:
            kind = rng.random()
            if kind < 0.55 and (ch in TO_LETTER or ch in TO_DIGIT):
                out.append(TO_LETTER.get(ch) or TO_DIGIT[ch]); conf.append(bad())
            elif kind < 0.80:
                sub = LOOKALIKE.get(ch) or (str(rng.integers(10)) if ch.isdigit()
                                            else chr(rng.integers(97, 123)))
                for c in sub:
                    out.append(c); conf.append(bad())
            elif kind < 0.93:                           # dropped character
                if conf:
                    conf[-1] = min(conf[-1], bad())
            else:                                       # inserted speck
                out.extend([ch, "."]); conf.extend([good(), bad()])
        else:
            out.append(ch); conf.append(good())
    return "".join(out), [int(c * 100) for c in conf]


# ---------------------------------------------------------- documents/pages
FILLER = {
    "order_record": ["Order confirmation", "Thank you for your order", "Items ordered",
                     "Qty 1", "Subtotal", "Shipping: Standard", "Payment: Visa ending 4417",
                     "Bill to: same as shipping", "Order status: Shipped"],
    "invoice": ["INVOICE", "Invoice number INV-{n}", "Tax", "Subtotal", "Total due",
                "Payment received - thank you", "Terms: paid by card", "Item  Qty  Price"],
    "carrier_record": ["Tracking details", "Status: Delivered", "Out for delivery",
                       "In transit - arrived at facility", "Label created",
                       "Departed facility", "Delivery attempt: 1", "Service: Ground"],
    "proof_of_delivery": ["PROOF OF DELIVERY", "Driver ID {n}", "Delivery confirmation",
                          "Left at: {loc}", "Package delivered", "Recipient signature",
                          "GPS verified"],
    "correspondence": ["From: support@merchant.example", "Subject: Re: your order",
                       "Hi, thanks for reaching out about your order.",
                       "Your parcel shows as delivered.", "Tracking number {trk}",
                       "Please let us know if anything else is needed.",
                       "Order #{order} total {amount}", "Kind regards, Customer care"],
    "policy": ["Returns and refunds policy", "Shipping policy", "Items may be returned "
               "within 30 days", "Delivery times are estimates", "Terms of sale",
               "Refunds are issued to the original card", "Order #{order}"],
}


GENERIC = ["Order #{order}", "Tracking number {trk}", "Customer service 1-800-555-0199",
           "Page 1 of 1", "Northwind Goods Ltd", "Questions? Reply to this message",
           "Amount {amount}", "Status: Delivered", "Ship date", "Reference {n}",
           "www.northwind.example", "Thank you"]
PAGE_SPECIFIC = (1, 3)       # distinctive lines per page (min, max exclusive)
PAGE_GENERIC = (2, 5)        # lines common to every document type
PAGE_CROP = 0.45             # share of screenshots and photos cropped to a few lines


def page_text(doc_type, field_lines, ctx, channel, rng):
    def fill(pool, k):
        return [l.format(n=rng.integers(1000, 99999), loc=ctx["loc"], trk=ctx["trk"],
                         order=ctx["order"], amount=ctx["amount_txt"])
                for l in rng.permutation(pool)[:k]]
    lines = (fill(FILLER[doc_type], rng.integers(*PAGE_SPECIFIC))
             + fill(GENERIC, rng.integers(*PAGE_GENERIC)) + field_lines)
    order = rng.permutation(len(lines))
    lines = [lines[i] for i in order]
    if channel in ("screenshot", "photo") and rng.random() < PAGE_CROP:
        k = rng.integers(1, 4)                          # cropped or partial capture
        start = rng.integers(0, max(1, len(lines) - k))
        lines = lines[start:start + k]
    read = [ocr(l, channel, rng)[0] if l not in field_lines else l for l in lines]
    return "\n".join(read)


def generate(seed=SEED):
    rng = np.random.default_rng(seed)
    n_merch = 600
    quality = rng.normal(0, 1, n_merch)            # merchants that keep good records
    merchant = rng.integers(0, n_merch, N_CASES)
    q = quality[merchant]

    def pick(n, strength, boost=None):
        w = np.exp(strength * q) * (1 if boost is None else boost)
        return set(rng.choice(N_CASES, n, replace=False, p=w / w.sum()))

    has_carrier = pick(N_CARRIER, 0.3)
    carrier_api = set(rng.choice(sorted(has_carrier), N_CARRIER_API, replace=False))
    no_carrier = np.array([1.0 if i in has_carrier else 4.0 for i in range(N_CASES)])
    has_pod = pick(N_POD, 0.2, no_carrier)          # a POD stands in for the carrier
    has_invoice = pick(N_INVOICE, 0.3)

    cases, truth, docs, readings, pages = [], [], [], [], []
    for i in range(N_CASES):
        cid = f"NR{i + 1:05d}"
        opened = START + timedelta(days=int(rng.integers(0, 365)))
        order_on = opened - timedelta(days=int(rng.integers(12, 45)))
        expected = order_on + timedelta(days=int(rng.integers(3, 8)))
        claimed = opened
        amount = int(round(np.exp(np.log(90) + rng.normal(0, 0.8)) * 100))
        amount = max(amount, 899)
        ship = make_address(rng)

        # What really happened to the parcel
        r = rng.random()
        bad_merchant = 1 / (1 + np.exp(-(-2.3 - 0.5 * q[i])))
        if r < bad_merchant * 0.55:
            outcome, delivered = "unit_differs", dict(ship)
            delivered["unit"] = other_unit(rng, ship["unit"]) if ship["unit"] else \
                str(rng.integers(1, 30))
        elif r < bad_merchant:
            outcome, delivered = "wrong_address", make_address(rng)
            delivered["city"], delivered["state"] = ship["city"], ship["state"]
        else:
            outcome, delivered = "delivered", dict(ship)
        late = rng.random() < 0.14
        delivered_on = expected + timedelta(days=int(rng.integers(4, 9))) if late \
            else expected - timedelta(days=int(rng.integers(0, 4)))
        if delivered_on >= claimed:
            delivered_on = claimed - timedelta(days=1)
        attested = rng.choice(["signed", "photo", "none"], p=[0.22, 0.48, 0.30])

        trk = f"NP{rng.integers(10**11, 10**12)}"
        order_id = f"{rng.integers(100000, 999999)}"
        ctx = {"loc": LOCATIONS[rng.integers(len(LOCATIONS))], "trk": trk,
               "order": order_id, "amount_txt": f"${amount / 100:,.2f}"}

        plan = [("order_record", [("ship_to", ship), ("amount", amount)])]
        if i in has_carrier:
            fields = [("delivered_to", delivered), ("delivered_on", delivered_on)]
            if i in carrier_api:
                fields.append(("attested", attested))
            plan.append(("carrier_record", fields))
        if i in has_pod:
            plan.append(("proof_of_delivery", [("delivered_to", delivered),
                                               ("delivered_on", delivered_on),
                                               ("attested", attested)]))
        if i in has_invoice:
            plan.append(("invoice", [("amount", amount), ("ship_to", ship)]))
        extra = rng.poisson(0.6 + 0.15 * max(q[i], 0))
        for _ in range(min(extra, 3)):
            plan.append(("correspondence" if rng.random() < 0.7 else "policy", []))

        for d, (doc_type, fields) in enumerate(plan, start=1):
            types, probs = CHANNEL_MIX[doc_type]
            channel = rng.choice(types, p=probs)
            if doc_type == "carrier_record":
                channel = "api" if i in carrier_api else "screenshot"
            doc_id = f"{cid}-D{d}"
            field_lines = []
            for name, value in fields:
                fmt = ""
                if name in ("ship_to", "delivered_to"):
                    style = {"order_record": "full", "invoice": "unit",
                             "carrier_record": "upper",
                             "proof_of_delivery": "upper"}[doc_type]
                    true = render_address(value, style)
                elif name == "amount":
                    true = f"${value / 100:,.2f}"
                elif name == "delivered_on":
                    fmt = {"carrier_record": "iso" if channel == "api" else "mon",
                           "proof_of_delivery": "us"}[doc_type]
                    true = render_date(value, fmt, rng)
                else:
                    true = render_attested(value, rng)
                raw, conf = ocr(true, channel, rng)
                if channel == "screenshot" and rng.random() < CROP:
                    raw, conf = "", []                 # cropped above the field
                readings.append({"case_id": cid, "doc_id": doc_id, "doc_type": doc_type,
                                 "page": 1, "channel": channel, "field": name,
                                 "date_format": fmt, "raw_text": raw,
                                 "char_conf": " ".join(map(str, conf)),
                                 "true_text": true})
                label = {"ship_to": "Ship to:", "delivered_to": "Delivered to:",
                         "amount": "Total:", "delivered_on": "Delivered on:",
                         "attested": "Signature:"}[name]
                if raw:
                    field_lines.append(f"{label} {raw}")
            text = page_text(doc_type, field_lines, ctx, channel, rng)
            if channel != "api":
                pages.append({"page_id": f"{doc_id}-P1", "doc_id": doc_id, "case_id": cid,
                              "doc_type": doc_type, "channel": channel, "text": text})
            docs.append({"doc_id": doc_id, "case_id": cid, "doc_type": doc_type,
                         "channel": channel, "pages": 1,
                         "sha256": hashlib.sha256(text.encode()).hexdigest()})

        cases.append({"case_id": cid, "reason": "not_received",
                      "opened_on": opened.isoformat(), "claimed_on": claimed.isoformat(),
                      "expected_on": expected.isoformat(), "amount_cents": amount,
                      "currency": "USD", "merchant_id": f"M{merchant[i]:04d}",
                      "tracking_number": trk if i in has_carrier else "",
                      "n_documents": len(plan)})
        truth.append({"case_id": cid, "delivery": outcome,
                      "delivered_on": delivered_on.isoformat(), "late": late,
                      "attested": attested, "merchant_quality": round(q[i], 3)})
    return (pd.DataFrame(cases), pd.DataFrame(docs), pd.DataFrame(readings),
            pd.DataFrame(pages), pd.DataFrame(truth), rng)


def add_outcomes(truth, perfect_score, quality, rng):
    """Whether the merchant's evidence prevailed with the reviewer (simulator)."""
    z = -6.0 + 8.2 * perfect_score + 0.1 * quality + rng.normal(0, 0.3, len(truth))
    p = 0.08 + 0.89 / (1 + np.exp(-z))      # some weak packets still prevail
    return rng.random(len(truth)) < p


def main():
    cases, docs, readings, pages, truth, rng = generate()
    # The outcome depends on what the documents really show: score each packet
    # with perfect readings (the true text) and let reviewers decide from that.
    import evidence_pipeline as ep                       # noqa: E402
    perfect = ep.perfect_scores(cases, readings, truth)
    truth["perfect_score"] = perfect
    truth["prevailed"] = add_outcomes(truth, perfect, truth.merchant_quality, rng)
    OUT.mkdir(exist_ok=True)
    for name, frame in (("cases", cases), ("documents", docs), ("readings", readings),
                        ("pages", pages), ("truth", truth)):
        frame.to_csv(OUT / f"{name}.csv", index=False)
    size = sum(f.stat().st_size for f in OUT.glob("*.csv")) / 1e6
    print(f"wrote {OUT.name}/: {len(cases):,} cases, {len(docs):,} documents, "
          f"{len(readings):,} field readings, {len(pages):,} pages ({size:.1f} MB)")
    print(f"  merchant's evidence prevailed in {truth.prevailed.mean():.1%} of cases")
    print("  readings by channel:", {str(k): int(v) for k, v in readings.channel.value_counts().items()})


if __name__ == "__main__":
    main()
