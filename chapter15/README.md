# Chapter 15: Security, Compliance and Responsible AI

📖 **Read the chapter:** [CHAPTER.md](CHAPTER.md)

This chapter adds the controls that let an institution answer a regulator's request completely, quickly and truthfully. It turns a logistic model's score into specific reason codes. It reports flag and error rates by customer segment, and shows how two plausible proxy features made a first-party review flag treat older customers and second-language writers less favourably, although neither attribute was a feature. It replaces a redactor that missed half the card numbers with one that finds all of them and keeps order numbers intact. It adds a hash-chained audit log with write-once checkpoints, and a model card for Chapter 10's win model. The chapter describes regulatory expectations in general terms for engineers. It is not legal advice.

All data are synthetic, and every result is illustrative.

## Files

| File | Purpose |
|------|---------|
| `reasons.py` | Listing 15.1: `reason_codes()`, the specific reasons that raised a logistic model's score (contribution = coefficient × standardized value). It also has `contributions()` for Figure 15.2. `REASON_TEXT` has extra entries for the two proxy features, so that the earlier model can be explained too. |
| `fairness.py` | Listing 15.2: `fairness_report()`, which gives flag rate, wrongly-flagged rate (FPR), misuse found (TPR), ratios to a reference segment, and a minimum-size marker for each segment. |
| `redact.py` | Listing 15.3: `redact()` (version 3: separators, Luhn check, card-network prefix, label exception, emails and phones), with versions 1 and 2 kept for comparison. |
| `audit.py` | Listing 15.4: `AuditLog` and `verify()`, plus `MemoryStore` and `WriteOnceCheckpoints` as local stand-ins for the table and for object-lock storage. |
| `model_card.yaml` | Listing 15.5: the model card for `outcome-win-probability` (`outcome-1.0`). |
| `governance_demo.py` | Produces the chapter's results: 20,000 synthetic claims with age band and language preference, both versions of the flag, reason codes, the redaction test, the audit-log test and the model-card check. |
| `tests/test_chapter15.py` | pytest tests for each module. |
| `governance_claims.csv` | The 20,000 synthetic claims (written by `governance_demo.py`). |
| `fairness_report.csv` | The fairness report for the live flag (proxies removed). |
| `narratives.csv` | The 2,000 synthetic narratives used for Table 15.7. |

## How to run

```bash
cd chapter15
python governance_demo.py     # about 25 s; writes the three CSV files
python -m pytest -q tests
```

## Chapter artifact

The audit trail (`audit.py`), the fairness report (`fairness.py`) and the model card (`model_card.yaml`), together with reason codes and redaction.

## Results (from `python governance_demo.py`)

Misuse is 8.0% overall, and by construction it is equal across segments: 8.0%, 7.9% and 8.3% by age band, and 8.0% and 7.9% by language. Table 15.4 shows the flag on 8,079 held-out test claims, with 10% flagged:

| Measure | With proxies (book) | With proxies (code) | Proxies removed (book) | Proxies removed (code) |
|---|---|---|---|---|
| AUC | 0.938 | 0.945 | 0.917 | 0.930 |
| Share of misuse flagged | 71.5% | 72.9% | 66.1% | 69.1% |
| Wrongly flagged, 35 to 64 | 3.2% | 3.5% | 4.8% | 4.7% |
| Wrongly flagged, 65 and over | 8.2% | 8.4% | 5.2% | 4.8% |
| Wrongly flagged, English | 3.7% | 3.8% | 5.0% | 5.0% |
| Wrongly flagged, other language | 9.3% | 8.9% | 4.9% | 4.3% |
| Flag-rate ratio, 65+ to 35-64 | 1.67 | 1.61 | 1.10 | 1.04 |
| Flag-rate ratio, other to English | 1.68 | 1.74 | 1.01 | 1.03 |
| Wrong-flag ratio, 65+ / other language | 2.6 / 2.5 | 2.38 / 2.33 | about 1 | 1.01 / 0.86 |

**Figure 15.2.** One flagged claim was filed 58 days after purchase, with one earlier dispute and a known device. It scored 0.47 against a threshold of 0.19 (book: 0.29 against 0.21). Its contributions to the log-odds were: days to file +2.80, earlier dispute +1.02, amount −0.14 and device −0.18. The code returned two reasons: "The claim was made 58 days after the purchase" and "1 other disputes were made in the last 12 months".

**Table 15.7** (2,000 synthetic narratives):

| Version | Card numbers removed | Order numbers destroyed |
|---|---|---|
| 1 | 52.4% of 595 (book 53.5% of 587) | 100% of 600 (book 100% of 606) |
| 2 | 100% | 11.5% (book 7.1%) |
| 3 | 100% | 0.0% |

Version 3 also removed 346 email addresses and 300 telephone numbers.

**Audit log.** 100,000 records were written in about 3.2 s and verified in about 2.1 s (book: under 1 s and 0.7 s, so timings depend on the machine). After record 42,017 was edited to a score of 0.999, verification stopped at exactly 42,017. A forger who recomputes every later hash passes verification without checkpoints, but with the 10 write-once checkpoints verification stops at 49,999, the first checkpoint after the edit.

**Model card.** All the sections of Table 15.8 are present. `model_card.yaml` parses with PyYAML.

### Deviations from the book

- The fairness numbers come from a synthetic generator whose strengths are set by `GEN` in `governance_demo.py`, tuned toward Table 15.4. The pattern is reproduced: with proxies, the wrong-flag rate is about 2.4 times higher for both groups; without them, it is close to parity, at a cost of about 4 points of detection. The individual figures differ by up to 1.3 points, and the proxy-free AUC is 0.930 against the book's 0.917.
- Version 2 of the redactor destroyed 11.5% of order numbers, against the book's 7.1%. About 10% of random 16-digit numbers pass the Luhn checksum by chance, so 7.1% would be an unusually low draw.
- `model_card.yaml` quotes the `owner` value. The listing's unquoted `owner: Recovery analytics; validator: Model Risk (independent)` is not valid YAML, because a plain scalar cannot contain `: `. All other lines are unchanged.
