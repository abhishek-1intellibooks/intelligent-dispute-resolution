"""Redacting card numbers and contact details from free text (Listing 15.3).

`redact` is version 3 of Table 15.7. Versions 1 and 2 are kept for the
comparison in governance_demo.py.
"""
import re

CANDIDATE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
LABELLED = re.compile(r"\b(order|invoice|tracking|reference|ref)\b\W*$", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)")


def luhn_ok(digits):
    total, double = 0, False
    for ch in reversed(digits):
        n = int(ch) * (2 if double else 1)
        total += n - 9 if n > 9 else n
        double = not double
    return total % 10 == 0


def redact(text):
    def card(m):
        digits = re.sub(r"\D", "", m.group())
        looks_like_card = luhn_ok(digits) and digits[0] in "3456"
        labelled = LABELLED.search(text[:m.start()][-25:])
        return "[card number]" if looks_like_card and not labelled else m.group()
    text = CANDIDATE.sub(card, text)
    return PHONE.sub("[phone]", EMAIL.sub("[email]", text))


# Earlier versions, for Table 15.7 ------------------------------------------
V1_PATTERN = re.compile(r"\b\d{12,19}\b")


def redact_v1(text):
    """Chapter 12: any run of 12 to 19 digits."""
    return V1_PATTERN.sub("[card number]", text)


def redact_v2(text):
    """Digits with optional spaces or dashes, passing the card checksum."""
    def card(m):
        digits = re.sub(r"\D", "", m.group())
        return "[card number]" if luhn_ok(digits) else m.group()
    return CANDIDATE.sub(card, text)
