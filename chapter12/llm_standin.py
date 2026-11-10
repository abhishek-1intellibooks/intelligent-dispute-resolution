"""A deterministic stand-in for a hosted chat model.

The stand-in reads the same system prompt and context that a hosted model
would, writes the document from templates, and then makes known kinds of
mistake at rates you can set. Because it records which mistakes it made, the
evaluation can measure what the checker catches against a known truth. Its
rates are illustrative parameters, not a measurement of any real model.

Mistakes it can make (names used throughout the chapter):

* bad_citation      cites an item that does not exist, or nothing at all
* omission          leaves out a fact the reason code makes decisive
* wrong_fact        misstates a value (amount, date, unit) or a word
                    ('signature' where the record says 'photograph')
* overclaim         says more than the record supports ('received the parcel')
* unsupported_claim asserts something that is in no item (a second attempt,
                    a neighbour, a good complaints record)
* ordinal_dates     not a mistake: writes dates as 'the 28th of November 2025',
                    which is correct but which the checker's parser cannot read

Every call is seeded from the prompt and the number of times that prompt has
been seen, so a run is reproducible and a regeneration is a fresh draw.
"""
import hashlib
import json
import random
import re
from datetime import date, timedelta

from normalize import MONTH_NUM

ERROR_TYPES = ("bad_citation", "omission", "wrong_fact", "overclaim", "unsupported_claim")

# Per-draft probability of each mistake, by kind of document. Lower in the
# grounded configurations, as published studies of retrieval-grounded
# generation lead one to expect. Illustrative values chosen so that the
# evaluation lands near the book's Table 12.6.
DEFAULT_RATES = {
    "summary_plain": {"wrong_fact": 0.16, "unsupported_claim": 0.15, "overclaim": 0.10,
                      "omission": 0.10, "ordinal_dates": 0.22},
    "summary_cite": {"bad_citation": 0.062, "omission": 0.075, "wrong_fact": 0.085,
                     "overclaim": 0.04, "unsupported_claim": 0.078, "ordinal_dates": 0.235},
    "summary_slot": {"bad_citation": 0.03, "omission": 0.035, "wrong_fact": 0.015,
                     "overclaim": 0.022, "unsupported_claim": 0.045},
    "letter": {"overclaim": 0.05, "wrong_fact": 0.03, "unsupported_claim": 0.03},
    "narrative": {"unsupported_claim": 0.03, "bad_citation": 0.02},
}
CLEAN_RATES = {mode: {} for mode in DEFAULT_RATES}

# Share of each mistake written in a form the checker's patterns can see.
VISIBLE = {"wrong_fact": 0.92, "overclaim": 0.86, "unsupported_claim": 0.70}
# With facts slotted, the model rarely writes a value itself, so most of its
# wrong facts are words ('signature' for 'photograph') that no parser reads.
VISIBLE_SLOTTED = {**VISIBLE, "wrong_fact": 0.7}

NAMES = {"claim": "C1", "merchant": "C2", "clock": "C3", "narrative (customer's words)": "N1",
         "ordered_on": "F1", "order_amount": "F2", "shipped_to": "F3", "expected_on": "F4",
         "delivered_to": "F5", "delivered_on": "F6", "proof_of_delivery": "F7",
         "sufficiency": "D1", "recovery": "D2"}
NARR = "narrative (customer's words)"

SUMMARY = [
    ("claim", "claim", "The claim concerns a {claim}", ["claim"]),
    ("claim", "merchant", "The merchant is {merchant}", ["merchant"]),
    ("claim", "narr", "The customer says the parcel never arrived", [NARR]),
    ("evidence", "order", "The order was placed on {ordered_on} for {order_amount}",
     ["ordered_on", "order_amount"]),
    ("evidence", "shipped", "It was shipped to {shipped_to}", ["shipped_to"]),
    ("evidence", "delivery", "The carrier records delivery to {delivered_to} on {delivered_on}",
     ["delivered_to", "delivered_on"]),
    ("evidence", "proof", "The expected delivery date was {expected_on}, and the proof of "
                          "delivery on file is {proof_of_delivery}",
     ["expected_on", "proof_of_delivery"]),
    ("evidence", "score", "The sufficiency assessment recorded is {sufficiency}", ["sufficiency"]),
    ("status", "clock", "The case stands at {clock} on the investigation clock", ["clock"]),
    ("status", "recovery", "The recovery decision recorded is {recovery}", ["recovery"]),
    ("open_questions", "mailroom", "The record does not say whether the building at "
                                   "{delivered_to} has a shared mailroom", ["delivered_to"]),
]

