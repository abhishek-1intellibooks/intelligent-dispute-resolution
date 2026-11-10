# Chapter 11: Document Intelligence and Evidence Automation

This chapter treats evidence as a set of facts rather than a pile of files. The requirements for a not-received claim are held as a versioned rule set. The pipeline reads the decisive facts (ship-to, amount, delivered-to, delivered-on, attestation) from order records, carrier records, proofs of delivery and invoices that arrive through five channels: API, native PDF, screenshot, clean scan and phone photo. It normalizes the values, matches addresses component by component and combines the checks into a sufficiency score with a veto, a verdict and named gaps. Any reading below a confidence of 0.80 is rejected. The pipeline then falls back to a more trusted source or asks a person. That cuts wrong facts sharply, at the cost of a review queue.

> All data are synthetic and every result is illustrative. No OCR engine is needed: `make_evidence_data.py` simulates OCR character errors and per-character confidence by channel.

## Files

| File | Purpose |
|------|---------|
| `make_evidence_data.py` | Seeded generator for `evidence_packets/`: 4,000 not-received disputes (April 2025 to March 2026), 12,680 documents and exactly 23,860 field readings, with simulated OCR errors by channel. |
| `evidence_packets/cases.csv` | Case record per dispute (Chapter 8): amount in cents, expected, claimed and opened dates, tracking number, number of documents. |
| `evidence_packets/documents.csv` | One row per document: type, channel, pages, SHA-256 of its content. |
| `evidence_packets/readings.csv` | 23,860 field readings: raw OCR text, per-character confidence (0–100), date format of the source, and the true text (used only to measure). |
| `evidence_packets/pages.csv` | Text of every non-API page (9,530), used by `classify_pages.py`. |
| `evidence_packets/truth.csv` | Simulator-only data: what happened to each parcel, the perfect-reading score and whether the merchant's evidence prevailed. |
| `requirements.py` | Listing 11.1. `Requirement`, the `NOT_RECEIVED` rule set (`nr-2025.2`), an older `nr-2024.1`, `RULE_SETS` and `rules_for`. |
| `extract.py` | Listing 11.2 (`Fact`, `field_confidence`, `normalize_address`, `read_amount`, `repair_date_digits`). Also has readers for dates by source format and for attestations ("Not required" is not a signature), `normalize_tracking`, `facts_from_readings`, and an `OcrEngine` interface with an optional `TesseractEngine`. |
| `match.py` | Listing 11.3. `address_match`, `amount_match` and `on_time`. Uses rapidfuzz if installed, otherwise an exact pure-Python `fuzz.ratio`. Run it to score 1,500 address pairs. |
| `sufficiency.py` | Listing 11.4. Sufficiency score, gaps and verdict (Table 11.4). |
| `classify_pages.py` | Character 3–5-gram TF-IDF with logistic regression over six page types. Abstains below 60% confidence. |
| `evidence_pipeline.py` | Listing 11.5 (`choose`, `build_evidence`). Run it to evaluate all 4,000 packets (Figures 11.2, 11.4 and 11.5, Tables 11.6 and 11.7). |
| `worked_example.py` | The $249 claim (Table 11.8). |
| `tests/test_evidence.py` | 17 pytest tests: normalizers on clean data (including Sterling Lane, Unity Road and the Oct date bug), address verdicts, scoring, veto, rule-set selection and the fallback chain. |
| `requirements.txt` | Packages for this chapter. Note that `requirements.py` is the evidence rule set, not a package list. |

`evidence_packets/` is 8.3 MB in five CSV files, so it is committed in full.

## How to run

```bash
cd chapter11
python make_evidence_data.py     # writes evidence_packets/ (about 20 s)
python match.py                  # address scores on 1,500 pairs
python classify_pages.py         # page classifier on 1,000 test pages
python evidence_pipeline.py      # Figures 11.2/11.4/11.5, Tables 11.6/11.7
python worked_example.py         # Table 11.8
python -m pytest -q              # 17 tests
```

To read real documents, install an OCR engine (see `requirements.txt`) and plug it in through `extract.OcrEngine`. Everything downstream of `Fact` stays the same.

## Chapter artifact

`evidence_pipeline.py` is the evidence pipeline. For every case it returns the facts with their document, page, channel, confidence and how each was obtained (auto or review), along with the sufficiency score, verdict, gaps, rule-set version and pipeline version.

## Results (as printed by the code)

| Measure | This repository | Book |
|---|---|---|
| Field readings / read correctly | 23,860 / 96.4% | 23,860 / 94.1% |
| Correct by channel: API, native / screenshot / clean scan / photo | 100% / 94.3% / 87.5% / 71.7% | 100% / ~95% / ~87% / ~60% |
| Photo: delivered-to address / delivery date | 42.9% / 76.1% | 35% / 85% |
| Gate 0.80, coverage at accuracy: screenshot / clean scan / photo | 92% at 99.9% / 72% at 99.8% / 1% | 90% at 99.4% / 67% at 99.0% / ~0% |
| All channels at 0.80 | 91.7% accepted at 99.98% | 85.6% at 99.8% |
| Page classifier: accuracy / abstain / accuracy on remainder | 96.0% / 5.7% / 99.6% | 95.4% / 7.7% / 97.8% |
| address_match: same address, two styles, clean scan / random pairs | 0.96 / 0.13 | 0.96 / 0.16 |
| Naive pipeline: cases with a wrong fact | 264 (6.6%) | 236 (5.9%) |
| Gated pipeline: cases with a wrong fact | 5 (0.1%) | 16 (0.4%) |
| Gated: cases sent to a person / facts reviewed | 625 (15.6%) / 933 | 408 (10.2%) / 550 |
| Naive: cases sent to a person | 109 (2.7%) | 39 (1.0%) |
| Sufficient judged not sufficient: naive / gated | 154 / 1 | 141 / 11 |
| Score identical to a perfect reading: naive / gated | 95.6% / 99.98% | 96.2% / 99.7% |
| Evidence prevailed | 61.9% | 61.2% |
| Prevailed: score < 0.20 / > 0.85 | 12% / 82% | 10% / 84% |
| AUC: sufficiency score / number of documents | 0.74 / 0.55 | 0.80 / 0.59 |
| Analyst time: manual / pipeline | 1,333.3 h / 142.2 h (89% less) | 1,333.3 h / 118.2 h |
| Worked example: first reading of the unit | 2, confidence 0.58, rejected | same |
| Worked example: score and verdict | 0.95, sufficient, no gaps | same |
| Worked example: if the photo had been trusted | 0.50, borderline, "unit differs" | same |

### Known gaps from the book's numbers

- **Review queue.** The gated pipeline sends more work to a person here (15.6% of cases against 10.2%). In this data, phone photos and scans are often the only source of a fact, so the 0.80 gate holds more of them back.
- **Accuracy mix.** A larger share of readings comes from API and native channels than in the book. Overall accuracy is therefore higher (96.4% against 94.1%), even though each channel's accuracy is close to the book's.
- **Score AUC.** The AUC of the sufficiency score is 0.74 (book 0.80). Scores cluster at a few values (0.75, 0.85, 0.95), and those ties limit how well the score can separate outcomes.
- **Carrier attestation.** Carrier API records also report the attestation (signature or photo), which reduces photo-only reviews. The worked example's carrier record leaves it out, so the attestation comes from the photographed slip, as in Table 11.8.
