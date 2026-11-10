"""Compare facts with the case record (Listing 11.3).

Uses rapidfuzz when it is installed; otherwise an exact pure-Python
equivalent of rapidfuzz.fuzz.ratio (normalized Indel similarity), so results
are the same either way.
"""
from datetime import date, datetime

try:
    from rapidfuzz import fuzz
except ImportError:                                   # same numbers, slower
    class fuzz:                                       # noqa: N801
        @staticmethod
        def ratio(a, b):
            if not a and not b:
                return 100.0
            prev = [0] * (len(b) + 1)                 # longest common subsequence
            for ca in a:
                cur = [0]
                for j, cb in enumerate(b):
                    cur.append(prev[j] + 1 if ca == cb else max(prev[j + 1], cur[j]))
                prev = cur
            return 100.0 * 2 * prev[-1] / (len(a) + len(b))


def address_match(found, given):
    """Compare a delivered-to address with the ship-to address on the order."""
    if not found or not given:
        return 0.0, "missing"
    number = found["number"] == given["number"]
    street = fuzz.ratio(found["street"], given["street"]) / 100
    zip5 = found["zip"] == given["zip"]
    unit = found["unit"] == given["unit"]
    score = 0.30 * number + 0.30 * street + 0.25 * zip5 + 0.15 * unit
    if number and street > 0.85 and zip5:
        return round(score, 3), "match" if unit else "unit_differs"
    return round(score, 3), "no_match"


def amount_match(found_cents, case_cents, currency, case_currency):
    return currency == case_currency and found_cents == case_cents


def _day(d):
    """Dates as day numbers, so that a grace period in days can be added."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if isinstance(d, datetime):
        d = d.date()
    return d.toordinal() if isinstance(d, date) else d


def on_time(delivered_on, expected_on, claimed_on, grace_days=3):
    delivered_on, expected_on, claimed_on = map(_day, (delivered_on, expected_on,
                                                       claimed_on))
    return (delivered_on <= expected_on + grace_days) and (delivered_on < claimed_on)


if __name__ == "__main__":
    # 1,500 test pairs: the same address printed in two styles and read from a
    # clean scan, against two addresses drawn at random.
    import numpy as np

    from extract import normalize_address
    from make_evidence_data import make_address, ocr, render_address

    rng = np.random.default_rng(3)
    same, rand = [], []
    for _ in range(1500):
        a, b = make_address(rng), make_address(rng)
        printed = normalize_address(render_address(a, "full"))
        scanned = normalize_address(ocr(render_address(a, "upper"), "clean_scan", rng)[0])
        same.append(address_match(scanned, printed)[0])
        rand.append(address_match(normalize_address(render_address(b, "upper")),
                                  printed)[0])
    print(f"address_match on 1,500 pairs: same address, two styles, clean scan "
          f"{np.mean(same):.2f}; random pairs {np.mean(rand):.2f}")
