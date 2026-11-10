# Chapter 2: Understanding the Rules of the Game: Regulation and Network Frameworks

📖 **Read the chapter:** [CHAPTER.md](CHAPTER.md)

This chapter sets out the rules every automated dispute decision must respect. They come in three layers, and each layer runs its own kind of clock:

- **Law** (statutory clocks): Regulation E, Regulation Z, UK APP reimbursement.
- **Network and scheme rules** (network clocks): Visa, Mastercard, Nacha, FedNow/RTP.
- **Institutional policy** (policy clocks).

This folder holds the deadlines **as data** in `timelines.yaml`. Every entry carries its source, edition, effective date and last-verified date. `clocks.py` turns a claim's start events into a dated list of obligations. The rules are stated as of October 2026. This is illustrative companion material, not legal advice.

## Files

| File | Purpose |
|---|---|
| `timelines.yaml` | 27 regulatory, network and policy deadlines. Each has `id`, `layer`, `source`, `edition`, `applies_to`, `starts_on`, `amount`, `unit`, `consequence`, `effective_from`, `last_verified`, and optionally `when_any` / `unless` / `note` |
| `clocks.py` | The loader from the chapter (`BDAY`, `add_time`, `deadlines`), plus `load_rules` and `stale_rules`. `python clocks.py` runs the worked example |
| `deadlines.py` | Alias of `clocks.py`. Chapter 3's "What you now have" list calls the module `chapter02/deadlines.py` |
| `tests/test_clocks.py` | Reproduces the chapter's printed output. Also checks the MLK Day holiday, the flags, and that every entry has source, edition and verification date |
| `requirements.txt` | Packages for this chapter |

## How to run

```bash
cd chapter02
python clocks.py
python -m pytest -q tests
```

## Chapter artifact

The rules as data: `timelines.yaml` together with the loader. The file covers:

- **Regulation E:**
  - determine within 10 business days, or extend to 45 days
  - 90-day and 20-business-day variants for new accounts and POS or foreign transfers
  - notify within 2 business days of a provisional credit
  - report within 3 business days of completing the investigation
  - written confirmation, the notice window and the liability tier
- **Regulation Z:** acknowledge in 30 days, resolve within 90 days, and the notice window.
- **Visa:** the 13.1 filing window, plus the dispute response and pre-arbitration windows.
- **Mastercard:** the 4853 filing window, plus the second presentment and pre-arbitration windows.
- **Nacha:** R10/R11 and R29 returns.
- **UK APP reimbursement:** 5 and 35 business days, and the 13-month claim window.
- **Issuer policy:** illustrative policy clocks.

## Results (as printed by the code)

A claim received on Monday 5 January 2026, for a transaction processed on 20 December 2025:

```
credit_card
  2026-02-04  reg_z_acknowledge    12 CFR 1026.13(c)(1)
  2026-04-05  reg_z_resolve        12 CFR 1026.13(c)(2)
  2026-04-19  visa_13_1_filing     Visa Core Rules, 11.10.2
debit_card
  2026-01-20  reg_e_determine      12 CFR 1005.11(c)(1)
  2026-02-19  reg_e_extended       12 CFR 1005.11(c)(2)
  2026-04-19  visa_13_1_filing     Visa Core Rules, 11.10.2
```

This matches the chapter line for line. The Regulation E determination falls on 20 January because Martin Luther King Jr. Day is not counted. All 35 tests pass.

## Deviations from the listing

- `add_time` wraps `start` in `pd.Timestamp` before adding the business-day offset. Without this, the listing tries to add a pandas offset to a plain `datetime.date`.
- `deadlines()` defaults `path` to the `timelines.yaml` next to the module, so it runs from any folder.
- `deadlines()` also takes an optional `flags=()` argument that honors `when_any` and `unless`. For example, `flags={"pos_or_foreign"}` replaces the 45-day extension with 90 days. Without flags, the output is the same as the book's.
- Policy rules start on `case_opened`. The worked example does not supply that event, so its output has no policy rules, as in the book.
- Business days follow the US federal holiday calendar. An institution substitutes its own calendar, and the UK entries would need a UK calendar.
