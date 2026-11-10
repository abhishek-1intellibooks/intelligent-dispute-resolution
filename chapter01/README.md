# Chapter 1: Understanding the Dispute Landscape in Modern Payments

This chapter defines a dispute and its three families: unauthorized, defective and first-party. It compares how disputes behave across payment rails and builds the economic picture of a representative mid-sized US issuer with about 4 million active cards. This folder holds two things. The first is the synthetic issuer dataset used throughout the book. The second is a notebook that reproduces the chapter's tables and data figures and computes the **baseline Dispute Ledger**. The Ledger shows how much of the issuer's combined loss and operating cost each of the four levers can address: Prevent, Deflect, Decide and Recover.

All data are synthetic and all amounts are illustrative.

## Files

| File | Purpose |
|---|---|
| `disputes_sample.csv` | 5,000 synthetic card disputes: one year at the representative issuer, scaled down 144 times (5,000 x 144 = 720,000 cases a year) |
| `make_data.py` | Seeded generator for `disputes_sample.csv`, calibrated to Table 1.2 |
| `explore.ipynb` | Executed notebook: headline figures (Table 1.2), family breakdown (Figure 1.1 in numbers), money waterfall (Figure 1.3), baseline Dispute Ledger |
| `build_notebook.py` | Builds `explore.ipynb` with nbformat |
| `baseline_ledger.csv` | The chapter artifact, written by the notebook's last cell |
| `tests/test_dataset.py` | Checks the Table 1.2 figures, money reconciliation and generator determinism |
| `requirements.txt` | Packages for this chapter |

### Dataset columns

`case_id`, `opened_at`, `closed_at`, `product` (credit_card / debit_card), `network` (visa / mastercard), `family` (unauthorized / defective / first_party), `amount`, `represented` (contested through representment), `outcome`, `recovered`, `net_loss`, `handling_cost`.

For represented cases, `outcome` is `won` or `lost`. It records whether the representment succeeded, which is how Chapter 3 reads it. For all other cases, `outcome` is one of:

- `accepted`: the merchant accepted the chargeback and the amount was recovered.
- `written_off`: the issuer absorbed the claim.
- `denied`: the claim was denied and the cardholder was re-billed.

`net_loss` is the amount that was not recovered. It equals the full amount for `written_off` and `won` cases and is zero otherwise.

## How to run

```bash
cd chapter01
python make_data.py                # regenerates disputes_sample.csv (seeded)
python build_notebook.py           # rebuilds explore.ipynb
python -m nbconvert --to notebook --execute --inplace explore.ipynb
python -m pytest -q tests
```

You can also open `explore.ipynb` in Jupyter and run all cells. The first code cell is the listing from the chapter.

## Chapter artifact

The baseline Dispute Ledger, saved as `baseline_ledger.csv`. Every dollar goes to exactly one lever:

- **Prevent:** written-off losses on unauthorized claims.
- **Deflect:** written-off losses on defective claims.
- **Decide:** written-off losses on first-party claims, plus all handling cost.
- **Recover:** losses where the merchant's representment succeeded.

The notebook repeats these rules beside the code.

## Results (as printed by the code)

Table 1.2, reproduced from the sample x 144:

| Metric | Book | Notebook |
|---|---|---|
| Dispute cases per year | 720,000 | 720,000 |
| First-party share | 38% | 38% |
| Average handling cost per case | $28 | $28 |
| Contested through representment | 31% | 31% (1,550 sample cases) |
| Win rate on contested cases | 42% | 42% (651 won) |
| Average disputed amount | $186 | $186.00 |
| Net annual dispute loss | $61 million | $61.0 million |
| Annual operating cost | $20 million | $20.2 million |

Money waterfall (Figure 1.3), in $ millions a year:

| Step | $M |
|---|---|
| Gross disputed value | 133.9 |
| Denied | -11.4 |
| Chargebacks accepted by merchants | -38.5 |
| Failed representments recovered | -23.0 |
| **Net loss** | **61.0** |

Baseline Dispute Ledger, out of $81.2M combined loss and operating cost (the book says "$81 million"):

| Lever | $M a year | Share |
|---|---|---|
| Prevent | 27.0 | 33% |
| Deflect | 8.1 | 10% |
| Decide | 30.2 | 37% |
| Recover | 15.9 | 20% |

The book does not give a per-lever split. These shares come from applying the assignment rules above to the synthetic data. All 3 tests pass.

## Notes

- Figures 1.1, 1.2 and 1.4 to 1.7 are conceptual diagrams. The notebook gives Figure 1.1 in numbers (cases and loss by family) and draws Figure 1.3.
- The generator hits the Table 1.2 shares exactly. It uses exact counts, rescales amounts and handling costs to the target means, and picks write-offs so that the net loss reaches $61M.
