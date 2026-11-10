# Chapter 9: ML for Classification and Triage

This chapter makes the first decisions about a claim when it arrives. It treats triage as three
estimates and one policy that combines them. The estimates are the claim's family (unauthorized,
defective or first-party), its expected effort, and its risk of missing the ten-business-day clock;
the policy sets the priority band and the queue. A logistic regression on intake-only features
(guarded by `intake_view`) is compared with reason-code rules and a gradient-boosted challenger,
abstains below a confidence of 0.70, and feeds an SLA-risk model. A queue replay of November and
December shows what ordering by least slack is worth. The models are served by a FastAPI service
that returns reasons and model versions with every decision.

All data are synthetic and every result, including the dollar costs, is illustrative.

## Files

| File | Purpose |
|---|---|
| `make_triage_data.py` | Seeded generator for `claims_closed.csv`: 24,000 closed card claims in 2025, with intake fields, queue depth and closure outcomes. It runs the year first in, first out through `queue_sim.py` and applies 5% label noise |
| `claims_closed.csv` | The generated dataset (7 MB) |
| `capacity.csv` | Starts per business day used in the historical run, which the replay reuses |
| `queue_sim.py` | Business-day queue simulator (`CLOCK_DAYS`, `DAILY_STARTS`, `as_day`, capacity profile, `run`) |
| `features.py` | Listing 9.1: `AVAILABLE_AT`, feature groups, `intake_view`, `preprocessor` |
| `train_classifier.py` | Listings 9.2 and 9.3: time split, baselines, logistic regression and boosted trees, cost per 1,000, abstention curve, feature-group ablation; saves `triage_model.joblib` and `classifier_results.json` |
| `priority.py` | Listing 9.4: `expected_work`, `sla_frame`, `band`, `route` |
| `sla_risk.py` | Effort table (9.8), SLA-risk model, calibration, priority bands (9.9) and the four-policy replay (9.10); saves `sla_model.joblib` and `sla_results.json` |
| `triage_service.py` | Listing 9.5: the FastAPI service (`POST /triage`) |
| `demo_request.py` | Sends the worked-example claim, in-process via TestClient or to a running server with `--url` |
| `test_triage.py` | pytest: the late-feature guard, bands, abstention routing, and the service including request validation |

## How to run

```bash
cd chapter09
python make_triage_data.py      # optional: claims_closed.csv and capacity.csv are committed
python train_classifier.py      # about 1 minute
python sla_risk.py
python demo_request.py          # in-process TestClient
# or against a live server:
uvicorn triage_service:app --port 8000
python demo_request.py --url http://127.0.0.1:8000
python -m pytest -q
```

## Chapter artifact

`chapter09/triage_service.py`: classifies a claim, scores its deadline risk, assigns a priority
band and routes it to a queue, with reasons and model versions.

## Results (as printed by the code; book values in brackets)

Split: train 15,731 / validation 3,961 / test 4,308 (exactly as in the book). Families over the year:
38.6% first-party, 33.6% unauthorized and 27.8% defective [38/34/28]. 20.3% of claims are coded Other [one in five].

Table 9.4, test months (1,698 first-party [1,602]):

| Approach | Accuracy | Macro F1 | Recall unauth. | Recall defective | Recall first-party | Cost / 1,000 |
|---|---|---|---|---|---|---|
| Reason-code rule | 49.1% [50.8] | 0.41 [0.42] | 76.5% [75.5] | 86.9% [87.4] | 0.0% [0.0] | $18,186 [$18,777] |
| Rule + first-party points | 55.1% [53.0] | 0.52 [0.47] | 76.4% [75.3] | 85.5% [86.3] | 16.3% [7.2] | $16,959 [$18,377] |
| Logistic regression | 89.0% [89.7] | 0.89 [0.90] | 92.9% [94.0] | 86.1% [83.5] | 87.6% [90.3] | $7,021 [$7,071] |
| Gradient-boosted trees | 89.0% [89.6] | 0.89 [0.89] | 92.7% [93.8] | 86.7% [83.2] | 87.3% [90.6] | $7,055 [$7,293] |