LETTER = [
    ("body", "opening", "We have reviewed your dispute about your payment to {merchant}, "
                        "recorded as a {claim}", ["merchant", "claim"]),
    ("body", "narr", "You told us that your order did not arrive", [NARR]),
    ("body", "order", "Your order was placed on {ordered_on} and shipped to {shipped_to}",
     ["ordered_on", "shipped_to"]),
    ("body", "delivery", "The carrier's records show delivery to your address, {delivered_to}, "
                         "on {delivered_on}", ["delivered_to", "delivered_on"]),
    ("body", "proof", "The carrier's proof of delivery is {proof_of_delivery}, and a copy is "
                      "enclosed", ["proof_of_delivery"]),
    ("body", "credit", "Your provisional credit stays in place while you respond, and we are "
                       "at {clock} of our investigation", ["clock"]),
    ("body", "reply", "Please reply within 10 days with anything the carrier's records do not "
                      "show", ["clock"]),
    ("body", "rights", "You may ask us for copies of the documents we relied on",
     ["sufficiency"]),
]

NARRATIVE = [
    ("body", "order", "The order was placed on {ordered_on} for {order_amount} and shipped to "
                      "{shipped_to}, the address the cardholder supplied",
     ["ordered_on", "order_amount", "shipped_to"]),
    ("body", "delivery", "The carrier's record shows delivery to that address [{K:delivered_to}] "
                         "on {delivered_on}, before the expected date of {expected_on}, with "
                         "{proof_of_delivery}",
     ["delivered_on", "expected_on", "proof_of_delivery"]),
    ("body", "rule", "These records meet the proof-of-delivery requirements of [{RULE}] for "
                     "this reason code", []),
]

OVERCLAIM_VISIBLE = [
    ("The customer received the parcel on {delivered_on}", ["delivered_to", "delivered_on"]),
    ("The carrier record proves that the customer took delivery at {delivered_to}",
     ["delivered_to"]),
    ("The delivery scan confirms receipt by the customer on {delivered_on}",
     ["delivered_to", "delivered_on"]),
]
OVERCLAIM_HIDDEN = [("The customer evidently has the goods", ["delivered_to", "delivered_on"])]
LETTER_OVERCLAIM = ("Our records show you received your parcel on {delivered_on}",
                    ["delivered_to", "delivered_on"])

UNSUPPORTED_VISIBLE = [
    ("The carrier attempted delivery once before, on {attempt_day}", ["delivered_on"]),
    ("The parcel was left with a neighbour at {delivered_to}", ["delivered_to"]),
    ("The merchant offered a replacement", ["merchant"]),
    ("The customer also spoke to the merchant by phone", [NARR]),
]
UNSUPPORTED_HIDDEN = [
    ("The merchant has a good record of resolving complaints", ["merchant"]),
    ("Deliveries to this address have been reliable in the past", ["delivered_to"]),
]
INVENTED_IDS = ["F12", "F9", "D3", "E1"]


def parse_pack(user):
    """Read the numbered items (or plain notes) the way a model would."""
    m = re.search(r"<context>\n(.*?)\n</context>", user, re.S)
    body = m.group(1) if m else user
    items = {}
    for line in body.splitlines():
        hit = re.match(r"\[([A-Z][\w-]*)\] ([^:]+): (.*)$", line)
        if hit:
            items[hit.group(1)] = (hit.group(2), hit.group(3))
            continue
        hit = re.match(r"([^:]+): (.*)$", line)
        if hit and hit.group(1) in NAMES:
            items[NAMES[hit.group(1)]] = (hit.group(1), hit.group(2))
    return items


def ordinal(value):
    """'28 November 2025 at 14:12' -> 'the 28th of November 2025 at 14:12'."""
    def repl(m):
        d = int(m.group(1))
        suffix = "th" if 11 <= d % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
        return f"the {d}{suffix} of {m.group(2)}"
    return re.sub(r"\b(\d{1,2}) (" + "|".join(MONTH_NUM) + r")\b", repl, value, count=1)


def shift_date(value, days):
    m = re.search(r"\b(\d{1,2}) (" + "|".join(MONTH_NUM) + r") (\d{4})", value)
    if not m:
        return value
    d = date(int(m.group(3)), MONTH_NUM[m.group(2)], int(m.group(1))) + timedelta(days=days)
    return value[:m.start()] + f"{d.day} {d:%B %Y}" + value[m.end():]


