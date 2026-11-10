"""The checker (Listing 12.4), plus the privacy and length checks of Table 12.5.

check() returns a list of (flag, sentence) pairs; an empty list means the
draft passed. Flags: tone, no_citation, bad_citation, unsupported_value,
unsupported_claim, missing_required, privacy.
"""
import re

from normalize import amounts, dates, units   # Chapter 11 parsers, extended

CITE = re.compile(r"\[([A-Z][\w-]*)\]")
# The book's pattern reads 'received the parcel'; 'received your parcel' is
# added so that the customer letter's second-person wording is caught too.
OVERCLAIM = re.compile(r"\b(received (?:the|your) parcel|confirms receipt|fraudulent|"
                       r"lying|not telling the truth|proves?)\b", re.I)
ATTRIBUTES = re.compile(r"\b(signed for|neighbour|replacement|attempted|"
                        r"by phone|high risk)\b", re.I)
PRIVATE = [re.compile(r"\b\d{12,19}\b"),                       # card number
           re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),          # email address
           re.compile(r"\+?\d[\d\s().-]{8,}\d")]                # telephone number


def check(sentences, items, required=("F1", "F3", "F5", "F6")):
    flags = []
    for s in sentences:
        ids, body = CITE.findall(s), CITE.sub("", s)
        if any(p.search(body) for p in PRIVATE):
            flags.append(("privacy", s))
        if OVERCLAIM.search(body):
            flags.append(("tone", s))
        if not ids:
            flags.append(("no_citation", s)); continue
        if any(i not in items for i in ids):
            flags.append(("bad_citation", s)); continue
        source = " ".join(items[i][1] for i in ids)
        if any(not parse(body) <= parse(source) for parse in (amounts, dates, units)):
            flags.append(("unsupported_value", s)); continue
        if ATTRIBUTES.search(body) and not ATTRIBUTES.search(source):
            flags.append(("unsupported_claim", s))
    cited = {i for s in sentences for i in CITE.findall(s)}
    flags += [("missing_required", f) for f in required
              if f in items and f not in cited]
    return flags


def check_length(text, max_words):
    """Structure and length: a draft over its word limit is regenerated."""
    words = len(CITE.sub("", text).split())
    return [("too_long", f"{words} words")] if words > max_words else []


def action_for(flags):
    """What Table 12.5 says to do with a set of flags."""
    kinds = {kind for kind, _ in flags}
    if "privacy" in kinds:
        return "block_and_alert"
    return "regenerate" if kinds else "pass"
