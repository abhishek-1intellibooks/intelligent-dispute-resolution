# Chapter 14: Cloud-Native Dispute Platform Architecture

This chapter turns the components of Chapters 8 to 13 into one platform that stays calm on the busiest day of the year. Intake acknowledges a claim in milliseconds and does the work afterwards. Every state change is written together with its event through a transactional outbox. Consumers are idempotent, with retries and a dead-letter queue. Workers behind the queue autoscale on event lag (KEDA), and a shared token budget with a priority lane protects the model provider's limit. `peak_day.py` simulates a normal day of 40,327 claims and a peak day of 159,803, minute by minute. It compares a synchronous monolith with event-driven intake, and four ways of staffing the drafting stage.

All data are synthetic, and every amount, price and result is illustrative.

## Files

| File | Purpose |
|------|---------|
| `events.py` | Listing 14.1: the `Event` envelope and `transition()`, which changes state and writes the outbox in one transaction. Also includes a sqlite-backed `LocalConnection` with the psycopg-style API, the schema, an outbox `relay()` and an in-memory event log partitioned by case. |
| `consumer.py` | Listing 14.2: the idempotent `handle()`, with `Retryable`, `MAX_ATTEMPTS = 5` and a dead-letter queue, plus a demo in which every event arrives twice. |
| `budget.py` | Listing 14.4: `TokenBudget`, a token bucket with a priority lane, plus an asyncio demo. |
| `peak_day.py` | The chapter's simulation. Its parameters are set at the top of the file. It produces Tables 14.4 and 14.6 and Figures 14.3 to 14.6. |
| `intake_service.py` | Event-driven intake (FastAPI): idempotency keys, case and `claim.received` written in one transaction, a 202 reply, and `/api/reconcile` for the reconciliation row of Table 14.7. |
| `loadtest/locustfile.py` | Listing 14.5: the Locust peak-day replay (`Claimant`, `PeakDay`). |
| `deploy/writer-scaledobject.yaml` | Listing 14.3: the KEDA rule for the Chapter 12 writer (min 2, max 20, lag 50, cooldown 300). |
| `deploy/writer-scaledobject-rate.yaml` | A variant that adds a rate trigger. This is the rule `peak_day.py` simulates. |
| `deploy/*-scaledobject.yaml` | KEDA rules for intake (request rate), case, triage, recovery, evidence (documents queued) and agent. |
| `deploy/k8s/*.yaml` | Namespace, Deployments, Services and the clock-scanner CronJob for intake, case and clocks (Ch. 2, 3, 8), triage (`chapter09/triage_service.py`), recovery (`chapter10/fight_or_accept.py`), evidence (`chapter11/evidence_pipeline.py`), writer (`chapter12/service.py`) and agent (`chapter13/agent.py`). Each worker Deployment runs an outbox-relay sidecar. |
| `deploy/kustomization.yaml` | `kubectl apply -k chapter14/deploy` applies everything. |
| `deploy/Dockerfile.intake`, `Dockerfile.triage`, `Dockerfile.worker` | Container images, built from the repository root. `Dockerfile.worker` takes `--build-arg CHAPTER=chapterNN`. |
| `deploy/worker.py` | Container entrypoint. `ROLE=consumer` runs `HANDLER` through `consumer.handle` on Kafka. `ROLE=relay` publishes the outbox. |
| `deploy/handlers.py` | Binds each earlier chapter's component to the event log, using the interfaces shown in the book's listings. |
| `deploy/clock_scanner.py` | Deadlines as data: emits `clock.at_risk` for open clocks due within 2 business days. |
| `deploy/schema.sql` | PostgreSQL 16 tables: cases, outbox, processed, clocks and case_history. |
| `tests/test_chapter14.py` | pytest: outbox atomicity, stale state, relay redelivery, duplicates, dead letters, token priority, intake idempotency and reconciliation, manifests, cost and queueing checks. |
| `peak_day_results.csv`, `arrivals_by_minute.csv`, `figures/` | Outputs of `peak_day.py`. |

## How to run

```bash
cd chapter14
python peak_day.py          # Tables 14.4, 14.6 and Figures 14.3-14.6 (about 10 s)
python events.py            # outbox: stale transition refused, relay crash -> duplicate publish
python consumer.py          # idempotent consumer: duplicates skipped, failures dead-lettered
python budget.py            # priority lane: urgent requests admitted first
python -m pytest -q tests
python -m py_compile loadtest/locustfile.py
```

To run the load test, install locust (`pip install locust`). It is listed in `requirements.txt` but is not needed for anything else.

