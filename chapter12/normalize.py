"""Value parsers used by the checker (Chapter 11 normalizers, extended to prose).

Each parser turns free text into a set of canonical values, so that a value
written in a sentence can be compared with the value held in a record:

* amounts("$249.00") -> {"249.00"}
* dates("28 November 2025") -> {"2025-11-28", "--11-28"}
* units("41 Harlow Street, unit 12, 44107") -> {"street:41", "unit:12", "zip:44107"}

Chapter 11 parsed dates written as ISO strings and as "28 Nov 2025"; this
version also reads dates written in prose ("28 November 2025",
"November 28, 2025") and a day and month without a year ("29 November").
A month name that none of the patterns can resolve, such as the ordinal
style "the 28th of November", is returned as an *unverifiable* token. That
token never appears in a record, so the checker refuses a date it cannot
read rather than passing it.

The book's copy of this module lives in chapter11/; this chapter carries its
own copy so that it runs on its own.
"""
import re

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
MONTH_NUM = {m: i for i, m in enumerate(MONTHS, start=1)}
_M = "|".join(MONTHS)

AMOUNT = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{2}))?")
ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DMY = re.compile(rf"\b(\d{{1,2}}) ({_M})(?: (\d{{4}}))?\b")
MDY = re.compile(rf"\b({_M}) (\d{{1,2}}),? (\d{{4}})\b")
MONTH_WORD = re.compile(rf"\b({_M})\b")

UNIT = re.compile(r"\b(?:unit|apartment|apt\.?|suite|flat)\s*#?\s*(\d+[A-Z]?)\b", re.I)
STREET = re.compile(r"\b(\d{1,5})\s+(?:[A-Z][a-z]+\s){1,3}"
                    r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Way|Court|Ct|"
                    r"Place|Pl|Boulevard|Blvd|Terrace|Close)\b")
ZIP = re.compile(r"(?<![\d$.,])\b(\d{5})\b(?![.,]\d)")


def amounts(text):
    """Every dollar amount in the text, as a string with two decimals."""
    out = set()
    for whole, cents in AMOUNT.findall(text):
        out.add(f"{int(whole.replace(',', ''))}.{cents or '00'}")
    return out


def dates(text):
    """Every date in the text as ISO and as a year-less --MM-DD key.

    A date written without a year yields only the --MM-DD key, so that
    "29 November" in a sentence matches "29 November 2025" in a record.
    A month name left over after all patterns have been applied yields an
    'unverifiable:' token, which can never match a record.
    """
    out, spans = set(), []
    for m in ISO.finditer(text):
        y, mo, d = (int(g) for g in m.groups())
        out |= {f"{y:04d}-{mo:02d}-{d:02d}", f"--{mo:02d}-{d:02d}"}
        spans.append(m.span())
    for m in MDY.finditer(text):
        mo, d, y = MONTH_NUM[m.group(1)], int(m.group(2)), int(m.group(3))
        out |= {f"{y:04d}-{mo:02d}-{d:02d}", f"--{mo:02d}-{d:02d}"}
        spans.append(m.span())
    for m in DMY.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        d, mo = int(m.group(1)), MONTH_NUM[m.group(2)]
        out.add(f"--{mo:02d}-{d:02d}")
        if m.group(3):
            out.add(f"{int(m.group(3)):04d}-{mo:02d}-{d:02d}")
        spans.append(m.span())
    for m in MONTH_WORD.finditer(text):
        if not any(a <= m.start() < b for a, b in spans):
            out.add(f"unverifiable:{m.group(1)}@{m.start()}")
    return out


def units(text):
    """Address numbers: street numbers, unit or apartment numbers and ZIP codes."""
    out = {f"unit:{u.upper()}" for u in UNIT.findall(text)}
    out |= {f"street:{s}" for s in STREET.findall(text)}
    out |= {f"zip:{z}" for z in ZIP.findall(text)}
    return out
