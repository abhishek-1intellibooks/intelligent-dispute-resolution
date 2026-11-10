# Chapter 6: Friendly Fraud and First-Party Misuse

This chapter separates first-party misuse from the claims that resemble it: third-party compromise and merchant failure. It computes five signals per cardholder over a 90-day window that ends on a fixed as-of date:

- claims in the window
- not-received share
- top-merchant share
- proof rate
- median gap between claims

Explicit points combine the signals into a tier (standard, clarify or review), and each tier comes with readable reasons. A contest threshold, A > (c + qV) / p, weighs the cost of contesting a claim against the value of the customer relationship. The tier only routes a claim to a queue; it never decides the claim. All data are synthetic and all amounts illustrative.

## Files

| File | Purpose |
|---|---|
| `make_data.py` | Seeded extension of `../chapter01/disputes_sample.csv` with four columns: `card_id`, `merchant_id`, `reason`, `delivery_confirmed` |
| `disputes_extended.csv` | The same 5,000 rows as Chapter 1, plus the four columns |
| `first_party_signals.py` | The chapter artifact: `build_signals`, `score_signals` and `contest_threshold` from the listings, plus a demo `main()` |
| `tests/test_first_party_signals.py` | Tests the Table 6.5 rows, the worked example, merchant concentration, the as-of anchor and the Table 6.3 thresholds |
| `pytest.ini` | Silences the expected warning from taking the median gap of a single-claim cardholder |
| `requirements.txt` | Packages for this chapter |

## How to run

```bash
cd chapter06
python make_data.py               # needs ../chapter01/disputes_sample.csv
python first_party_signals.py
python -m pytest -q tests
python build_notebook.py           # (re)build the signal notebook
jupyter notebook first_party_signals.ipynb
```

`first_party_signals.ipynb` is the signal notebook. It walks through dispute concentration, the signals and tiers (Table 6.5), the worked example (card c1024) and the contest thresholds (Table 6.3). It is stored with its outputs already run.

## Chapter artifact

`first_party_signals.py` produces per-cardholder signals, a tier with reasons and the contest threshold.

## Results (as printed by the code)

| Figure | Book | Code |
|---|---|---|
| Share of disputes raised by the top 3% of disputing cardholders | about 11% | 11.1% |

The data has 4,300 disputing cardholders, so the top 3% is 129 of them. 90.7% of cardholders raise a single claim.

Scoring first-party claims as of 2026-09-30 covers 416 cardholders: 398 standard, 6 clarify and 12 review.

Table 6.5 is reproduced exactly:

| Card | Claims | Not received | Top merchant | Proof rate | Gap (days) | Points | Tier |
|---|---|---|---|---|---|---|---|
| c741 | 6 | 0.83 | 0.17 | 0.67 | 6.0 | 7 | review |
| c2677 | 3 | 1.00 | 0.33 | 0.33 | 6.5 | 4 | clarify |
| c3578 | 2 | 0.50 | 0.50 | 1.00 | 57.0 | 2 | standard |

The worked example is card c1024. It has 4 claims, a not-received share of 1.0, a top-merchant share of 0.25, a proof rate of 0.75 and a 7-day median gap. It scores 7 points and goes to review, with its reasons.

The contest threshold is $95 when the relationship has no value. Table 6.3 is reproduced:

| Relationship value V | Threshold at p = 0.42 | Threshold at p = 0.70 |
|---|---|---|
| $150 | $113 | $68 |
| $2,000 | $333 | $200 |
| $600 | $167 | $100 |

Classification has to come first. Without the first-party filter, 11 more cardholders would leave the standard tier, and 10 of them are bursts of unauthorized claims (card compromise, not misuse).

All 15 tests pass.

## Notes and deviations

- `make_data.py` **plants** cards c741, c2677 and c3578 (Table 6.5) and c1024 (the worked example). It places their claims on existing first-party rows with exact day gaps, so that the chapter's illustrative rows come out exactly.
- The rest of the card structure is randomly generated from a fixed seed. It includes first-party pattern cards, bursts of unauthorized claims and a failing merchant, `m0042`.
- `build_signals` writes `pd.Timedelta(window_days, unit="D")` instead of `pd.Timedelta(days=window_days)`. The result is the same, but the keyword form raises a deprecation warning with pandas 2.3 and NumPy 2.5.
- `main()` scores first-party claims only, following the chapter's rule that the family label decides which claims are scored.
- In the Table 6.3 "Treatment" column, a claim counts as "close to the line" when its amount is within 25% of the p = 0.42 threshold.
- The chapter refers to a signal notebook in this README. No notebook is included; `python first_party_signals.py` prints the same tables.
