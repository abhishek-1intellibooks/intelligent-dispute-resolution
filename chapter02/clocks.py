"""Turn a claim into a dated list of obligations (Chapter 2).

The rules live in timelines.yaml; this module only does date arithmetic.
`add_time` and `deadlines` follow the chapter's listing. Two additions keep the
book's behavior unchanged for the default call:

* `path` defaults to the timelines.yaml next to this file, so the module works
  from any working directory;
* an optional `flags` argument honors the `when_any` / `unless` fields used by
  the conditional Regulation E entries (new account, point-of-sale or
  out-of-state transfers). With no flags those entries are skipped, exactly as
  a rule with an unknown start event is skipped.

Run:  python clocks.py
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

HERE = Path(__file__).resolve().parent
RULES_PATH = HERE / "timelines.yaml"

BDAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())


def add_time(start: date, amount: int, unit: str) -> date:
    if unit == "business_days":
        return (pd.Timestamp(start) + amount * BDAY).date()
    return start + timedelta(days=amount)


def load_rules(path=RULES_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["rules"]


def _conditions_met(rule: dict, flags: set[str]) -> bool:
    when_any = rule.get("when_any")
    if when_any and not flags.intersection(when_any):
        return False
    return not flags.intersection(rule.get("unless", []))


def deadlines(product, events, path=RULES_PATH, flags=()):
    rules = load_rules(path)
    flags = set(flags)
    out = []
    for r in rules:
        if (product in r["applies_to"] and r["starts_on"] in events
                and _conditions_met(r, flags)):
            due = add_time(events[r["starts_on"]], r["amount"], r["unit"])
            out.append((r["id"], r["source"], due))
    return sorted(out, key=lambda t: t[2])


def stale_rules(as_of: date, max_age_days: int = 180, path=RULES_PATH) -> list[str]:
    """Rule ids whose last_verified date is older than max_age_days."""
    return [r["id"] for r in load_rules(path)
            if (as_of - date.fromisoformat(r["last_verified"])).days > max_age_days]


def main() -> None:
    # A claim received on Monday 5 January 2026 for a transaction processed on
    # 20 December 2025 (the chapter's worked example).
    events = {"notice_received": date(2026, 1, 5),
              "processing_date": date(2025, 12, 20)}
    for product in ("credit_card", "debit_card"):
        print(product)
        for rule_id, source, due in deadlines(product, events):
            print(f"  {due}  {rule_id:20s} {source}")


if __name__ == "__main__":
    main()
