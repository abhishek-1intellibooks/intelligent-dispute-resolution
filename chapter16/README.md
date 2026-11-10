# Chapter 16: Case Studies and the Future of Disputes

The final chapter looks at the whole platform. Three composite case studies show the book's components at work. A look at agentic commerce shows how disputes change when software buys on customers' behalf, which is where `mandate.py` checks a purchase against the signed mandate its customer gave. The chapter then sets out a roadmap with exit criteria (`roadmap.yaml`) and ends with the capstone, `run_month.py`. The capstone runs one synthetic month of 60,000 claims through the components of Chapters 8 to 15 and through a manual baseline. It is self-contained. It does not import the earlier chapters' code but takes each parameter the book quotes as a named constant, with its source chapter given in a comment (Table 16.5).

All data are synthetic, and every amount and result is illustrative. The case studies in the chapter are composites.

## Files

| File | Purpose |
|------|---------|
| `mandate.py` | Listing 16.1: `Mandate` and `check_purchase()`. It verifies the customer's Ed25519 signature, then checks agent, amount, category, expiry and confirmation. It also runs a demo on 10,000 synthetic agent purchases with injected faults, and the worked example. |
| `ed25519_fallback.py` | A pure-Python Ed25519 (RFC 8032) with the same API, used only when `cryptography` is not installed. It is verified against RFC 8032 test vector 1. |
| `run_month.py` | Listing 16.2: the capstone. It contains `run_month()` (as in the listing), `Platform`, `load_month`, `compare`, a hash-chained `AuditTrail`, and all the parameters as named constants. |
| `config/production-like.yaml` | Parameter overrides read by `Platform.from_config`. Edit them to rerun the month with your own rates and times. |
| `claims_month.jsonl` | The synthetic month (60,000 claims, about 9 MB). `run_month.py` generates it with seed 16 if it is missing. |
| `month_summary.csv` | Table 16.6, as written by the last run. |
| `roadmap.yaml` | Table 16.4 as data: five phases (including the throughout-the-programme "Scale and govern"), each exit criterion linked to the check that proves it. |
| `tests/test_chapter16.py` | pytest: mandate checks, the worked example, the RFC 8032 vector, the roadmap, the config, and a 2,000-claim month with an audit-tamper test. |

## How to run

```bash
cd chapter16
python mandate.py             # about 20 s with the pure-Python fallback, faster with cryptography
python run_month.py           # about 25 s; generates claims_month.jsonl on first run
python -m pytest -q tests
```

`pip install cryptography` makes `mandate.py` use the real library. Without it, the fallback is used and the results are the same.

## Chapter artifact

`run_month`: the end-to-end capstone.

## Results

**`python mandate.py`**

10,000 synthetic agent purchases; 1,428 outside their mandates (book 1,412). By reason:

| Reason | This code | Book |
|---|---|---|
| Over the amount allowed | 619 | 601 |
| After expiry | 392 | 344 |
| Outside the allowed categories | 303 | 316 |
| Without a required confirmation | 289 | 307 |

A mandate whose payload was altered after signing is rejected with "the mandate's signature is not the customer's". The worked example ($249 against a $150 mandate, confirmation required above $135) returns exactly the book's two reasons:

- "total 249.00 over the limit of 150.00"
- "no customer confirmation where the mandate required one"

**`python run_month.py`** (Figure 16.5)

- 50,466 claims (84.1%) finished without a person (book 50,461).
- 9,534 reached a person (book 9,539).
- 5,989 (10.0%) were flagged for first-party review (book 6,078).
- 24.2% were touched by a person in all (book 24.4%).

The audit trail held 245,989 records and verified intact, with 24 checkpoints.

Table 16.6:

| Measure | Manual (book) | Manual (code) | Platform (book) | Platform (code) |
|---|---|---|---|---|
| Analyst hours | 25,000 | 25,000 | 3,239 | 3,196 |
| Full-time analysts (140 h) | 178.6 | 178.6 | 23.1 | 22.8 |
| Analyst minutes per claim | 25.0 | 25.0 | 3.2 | 3.2 |
| Handling cost per claim | $18.75 | $18.75 | $2.55 | $2.52 |
| Median days to resolution or decision | 9.1 | 9.1 | 1.8 | 1.7 |
| Slowest 10% (days) | 14.8 or more | 14.6 or more | 5.9 or more | 5.3 or more |
| More than 14 calendar days | 13.5% | 12.4% | none | 0.0% |
| Touched by a person | 100% | 100% | 24.4% | 24.2% |

Figure 16.3, analyst hours on the platform:

| Activity | Hours |
|---|---|
| First-party review | 1,198 |
| Decisions on escalated cases | 1,028 |
| Approving letters | 727 |
| Other escalations | 243 |

Reading, assembling and writing fall to zero, against 13,500 and 6,250 hours under the manual baseline.

### Assumptions and deviations

- **Labelled assumptions.** Table 16.5 labels the parameters that are not inherited from earlier chapters as assumptions, and `run_month.py` labels them the same way. They are: the family mix, the 35% issuer-liability share, the 12 review minutes, $45 an hour and 140 hours a month. On top of these, the code adds these assumptions:
  - the timing distributions (`PLATFORM_TIMES`, `MANUAL_TIMES`);
  - the claim amounts (lognormal, median $95), which give about 8.4% of contestable unauthorized claims above the $500 agent limit;
  - a 5-day merchant inquiry window, which produces the step at five days in Figure 16.6;
  - one letter approval of 3 minutes for each claim a person decides or reviews;
  - a simple first-party score whose 0.21 threshold flags about 10% of claims;
  - the split of the 25 manual minutes across activities.
- **Tuning.** The timing parameters were tuned so that the manual median matches 9.1 days. The platform's slowest 10% start at 5.3 days, against the book's 5.9.
- **No imports from earlier chapters.** `run_month.py` represents each component by its measured rate rather than running it. For example, the agent finishes 71.3% of merchant-related claims, escalates 22.1% as adverse and 6.5% for other reasons (Chapter 13). This is deliberate: the capstone is self-contained and does not import Chapters 8 to 13. In the book's listing, `Platform`, `load_month` and `compare` come from `dispute_platform` and `reporting` modules; here they are defined in `run_month.py`.
