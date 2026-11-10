# Chapter 12: Generative AI for Dispute Operations

This chapter uses a language model for the writing around each dispute decision: case summaries, customer letters and representment narratives. The decisions themselves stay with other code and with people. The model is grounded in a numbered *context pack* built from the case, evidence and decision records. Rule passages are retrieved by filtering on network, reason family and edition before any similarity search. Every sentence must cite the items it relies on. In the representment, facts are written as placeholders that code fills from the record. A checker tests citations, values, attributes, coverage, tone and privacy. A small service regenerates a flagged draft once, sends it to a person if it is flagged again, logs every attempt, and releases nothing without a named approver.

> All data are synthetic and every amount and result is illustrative. The rule passages imitate the shape of card network rules but are invented. They are not any network's actual rules. The networks are called Network A and Network B, as in the book.

## Files

| File | Purpose |
|------|---------|
| `rules_library.jsonl` | 97 synthetic rule passages: 23 topics in six dispute families, for two networks, each in a current and a superseded edition (92), plus 5 general passages on regulation, tone and privacy |
| `rules_questions.jsonl` | 138 retrieval questions, three paraphrases of each of the 46 passages in force |
| `cases.jsonl` | 1,200 goods-not-received disputes, each with a case record, an evidence record (Chapter 11's shape) and a recovery decision (Chapter 10's shape). `DSP-0249` is the $249 worked example |
| `make_data.py` | Seeded generator for the three data files above |
| `rules_spec.py` | Source text for the rules library and the questions |
| `context.py` | Listing 12.1: `redact`, `context_pack`, `render_pack` |
| `rules.py` | Rule retrieval: `search_rules` (filter by reason, network and edition in force, then TF-IDF), `rules_for` |
| `summarize.py` | Listing 12.2: the summarizer, plus the slotted and prompt-only variants used by the evaluation |
| `draft.py` | Listing 12.3: `draft_narrative`, `render`, `chronology`, plus the customer-letter drafter |
| `guardrails.py` | Listing 12.4: `check`, plus the privacy and length checks of Table 12.5 |
| `normalize.py` | Amount, date and address-number parsers (the Chapter 11 normalizers, extended to dates written in prose) |
| `service.py` | Listing 12.5: `produce` and `approve`, the three writers, and the generation log |
| `llm_client.py` | `generate(system, user, ...)`: one function in front of the model. Defaults to the offline stand-in. Has adapters for two hosted providers |
| `llm_standin.py` | Deterministic stand-in model. It writes from templates and makes known kinds of mistake at rates you can set |
| `records.py` | Loads `cases.jsonl` into `Case` objects |
| `evaluate.py` | Figure 12.3 (retrieval) and Tables 12.6 and 12.7 (1,200 summaries in three configurations) |
| `worked_example.py` | Table 12.8: the service on the $249 claim |
| `test_chapter12.py` | Tests of redaction, retrieval by edition, slotting and each check |
| `evaluation_results.json`, `figures/`, `generation_log.jsonl` | Outputs of `evaluate.py` and `worked_example.py` |

## How to run

From the repository root, with the virtual environment active:

```bash
cd chapter12
python make_data.py        # regenerates the three .jsonl data files (seed 12)
python evaluate.py         # retrieval and summary evaluation (~40 s)
python worked_example.py   # the $249 claim: summary, letter, representment narrative
python -m pytest -q        # 16 tests
```

### Using a hosted model

`llm_client.generate` uses the deterministic stand-in unless **both** of these are set:

```bash
export LLM_PROVIDER=anthropic   # or: openai
export LLM_MODEL=<a pinned, dated model id>
export ANTHROPIC_API_KEY=...    # or OPENAI_API_KEY
pip install anthropic           # or: pip install openai
```

With a hosted model, `evaluate.py` still runs retrieval, the checker and the service unchanged. The stand-in's record of its own mistakes is the ground truth for "drafts containing an error", so a hosted run reports only the flag and hand-off rates. The stand-in's error rates are illustrative parameters. They are not measurements of any model.

## Chapter artifact

**The case summarizer and representment drafter.** This is `service.produce` with the summary, letter and representment writers, guarded by `guardrails.check`. It writes `generation_log.jsonl`, a log of every draft, its flags and its approval.

## Results

Numbers printed by `evaluate.py` and `worked_example.py` on this repository's data, compared with the book's.

**Retrieval (Figure 12.3), 138 questions**

| Retriever | Top 1 | Top 3 | Book |
|-----------|------:|------:|------|
| Similarity over the whole library | 55% | 98% | 54% / 98% |
| Filter on reason, network and edition, then search | 100% | 100% | 100% |

**Table 12.6: 1,200 case summaries (stand-in model)**

| Measure | Prompt only | Grounded, cited | Grounded, slotted | Book |
|---------|-----------:|----------------:|------------------:|------|
| Drafts containing an error | 42.4% | 26.4% | 15.6% | 41.8 / 27.4 / 15.2 |
| Drafts flagged by the checker | not checkable | 40.4% | 13.4% | – / 42.0 / 13.0 |
| Clean drafts flagged (false alarms) | – | 15.8% | 0.0% | – / 16.2 / 0.0 |
| Sent to a person after one regeneration | – | 17.7% | 1.9% | – / 16.3 / 2.0 |
| Released with an error | 42.4% | 2.4% | 2.2% | 41.8 / 2.4 / 2.4 |

**Table 12.7: flagged by type of error (2,400 grounded drafts)**

| Error | Drafts | Flagged | Book |
|-------|------:|------:|------|
| Bad citation | 110 | 100.0% | 124, 100.0% |
| Omission of a required fact | 101 | 100.0% | 131, 100.0% |
| Wrong fact | 129 | 89.1% | 106, 92.5% |
| Overclaim | 72 | 91.7% | 77, 90.9% |
| Unsupported claim | 148 | 80.4% | 149, 79.9% |

In the cited configuration, every false alarm comes from dates written in the ordinal style ("the 28th of November 2025"). The date parser cannot read them, so the checker refuses them. Slotted drafts never write dates, so they have no false alarms.

**Table 12.8: the $249 claim.** The summary passed on the first attempt (11 sentences, all cited). The first letter said "you received your parcel" and was flagged for tone. The second passed, and the analyst approved it with one sentence added about the building's mailroom. The representment narrative rendered 6 placeholders from the record with no flags. The stand-in is scripted to replay this sequence; the checker and service are the real code.

## Notes and deviations

- The book's `chapter11/normalize.py` and Chapter 11 evidence packets are not imported. This chapter carries its own `normalize.py` and generates its own 1,200 evidence records in the same shape, so it runs on its own.
- `OVERCLAIM` in `guardrails.py` also matches "received **your** parcel" (the book's pattern reads "received the parcel"). Without this, the letter in Table 12.8 would not be caught.
- `chronology` sorts on the date each value parses to. The book sorts on the raw value, which only orders correctly for ISO dates.
- The book names `llm_standin.py` in its text; it is included and used by default. The stand-in also writes the prompt-only and slotted variants the evaluation needs.