The logistic regression's largest confusion is between defective and first-party claims: 115 defective
claims predicted first-party and 130 first-party claims predicted defective [158 / 92]. 71 unauthorized
claims were predicted first-party [65].

Table 9.6, ablation (accuracy): all 89.0%, without narrative 76.3% [77.5], narrative only 85.2% [85.5],
without intake_reason 88.9% [89.6], without customer history 87.9% [88.8], without linkage 88.4% [89.1].

Table 9.7, abstention: at τ = 0.7, 87.5% routed automatically at 92.3% accuracy and 12.5% sent to review
[85.0% / 94.3%]. At τ = 0.9: 59.2% routed at 94.2% [66.9% / 96.1%].

Table 9.8, effort in business days (training months), with the record in hand / in hand and flagged /
missing / missing and flagged: defective 1.6 / 3.6 / 4.4 / 6.4, first-party 2.5 / 4.5 / 2.5 / 4.5,
unauthorized 2.5 / 4.4 / 2.5 / 4.6.

SLA risk: coefficients are slack −1.46, queue 1.53 and effort 1.94 (signs as in the book, with effort
weighted most). Test AUC is 0.94 [0.93], and the riskiest 10% hold 70% of breaches [76%]. The model
overstates risk in the 5–20% band (predicted 10.8%, observed 7.0%) [9.6% versus 3.9%]. With slack held
at 9 days, a five-day claim reaches even odds behind 5.5 days of queue [about 4.5], and a two-day claim
behind 9.5 days [more than 9].

Table 9.9, bands (test months): P1 506 claims (11.7%), 185 of them breached under first in, first out
[484, 197]; P2 366 (8.5%), 72 breached [357, 84]; P3 3,436, 66 breached [3,467, 49]. P1 and P2 together
hold 257 of 323 breaches [281 of 330].

Table 9.10, November and December replay:

| Policy | Breaches | Rate | Unauthorized breached | 95th-percentile wait (calendar days) |
|---|---|---|---|---|
| First in, first out | 323 [330] | 7.5% [7.7] | 50 [75] | 9 [10] |
| Earliest due date | 309 [313] | 7.2% [7.3] | 51 [66] | 9 [10] |
| Least slack (predicted effort) | 94 [115] | 2.2% [2.7] | 16 [25] | 10 [11] |
| Least slack (perfect foresight) | 0 [0] | 0.0% | 0 | 10 [11] |

Worked example (Table 9.11), from `demo_request.py`, both in-process and against a live uvicorn server:
family defective with confidence 0.79 (first-party 0.20, unauthorized 0.01) [0.89]. The top reasons
are narrative +1.79, prior_disputes_12m +0.19 and delivery_status +0.11 [narrative +1.57,
prior_disputes +0.13, mcc_group +0.05]. The queue is merchant_disputes [same]. The model versions are
triage-family-1.0 and triage-sla-1.0.

### Gaps against the book

- The worked example scores an SLA risk of 0.05, which puts it in P3. The book reports 0.22 and P2. The
  inputs are the same (10 days of slack, 5.5 days of queue, about 4 days of expected effort), but this
  synthetic SLA model is steeper on slack, so the example falls below the 20% threshold.
- Abstention coverage at high thresholds is lower than in the book, because the probabilities are less
  sharp.
- The "Rule + first-party points" baseline recovers more first-party claims (16%) than the book's 7%.
- The replay uses only the claims in `claims_closed.csv`. The historical run that produced it also
  simulated Nov–Dec 2024 and January 2026 arrivals, so the queue is full at the start and does not run
  dry at the end. Under first in, first out the replay reproduces the history exactly. Under the other
  policies, claims from late December do not compete with January arrivals.
- `preprocessor()` takes an optional `columns` argument, which is not in Listing 9.1, so that the
  ablation can drop feature groups. Model files load relative to the script folder.
- With numpy 2 and pandas 2.3 you may see a harmless numpy `DeprecationWarning` from inside pandas.
