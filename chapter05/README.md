# Chapter 5: Dispute Operations: People, Process, Performance

📖 **Read the chapter:** [CHAPTER.md](CHAPTER.md)

This chapter looks at the operation that works the dispute queue: its operating model, the five timestamps of a case, a balanced KPI set, queueing and staffing, and quality controls. The chapter artifact is a KPI dashboard that reports the same closed cases under two definitions of cycle time. The analyst's view runs from first touch to closure; the customer's view runs from the claim to closure. Putting them side by side shows that queue wait, which the first-touch view cannot see, takes up most of the customer's wait. **All data are synthetic and all amounts and rates are illustrative.**

## Files

| File | Purpose |
|---|---|
| `make_ops_log.py` | Seeded generator for `ops_log.csv`: 5,000 closed cases over twelve weeks, with the five timestamps of Table 5.2, the channel and the amount. The last three weeks have a surge. Analysts work weekdays 08:00-18:00 |
| `ops_log.csv` | The generated synthetic operations log (about 0.5 MB) |
| `build_notebook.py` | Builds `ops_kpi_dashboard.ipynb` with nbformat |
| `ops_kpi_dashboard.ipynb` | **Chapter artifact.** Listings 5.1 and 5.2 verbatim, Table 5.6, intake lag by channel, the surge-period comparison, Figure 5.5, the worked example (Figure 5.2), Little's Law, Table 5.4 and Figure 5.4, and the quality sample size. Stored with outputs |
| `fig_5_5_dashboard.png` | Figure 5.5, written by the notebook |
| `test_ops_log.py` | pytest checks: 5,000 rows, timestamps in order, analyst events on weekdays only, deterministic generator |
| `requirements.txt` | Packages for this chapter |

Figures 5.1 and 5.3 are conceptual diagrams with no data behind them, so the notebook does not reproduce them.

## How to run

```bash
cd chapter05
python make_ops_log.py                 # regenerates ops_log.csv (seed 20260505)
python build_notebook.py               # rebuilds the notebook (optional)
python -m nbconvert --to notebook --execute --inplace ops_kpi_dashboard.ipynb
python -m pytest -q test_ops_log.py
```

## Results (as printed by the notebook)

| Indicator | Analyst view | Claim view | Book (Table 5.6) |
|---|---|---|---|
| Median cycle time | 2.2 days | 6.4 days | 2.2 / 6.3 |
| 90th percentile | 4.9 days | 12.3 days | 4.5 / 11.8 |
| 95th percentile | 5.9 days | 14.8 days | 5.7 / 14.8 |
| Decisions after 10 business days | cannot be computed | 4.8% | 4.7% |
| Mean queue wait | not visible | 4.3 days (60% of mean cycle) | 4.3 days (60%) |

- Mean intake lag: app 0.0 h, web 0.3 h, phone 13.1 h, branch 13.3 h. The book says about 13 to 14 hours for phone and branch.
- Breach rate for claims received in the final three weeks was 6.6%, against 4.1% earlier. The book gives 6.7% and 4.0%.
- Worked example: the analyst view is 5 h 15 min and the claim view is 3 days 19 h 50 min. The decision falls on business day 2 of 10.
- Little's Law: 13,808 cases are in flight at 7 days and 9,863 at 5 days. Table 5.4 gives 400 / 353 / 316 analysts at waits of 3.0 / 5.7 / 19.0 times handling time. The quality sample is 385 cases (865 at a margin of ±2 points).

**Gap:** the 90th-percentile cycle times are about 0.4-0.5 days above the book's (4.9 vs 4.5, 12.3 vs 11.8). Every other headline figure is within 0.1 day or 0.1 point. The generator was tuned by grid search, and with this generator a lower p90 also pulled the p95 and the breach rate away from the book's values.

The dashboard uses closed cases only and treats weekends as the only non-business days, as the chapter describes. Adding open cases and a holiday calendar is left to the exercises.
