"""A tiny formula evaluator for business_case.xlsx, used only by the tests.

openpyxl writes formulas but does not calculate them, so the tests recompute
the workbook here. It supports exactly what the generator uses: cell and
range references (optionally sheet-qualified, optionally absolute), + - * /
^, comparisons, string literals and the functions SUM, IF, NPV, ROUND, AND
and COUNTIF. Anything else raises, so an unsupported formula cannot pass
silently.
"""

import re

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

_STR = re.compile(r'"[^"]*"')
_RANGE = re.compile(r"(?:([A-Za-z_]\w*)!)?\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?(\d+)")
_REF = re.compile(r"(?:([A-Za-z_]\w*)!)?\$?\b([A-Z]{1,3})\$?(\d+)\b")


def _flat(args):
    for a in args:
        if isinstance(a, list):
            yield from _flat(a)
        else:
            yield a


def _num(values):
    return [v for v in _flat(values) if isinstance(v, (int, float)) and not isinstance(v, bool)]


FUNCS = {
    "SUM": lambda *a: sum(_num(a)),
    "IF": lambda c, a, b=False: a if c else b,
    "NPV": lambda r, *cf: sum(v / (1 + r) ** (i + 1) for i, v in enumerate(_num(cf))),
    "ROUND": lambda x, n=0: round(x, int(n)),
    "AND": lambda *a: all(_flat(a)),
    "COUNTIF": lambda rng, crit: sum(1 for v in _flat([rng]) if v == crit),
}


class Workbook:
    def __init__(self, path):
        self.wb = load_workbook(path)          # formulas, not cached values
        self.cache = {}

    def value(self, sheet, ref):
        key = (sheet, ref)
        if key not in self.cache:
            raw = self.wb[sheet][ref].value
            self.cache[key] = self._eval(sheet, raw[1:]) if isinstance(raw, str) and raw.startswith("=") else raw
        return self.cache[key]

    def _range(self, sheet, a, b):
        ca, ra = re.match(r"([A-Z]+)(\d+)", a).groups()
        cb, rb = re.match(r"([A-Z]+)(\d+)", b).groups()
        return [self.value(sheet, f"{get_column_letter(c)}{r}")
                for r in range(int(ra), int(rb) + 1)
                for c in range(column_index_from_string(ca), column_index_from_string(cb) + 1)]

    def _eval(self, sheet, formula):
        strings = []

        def keep(m):
            strings.append(m.group(0))
            return f"__S{len(strings) - 1}__"

        def keep_code(code):
            strings.append(code)
            return f"__S{len(strings) - 1}__"

        expr = _STR.sub(keep, formula)
        expr = _RANGE.sub(lambda m: keep_code(
            f'_rng("{m.group(1) or sheet}","{m.group(2)}{m.group(3)}","{m.group(4)}{m.group(5)}")'),
            expr)
        expr = _REF.sub(lambda m: keep_code(
            f'_ref("{m.group(1) or sheet}","{m.group(2)}{m.group(3)}")'), expr)
        expr = expr.replace("<>", "!=").replace("^", "**")
        expr = re.sub(r"(?<![<>!=])=(?!=)", "==", expr)
        for i in reversed(range(len(strings))):
            expr = expr.replace(f"__S{i}__", strings[i])
        names = dict(FUNCS, _ref=self.value, _rng=self._range)
        return eval(expr, {"__builtins__": {}}, names)  # noqa: S307 - trusted, generated workbook