```bash
uvicorn intake_service:app --port 8080
locust -f loadtest/locustfile.py --host http://localhost:8080 --headless
curl localhost:8080/api/reconcile     # claims accepted = cases created = claim.received events
```

To deploy, you need Docker, a Kubernetes cluster with KEDA, PostgreSQL 16 and a Kafka-compatible log such as Redpanda. Build the images from the repository root as each Dockerfile's header shows, create one `<service>-db` secret per service, apply `deploy/schema.sql`, then run `kubectl apply -k chapter14/deploy`.

## Chapter artifact

The event backbone (`events.py`, `consumer.py`), the autoscaling rules (`deploy/`), the shared token budget (`budget.py`) and the peak-day load test (`loadtest/`).

## Results (from `python peak_day.py`)

| Measure | Book | This code |
|---|---|---|
| Normal / peak day claims | 40,327 / 159,803 | 40,327 / 159,803 |
| Busiest minute, normal / peak | 82 / 271 | 86 / 272 |
| Monolith capacity | 148 claims/min | 148 claims/min |
| Monolith, peak day: median / p99 wait | 30 min / about 2 h | 31.9 min / 1.97 h |
| Claims over the 30 s app timeout | 82% (131,280) | 84% (133,994); falls behind at 08:41 |
| Event-driven intake p99 | about 0.18 s | 0.18 s normal day, 0.19 s peak day |

Table 14.4, the drafting stage on the peak day:

| Measure | Fixed 14 | Fixed 40 | Autoscaled 2-40 | Autoscaled + priority | Capped at 20 |
|---|---|---|---|---|---|
| Drafted within 15 min | 21.6% (book 23.1%) | 79.8% (80.7%) | 79.8% (80.7%) | 81.7% (82.5%) | 79.8% |
| At-risk within 15 min | 21.7% (23.4%) | 79.8% (81.2%) | 79.8% (81.2%) | 100.0% (100.0%) | 79.8% |
| Slowest 5% waited (min) | 138 (137) | 27 (26) | 27 (26) | 32, at-risk 0 (32, under 1) | 27 |
| Largest backlog | 19,767 (19,543) | 5,592 (5,324) | 5,592 (5,324) | 5,592 (5,324) | 5,592 |
| Still waiting at midnight | 5,236 (5,112) | 0 | 0 | 0 | 0 |
| Worker-hours | 336 (336) | 960 (960) | 395 (399) | 395 (399) | 306 (301) |

On the normal day the autoscaled pool used 104 worker-hours (book: 96), against 336 for the fixed pool. On the peak day the autoscaled pool used 41% of the peak-sized pool's worker-hours (book: 42%).

Table 14.6, cost per claim: agent 7.29 cents, drafting 2.70, storage 0.77, document reading 0.54, observability 0.40 and compute 0.05, for a total of 11.8 cents. Language-model tokens are 85% of the total and the agent alone 62%. All of these match the book.

Figure 14.6, p99 reply time relative to idle, assuming exponential service times:

| Design | At 90% load | At 95% | At 99% |
|---|---|---|---|
| Monolith | 1.14 | 1.57 | 6.42 |
| Event-driven intake | 1.00 | 1.01 | 1.19 |

### Deviations from the book

- **Autoscaling rule.** With a lag-only rule (lag / 50, as in Listing 14.3), the simulated autoscaler builds a standing backlog of several hundred claims before it reaches 20 workers. Its service is then worse than the peak-sized pool's (76.6% within 15 minutes, with 133 claims left at midnight), whereas the book reports identical service. `peak_day.py` therefore scales on the larger of the lag trigger and a rate trigger: arrivals per minute divided by (10 × 0.9). This rule reproduces the book's identical service and its worker-hours to within a few percent. Listing 14.3 is reproduced unchanged in `deploy/writer-scaledobject.yaml`, and the two-trigger rule is in `deploy/writer-scaledobject-rate.yaml`.
- **At-risk claims within a minute.** Under the priority lane, 100% of at-risk claims were drafted within a minute, against the book's 95%, because the simulation works in whole minutes.
- **Figure 14.6.** With exponential service, the monolith's slowest replies grow by 14% at 90% load and by 57% at 95%. The book says they grow "by half" at 90%. The event-driven curve matches the book: flat at 90% and bending only above 99%.
- **Deployment adapters.** `deploy/handlers.py` assumes the earlier chapters' listing interfaces, such as `fight_or_accept(cases)` and `build_evidence(case, readings, review)`. The adapters run only inside the containers. Kafka, PostgreSQL and Kubernetes are not exercised by the local tests. The local tests cover the patterns themselves through the sqlite adapter.