def alter_amount(value, rng):
    m = re.search(r"\$([\d,]+)\.(\d{2})", value)
    if not m:
        return value
    whole = int(m.group(1).replace(",", ""))
    digits = str(whole)
    if len(digits) > 1 and digits[-1] != digits[-2]:
        new = int(digits[:-2] + digits[-1] + digits[-2])          # 249 -> 294
    else:
        new = whole + rng.choice([10, 20, 50])
    return value[:m.start()] + f"${new:,}.{m.group(2)}" + value[m.end():]


def alter_address(value, rng):
    m = re.search(r"unit (\d+)", value)
    if m:
        n = int(m.group(1))
        return value[:m.start()] + f"unit {n + rng.randint(1, 9)}" + value[m.end():]
    m = re.match(r"(\d+)", value)
    if m:
        return f"{int(m.group(1)) + 2}" + value[m.end():]
    return value


class StandIn:
    """Deterministic stand-in with settable error rates.

    rates  : {mode: {mistake: probability}}; missing modes use DEFAULT_RATES
    script : {mode: [[mistakes for call 1], [mistakes for call 2], ...]};
             replays a fixed sequence (used by worked_example.py), then falls
             back to the rates
    """
    name = "standin-1.0"

    def __init__(self, seed=12, rates=None, script=None):
        self.seed = seed
        self.rates = {**DEFAULT_RATES, **(rates or {})}
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.seen = {}
        self.last = None

    # ---------------------------------------------------------------- dispatch
    def generate(self, system, user, max_tokens=700, temperature=0):
        mode = self._mode(system)
        digest = hashlib.sha256(f"{self.seed}|{system}|{user}".encode()).hexdigest()
        count = self.seen.get(digest, 0)
        self.seen[digest] = count + 1
        rng = random.Random(int(digest[:16], 16) + count)
        items = parse_pack(user)
        if mode is None:
            self.last = {"mode": None, "errors": [], "ordinal": False}
            return json.dumps({"note": "The stand-in only writes this chapter's documents."})
        errors, use_ordinal = self._draw(mode, rng)
        self.last = {"mode": mode, "errors": errors, "ordinal": use_ordinal}
        if mode.startswith("summary"):
            style = {"summary_plain": "plain", "summary_cite": "cite", "summary_slot": "slot"}[mode]
            specs = self._apply(self._specs(SUMMARY), errors, use_ordinal, style, items, rng)
            out = {"claim": [], "evidence": [], "status": [], "open_questions": []}
            for spec in specs:
                out[spec["sec"]].append(self._sentence(spec, style, items))
            return json.dumps(out)
        if mode == "letter":
            specs = self._apply(self._specs(LETTER), errors, False, "cite", items, rng,
                                overclaim=LETTER_OVERCLAIM)
            return "\n".join(self._sentence(s, "cite", items) for s in specs)
        specs = self._apply(self._specs(NARRATIVE), errors, False, "slot", items, rng)
        return "\n".join(self._sentence(s, "slot", items) for s in specs)

    @staticmethod
    def _mode(system):
        if "You draft the narrative of a representment" in system:
            return "narrative"
        if "You draft a letter to a cardholder" in system:
            return "letter"
        if "from the analyst's notes" in system:
            return "summary_plain"
        if "You summarize card dispute cases" in system:
            return "summary_slot" if "placeholder" in system else "summary_cite"
        return None

    def _draw(self, mode, rng):
        rates = self.rates.get(mode, {})
        draws = {kind: rng.random() for kind in ERROR_TYPES + ("ordinal_dates",)}
        if self.script.get(mode):
            errors = list(self.script[mode].pop(0))
            return errors, False
        errors = [k for k in ERROR_TYPES if draws[k] < rates.get(k, 0.0)]
        return errors, draws["ordinal_dates"] < rates.get("ordinal_dates", 0.0)

    @staticmethod
    def _specs(table):
        return [{"sec": s, "tag": t, "tpl": tpl, "names": list(n), "override": {}, "cites": None}
                for s, t, tpl, n in table]

    # ---------------------------------------------------------------- writing
    @staticmethod
    def _key(name, items):
        for key, (item_name, _value) in items.items():
            if item_name == name:
                return key
        return NAMES.get(name)

    def _sentence(self, spec, style, items):
        slotted = []

        def fill(m):
            field = m.group(1)
            if field in spec["override"]:
                return spec["override"][field]
            key = self._key(field, items)
            if key is None or key not in items:
                return field
            if style == "slot":
                slotted.append(key)
                return "{{" + key + "}}"
            return items[key][1]

        text = re.sub(r"\{K:([\w ()'’]+)\}", lambda m: self._key(m.group(1), items) or "", spec["tpl"])
        rule = next((k for k, (n, _v) in items.items() if n == "rule"), "R-NONE")
        text = text.replace("{RULE}", rule)
        text = re.sub(r"\{([a-z_]+|narrative \(customer's words\))\}", fill, text)
        if style == "plain":
            return text + "."
        if spec["cites"] is not None:
            cites = spec["cites"]
        else:
            cites = [self._key(n, items) for n in spec["names"]]
            cites = [c for c in cites if c and c not in slotted]
        return text + (" " + "".join(f"[{c}]" for c in cites) if cites else "") + "."

    def _apply(self, specs, errors, use_ordinal, style, items, rng, overclaim=None):
        by_tag = {s["tag"]: s for s in specs}

        def value(name):
            key = self._key(name, items)
            return items[key][1] if key in items else ""

        if "omission" in errors:
            drop = rng.choice([t for t in ("order", "shipped") if t in by_tag] or ["order"])
            if drop not in by_tag and "delivery" in by_tag:
                drop = "delivery"
            specs = [s for s in specs if s["tag"] != drop]
            by_tag.pop(drop, None)
        if "overclaim" in errors and "delivery" in by_tag:
            if overclaim is not None:
                tpl, names = overclaim
            elif rng.random() < VISIBLE["overclaim"]:
                tpl, names = rng.choice(OVERCLAIM_VISIBLE)
            else:
                tpl, names = OVERCLAIM_HIDDEN[0]
            by_tag["delivery"].update(tpl=tpl, names=list(names))
        if "wrong_fact" in errors:
            visible = (VISIBLE_SLOTTED if style == "slot" else VISIBLE)["wrong_fact"]
            self._wrong_fact(by_tag, value, rng, visible)
        if "unsupported_claim" in errors:
            if rng.random() < VISIBLE["unsupported_claim"]:
                tpl, names = rng.choice(UNSUPPORTED_VISIBLE)
            else:
                tpl, names = rng.choice(UNSUPPORTED_HIDDEN)
            extra = {"sec": "evidence", "tag": "extra", "tpl": tpl, "names": list(names),
                     "override": {}, "cites": None}
            if "{attempt_day}" in tpl:
                extra["override"]["attempt_day"] = shift_date(value("delivered_on"), -1).split(" at ")[0]
            pos = max((i for i, s in enumerate(specs) if s["sec"] in ("claim", "evidence", "body")),
                      default=len(specs) - 1)
            specs.insert(pos + 1, extra)
        if "bad_citation" in errors:
            target = rng.choice([s for s in specs if s["tag"] not in ("narr",)] or specs)
            if style == "cite" and rng.random() < 1 / 3:
                target["cites"] = []
            else:
                target["cites"] = [rng.choice(INVENTED_IDS)]
        if use_ordinal:
            for tag, name in rng.sample([("order", "ordered_on"), ("delivery", "delivered_on"),
                                         ("proof", "expected_on")], 3):
                spec = by_tag.get(tag)
                if spec and "{" + name + "}" in spec["tpl"] and name not in spec["override"]:
                    spec["override"][name] = ordinal(value(name))
                    break
        return specs

    def _wrong_fact(self, by_tag, value, rng, visible):
        """Misstate a value the checker can parse, or (less often) a word it cannot."""
        if rng.random() < visible:
            options = []
            if "order" in by_tag and "{order_amount}" in by_tag["order"]["tpl"]:
                options.append(("order", "order_amount", alter_amount(value("order_amount"), rng)))
            if "delivery" in by_tag and "{delivered_on}" in by_tag["delivery"]["tpl"]:
                options.append(("delivery", "delivered_on",
                                shift_date(value("delivered_on"), rng.choice([-2, -1, 1, 2]))))
            for tag in ("shipped", "order"):
                if tag in by_tag and "{shipped_to}" in by_tag[tag]["tpl"]:
                    options.append((tag, "shipped_to", alter_address(value("shipped_to"), rng)))
            if options:
                tag, name, new = rng.choice(options)
                self._literal(by_tag[tag], name, new)
                return
        spec = by_tag.get("proof")
        if spec is not None:
            current = value("proof_of_delivery")
            new = "a signature on delivery" if "photograph" in current else "a delivery photograph"
            self._literal(spec, "proof_of_delivery", new)

    @staticmethod
    def _literal(spec, name, new):
        """The model writes a value itself instead of copying or slotting it.

        In the slotted style the item is then cited in brackets rather than
        filled from a placeholder, so the checker compares the written value
        with the record.
        """
        spec["override"][name] = new
