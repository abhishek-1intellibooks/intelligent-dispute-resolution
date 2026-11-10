"""Read facts from documents: records, normalizers and readers (Listing 11.2).

The listing's core (Fact, field_confidence, normalize_address, read_amount,
repair_date_digits) is followed by the remaining readers (dates and
attestations), the function that turns one field reading into a Fact, and the
OCR interface. The synthetic data already carry simulated OCR output, so the
chapter runs without an OCR engine; to run on real files, plug an engine into
OcrEngine (Tesseract through pytesseract, or a cloud document service).
"""
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

UNIT = re.compile(r",?\s*(?:\b(?:APT|APARTMENT|UNIT|STE|SUITE)\b|#)\s*\.?\s*([0-9A-Z]+)",
                  re.I)
SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "LANE": "LN", "DRIVE": "DR"}
DIGITS = str.maketrans("OlSBZ", "01582")     # common OCR confusions, digits only


@dataclass
class Fact:
    name: str
    value: object
    confidence: float     # weakest character in the field
    doc_id: str
    page: int
    channel: str          # api, native, screenshot, clean_scan, photo
    extractor: str = "extract-1.3"


def field_confidence(char_conf):
    return min(char_conf) if char_conf else 0.0


def normalize_address(raw):
    s = raw.upper().replace(".", " ")
    unit, m = "", UNIT.search(s)
    if m:
        unit, s = m.group(1), s[:m.start()] + s[m.end():]
    words = [SUFFIX.get(w, w) for w in s.split(",")[0].split()]
    zip5 = re.search(r"\b(\d{5})\b", s)
    return {"number": words[0] if words else "", "street": " ".join(words[1:]),
            "unit": unit, "zip": zip5.group(1) if zip5 else ""}


def read_amount(text):
    m = re.search(r"\$\s*([0-9OlSBZ,]+\.[0-9OlSBZ]{2})", text)
    if not m:
        return None
    return round(float(m.group(1).replace(",", "").translate(DIGITS)) * 100)  # cents


def repair_date_digits(text):
    """Fix OCR confusions inside numeric tokens only, so 'Oct' stays 'Oct'."""
    return re.sub(r"[0-9OlSBZ]{2,4}(?=[/\-\s]|$)",
                  lambda m: m.group(0).translate(DIGITS), text)


# ------------------------------------------------------------ more readers
DATE_FORMATS = {                       # parse by the format the source uses
    "iso": (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),          # carrier API
    "us": (r"(\d{1,2}/\d{1,2}/\d{4})", "%m/%d/%Y"),       # US proof of delivery
    "mon": (r"([A-Z][a-z]{2} \d{1,2}, \d{4})", "%b %d, %Y"),  # tracking page
}


def read_date(text, source_format):
    """ISO 8601 date, parsed with the format its source uses, or None."""
    pattern, fmt = DATE_FORMATS[source_format]
    m = re.search(pattern, repair_date_digits(text))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), fmt).date().isoformat()
    except ValueError:
        return None


def _like(word, target):
    """Tolerate one or two OCR errors in a keyword."""
    return SequenceMatcher(None, word, target).ratio() >= 0.75


def read_attestation(text):
    """signed, photo or none. 'Not required' is not a signature."""
    words = re.sub(r"[^A-Z ]", " ", text.upper()).split()
    if any(_like(w, "REQUIRED") for w in words):
        return "none"
    if words and _like(words[0], "SIGNED") and len(words) > 2:
        return "signed"
    if any(_like(w, "PHOTO") for w in words):
        return "photo"
    return None                                   # unreadable


def normalize_tracking(text):
    """Upper case, no spaces or punctuation: 'NP 7731 0429 8815.' -> 'NP773104298815'."""
    return re.sub(r"[^0-9A-Z]", "", text.upper())


def read_value(name, raw, date_format=""):
    """The canonical value of one field, or None if nothing usable was read."""
    if not raw:
        return None
    if name in ("ship_to", "delivered_to"):
        return normalize_address(raw)
    if name == "amount":
        return read_amount(raw)
    if name == "delivered_on":
        return read_date(raw, date_format)
    if name == "attested":
        return read_attestation(raw)
    raise ValueError(f"no reader for {name}")


def read_fact(name, raw, char_conf, doc_id, page, channel, date_format=""):
    value = read_value(name, raw, date_format)
    conf = field_confidence([c / 100 for c in char_conf]) if value is not None else 0.0
    return Fact(name, value, round(conf, 2), doc_id, int(page), channel)


def facts_from_readings(readings):
    """{case_id: {fact name: [Fact, ...]}} from readings.csv rows."""
    out = {}
    for r in readings.itertuples(index=False):
        conf = [int(c) for c in str(r.char_conf).split()] if isinstance(r.char_conf, str) \
            else []
        raw = r.raw_text if isinstance(r.raw_text, str) else ""
        fmt = r.date_format if isinstance(r.date_format, str) else ""
        fact = read_fact(r.field, raw, conf, r.doc_id, r.page, r.channel, fmt)
        out.setdefault(r.case_id, {}).setdefault(r.field, []).append(fact)
    return out


# ------------------------------------------------------------ OCR interface
class OcrEngine:
    """Anything that turns a page image into words with confidences."""

    def read(self, image_path):
        """Return a list of (text, confidence 0-1) per word, in reading order."""
        raise NotImplementedError


class TesseractEngine(OcrEngine):
    """Tesseract through pytesseract (optional; not needed for the chapter)."""

    def __init__(self, lang="eng"):
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError as exc:                     # degrade gracefully
            raise RuntimeError("pip install pytesseract pillow, and install the "
                               "Tesseract binary, to read real images") from exc
        self.lang = lang

    def read(self, image_path):
        import pytesseract
        from PIL import Image
        data = pytesseract.image_to_data(Image.open(image_path), lang=self.lang,
                                         output_type=pytesseract.Output.DICT)
        return [(w, max(float(c), 0) / 100) for w, c in zip(data["text"], data["conf"])
                if w.strip()]
