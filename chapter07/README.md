# Chapter 7: The Business Case for Dispute Transformation

📖 **Read the chapter:** [CHAPTER.md](CHAPTER.md)

This chapter builds the business case for a dispute program in the way a finance committee will accept it. First it puts dispute cost into one figure ($81M: $61M net loss plus $20M operating cost) and allocates that figure to the four levers of the Dispute Ledger. It then sizes each lever's benefit from drivers instead of percentages. The levers are applied in timeline order so that no dollar is counted twice. Finally the benefit is set against a three-year program cost, and the chapter runs scenarios and a sensitivity analysis. The chapter artifact is `business_case.xlsx`, a five-sheet workbook built from live Excel formulas. `business_case.py` holds the same lever logic in Python and serves as an independent test of the workbook. **Every input comes from Table 1.2 or is a labeled assumption. All figures are illustrative; replace the assumptions with your own data before using the model.**

## Files

| File | Purpose |
|---|---|
| `make_business_case.py` | Generates `business_case.xlsx` with openpyxl. Every calculated cell is a real formula, so the workbook recalculates. The file is flagged to recalculate fully on load |
| `business_case.xlsx` | **Chapter artifact.** Sheets: Summary, Inputs, Levers, Costs, Scenarios (Table 7.7). Inputs are in blue text and key assumptions have a yellow fill |
| `business_case.py` | Listing 7.1: `run_levers()`, the lever logic in Python |
| `sensitivity.py` | Three-year scenarios (Tables 7.5-7.6) and a one-at-a-time NPV sensitivity (Figure 7.4). `--plot` writes `sensitivity.png` |
| `tests/test_business_case.py` | Reads the workbook's Inputs, runs `run_levers()` on them and checks the result against the workbook's own formulas. Also checks the chapter's figures (Tables 7.2-7.6) |
| `tests/xlcalc.py` | A small formula evaluator for the tests, needed because openpyxl does not calculate formulas |
| `requirements.txt` | Packages for this chapter |

### Workbook map

| Sheet | Contents | Representative formula |
|---|---|---|
| Inputs | Table 1.2 values, lever assumptions, adoption ramp, discount rate, allocation shares with a 100% check, scenario multipliers | values only |
| Levers | Benefit by lever in timeline order; naive total and overlap removed | `=B4*Inputs!B12`, `=Inputs!B5+Inputs!B6/Inputs!B4` |
| Costs | Program cost by category and year (all assumptions) | `=SUM(B4:B7)` |
| Scenarios | Conservative / Base / Upside / slow-adoption, with NPV and payback | `=NPV(Inputs!$B$17,B21:D21)` |
| Summary | Pool, benefit and capture by lever; headline figures; checks | `=IF(D4=0,0,E4/D4)` |

The cost lines ($7.0M / $4.0M / $3.5M split across four categories) and the slow adoption ramp (20/50/85%) are assumptions chosen to match the chapter's totals.

## How to run

```bash
cd chapter07
python make_business_case.py      # writes business_case.xlsx
python business_case.py           # Listing 7.1
python sensitivity.py             # scenarios and sensitivity (add --plot for a chart)
python -m pytest -q tests
```

## Results

`python business_case.py` prints:

```
Prevent  $3,246,400
Deflect  $4,260,096
Decide   $3,625,482
Recover  $2,997,065
Total    $14,129,044
```

These match the book to the dollar. The workbook gives the same four figures. This was checked in two ways: by the test suite's formula evaluator, and once by a full recalculation in Microsoft Excel (outside the tests), which gave Levers!E8 = 14,129,043.56.

- **Pool by lever:** 18.30 / 11.15 / 29.25 / 22.30 ($M), total $81M. Capture is 17.7% / 38.2% / 12.4% / 13.4%, or 17.4% overall (Tables 7.2 and 7.4).
- **Sequencing:** the naive total is $15.02M, so sequencing removes $0.89M of overlap.
- **Base case:** net by year is −2.05 / 6.60 / 10.63, giving a three-year net of $15.17M, an NPV of $11.57M and payback in 15.7 months (Table 7.5).
- **Conservative:** three-year net −$0.32M, NPV −$1.05M, payback beyond year 3.
- **Upside:** three-year net $21.11M, NPV $16.34M, payback in 13.5 months. All three match Table 7.6.
- **Sensitivity:** a slow adoption ramp lowers NPV by $6.44M, the largest swing. The book says $6.4M.
- **Tests:** 10 passed.
