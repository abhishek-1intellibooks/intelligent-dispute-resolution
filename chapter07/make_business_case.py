"""Generate chapter07/business_case.xlsx with live Excel formulas.

Five sheets: Summary, Inputs, Levers, Costs and Scenarios (Table 7.7).
Every number typed into the workbook is an input on the Inputs or Costs
sheet (blue text; key assumptions on a yellow fill). Everything else is a
formula, so the workbook recalculates when any input is changed. The file is
flagged for a full recalculation on load, so Excel or LibreOffice computes
every formula when it is opened.

Inputs come from Table 1.2 of Chapter 1 or are labeled assumptions. All
figures are illustrative.

    python make_business_case.py
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.properties import CalcProperties

HERE = Path(__file__).resolve().parent
OUT = HERE / "business_case.xlsx"

BLUE = Font(color="0000FF")
BLUE_BOLD = Font(color="0000FF", bold=True)
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=14)
NOTE = Font(italic=True, color="666666")
KEY = PatternFill("solid", fgColor="FFFF00")
HEAD = PatternFill("solid", fgColor="D9E1F2")
TOP = Border(top=Side(style="thin"))

USD = '$#,##0'
USD2 = '$#,##0.00'
USDM = '$#,##0.00,,"M";[Red]($#,##0.00,,"M")'
PCT = '0.0%'
INT = '#,##0'

LEVERS = ["Prevent", "Deflect", "Decide", "Recover"]


def header(ws, row, labels):
    for col, text in enumerate(labels, start=1):
        c = ws.cell(row=row, column=col, value=text)
        c.font, c.fill = BOLD, HEAD
        c.alignment = Alignment(wrap_text=True, vertical="top")


def put(ws, ref, value, fmt=None, font=None, fill=None):
    c = ws[ref]
    c.value = value
    if fmt:
        c.number_format = fmt
    if font:
        c.font = font
    if fill:
        c.fill = fill
    return c


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
# (row, label, value, format, source, key assumption?)
INPUTS = [
    (4, "Dispute cases per year", 720_000, INT, "Table 1.2", False),
    (5, "Average handling cost per case", 28, USD2, "Table 1.2", False),
    (6, "Net annual dispute loss (unrecovered)", 61_000_000, USD, "Table 1.2", False),
    (7, "Annual operating cost", 20_000_000, USD, "Table 1.2", False),
    (8, "Cases contested through representment", 0.31, PCT, "Table 1.2", False),
    (9, "Win rate on contested cases (today)", 0.42, PCT, "Table 1.2", False),
    (10, "Average disputed amount", 186, USD2, "Table 1.2", False),
    (11, "Share classified as first-party misuse", 0.38, PCT,
     "Table 1.2 (reference only; not used in a formula)", False),
    (12, "Prevent: share of cases avoided", 0.04, PCT, "Assumption (Table 7.3)", True),
    (13, "Deflect: share of remaining cases resolved early", 0.06, PCT,
     "Assumption (Table 7.3)", True),
    (14, "Deflect: handling cost of an early resolution", 10, USD2,
     "Assumption: $28 - $18 saving (Table 7.3)", True),
    (15, "Decide: share of remaining cases on the new path", 0.62, PCT,
     "Chapter 1 example (Table 7.3)", True),
    (16, "Decide: handling saving per case ($28 to $19)", 9, USD2,
     "Chapter 1 example (Table 7.3)", True),
    (17, "Discount rate", 0.10, PCT, "Assumption", True),
    (18, "Recover: target win rate on contested cases", 0.50, PCT,
     "Chapter 1 question (Table 7.3)", True),
    (19, "Adoption, year 1", 0.35, PCT, "Assumption (Table 7.5)", True),
    (20, "Adoption, year 2", 0.75, PCT, "Assumption (Table 7.5)", True),
    (21, "Adoption, year 3", 1.00, PCT, "Assumption (Table 7.5)", True),
    (22, "Slow adoption ramp, year 1 (sensitivity)", 0.20, PCT, "Assumption (Figure 7.4)", False),
    (23, "Slow adoption ramp, year 2 (sensitivity)", 0.50, PCT, "Assumption (Figure 7.4)", False),
    (24, "Slow adoption ramp, year 3 (sensitivity)", 0.85, PCT, "Assumption (Figure 7.4)", False),
]

# Allocation of the cost pool to levers (Table 7.2): net-loss share, op-cost share
ALLOCATION = {"Prevent": (0.30, 0.00), "Deflect": (0.15, 0.10),
              "Decide": (0.25, 0.70), "Recover": (0.30, 0.20)}

# Scenario multipliers over the base (Table 7.6): benefit x, cost x
SCENARIOS = {"Conservative": (0.60, 1.25), "Base": (1.00, 1.00), "Upside": (1.20, 1.00)}

# Program cost by category and year (assumptions; totals $7.0M, $4.0M, $3.5M)
COSTS = {
    "Platform and integration": (3_500_000, 1_000_000, 500_000),
    "Data and models": (1_500_000, 1_000_000, 800_000),
    "Run (cloud, tooling, monitoring)": (800_000, 1_200_000, 1_500_000),
    "Change and training": (1_200_000, 800_000, 700_000),
}


def build_inputs(ws):
    ws["A1"].value, ws["A1"].font = "Inputs: every assumption in its own labeled cell", TITLE
    put(ws, "A2", "Blue text = input; yellow fill = key assumption. "
        "Replace every assumption with your own data before use. Illustrative only.", font=NOTE)
    header(ws, 3, ["Input", "Value", "Source / note"])
    for row, label, value, fmt, source, key in INPUTS:
        ws.cell(row=row, column=1, value=label)
        put(ws, f"B{row}", value, fmt, BLUE, KEY if key else None)
        ws.cell(row=row, column=3, value=source)

    put(ws, "A26", "Allocation of the cost pool to levers (Table 7.2)", font=BOLD)
    header(ws, 27, ["Lever", "Net loss share", "Operating cost share"])
    for i, lever in enumerate(LEVERS):
        r = 28 + i
        loss, ops = ALLOCATION[lever]
        ws.cell(row=r, column=1, value=lever)
        put(ws, f"B{r}", loss, PCT, BLUE, KEY)
        put(ws, f"C{r}", ops, PCT, BLUE, KEY)
    ws["A32"].value, ws["A32"].font = "Total", BOLD
    put(ws, "B32", "=SUM(B28:B31)", PCT, BOLD)
    put(ws, "C32", "=SUM(C28:C31)", PCT, BOLD)
    ws["A33"].value = "Check: each column sums to 100%"
    put(ws, "B33", '=IF(ROUND(B32,6)=1,"OK","CHECK")', font=BOLD)
    put(ws, "C33", '=IF(ROUND(C32,6)=1,"OK","CHECK")', font=BOLD)

    put(ws, "A35", "Scenario multipliers over the base (Table 7.6)", font=BOLD)
    header(ws, 36, ["Scenario", "Benefit multiplier", "Cost multiplier"])
    for i, (name, (b, c)) in enumerate(SCENARIOS.items()):
        r = 37 + i
        ws.cell(row=r, column=1, value=name)
        put(ws, f"B{r}", b, "0.00", BLUE, KEY)
        put(ws, f"C{r}", c, "0.00", BLUE, KEY)
    widths(ws, {"A": 52, "B": 18, "C": 48})


# ---------------------------------------------------------------------------
# Levers: driver-based benefit in timeline order (Table 7.3)
# ---------------------------------------------------------------------------
def build_levers(ws):
    ws["A1"].value, ws["A1"].font = "Levers: benefit by lever, in timeline order", TITLE
    put(ws, "A2", "Each lever works on the caseload the lever before it left "
        "(Decide and Recover both act on what Deflect left).", font=NOTE)
    header(ws, 3, ["Lever", "Caseload in", "Cases affected", "Saving per affected case",
                   "Benefit", "Caseload out", "Driver"])
    rows = {
        4: ("Prevent", "=Inputs!B4", "=B4*Inputs!B12", "=Inputs!B5+Inputs!B6/Inputs!B4",
            "=B4-C4", "Cases avoided x (handling + average loss)"),
        5: ("Deflect", "=F4", "=B5*Inputs!B13", "=Inputs!B5-Inputs!B14+Inputs!B6/Inputs!B4",
            "=B5-C5", "Resolved early x (handling saving + average loss)"),
        6: ("Decide", "=F5", "=B6*Inputs!B15", "=Inputs!B16",
            "=B6", "Cases on the new path x handling saving"),
        7: ("Recover", "=F5", "=B7*Inputs!B8", "=(Inputs!B18-Inputs!B9)*Inputs!B10",
            "=B7", "Contested cases x win-rate uplift x average amount"),
    }
    for r, (lever, cin, affected, saving, cout, driver) in rows.items():
        ws.cell(row=r, column=1, value=lever)
        put(ws, f"B{r}", cin, INT)
        put(ws, f"C{r}", affected, INT)
        put(ws, f"D{r}", saving, USD2)
        put(ws, f"E{r}", f"=C{r}*D{r}", USD)
        put(ws, f"F{r}", cout, INT)
        ws.cell(row=r, column=7, value=driver)
    ws["A8"].value, ws["A8"].font = "Total (sequenced)", BOLD
    put(ws, "E8", "=SUM(E4:E7)", USD, BOLD)
    for col in "ABCDEFG":
        ws[f"{col}8"].border = TOP

    ws["A10"].value = "Recover: extra wins"
    put(ws, "C10", "=C7*(Inputs!B18-Inputs!B9)", INT)
    ws["A11"].value = "Average loss per case"
    put(ws, "D11", "=Inputs!B6/Inputs!B4", USD2)

    put(ws, "A13", "Naive total: every lever applied to the full caseload", font=BOLD)
    header(ws, 14, ["Lever", "Caseload in", "Cases affected", "Saving per affected case", "Benefit"])
    naive = {
        15: ("Prevent", "=Inputs!B4*Inputs!B12", "=D4"),
        16: ("Deflect", "=Inputs!B4*Inputs!B13", "=D5"),
        17: ("Decide", "=Inputs!B4*Inputs!B15", "=D6"),
        18: ("Recover", "=Inputs!B4*Inputs!B8", "=D7"),
    }
    for r, (lever, affected, saving) in naive.items():
        ws.cell(row=r, column=1, value=lever)
        put(ws, f"B{r}", "=Inputs!B4", INT)
        put(ws, f"C{r}", affected, INT)
        put(ws, f"D{r}", saving, USD2)
        put(ws, f"E{r}", f"=C{r}*D{r}", USD)
    ws["A19"].value, ws["A19"].font = "Naive total", BOLD
    put(ws, "E19", "=SUM(E15:E18)", USD, BOLD)
    ws["A20"].value, ws["A20"].font = "Overlap removed by sequencing", BOLD
    put(ws, "E20", "=E19-E8", USD, BOLD)
    widths(ws, {"A": 34, "B": 14, "C": 15, "D": 16, "E": 16, "F": 14, "G": 50})


# ---------------------------------------------------------------------------
# Costs: program cost by category and year
# ---------------------------------------------------------------------------
def build_costs(ws):
    ws["A1"].value, ws["A1"].font = "Costs: program cost by category and year", TITLE
    put(ws, "A2", "Every line is an assumption (placeholders, not quotations).", font=NOTE)
    header(ws, 3, ["Category", "Year 1", "Year 2", "Year 3", "Total", "Basis"])
    for i, (cat, years) in enumerate(COSTS.items()):
        r = 4 + i
        ws.cell(row=r, column=1, value=cat)
        for col, value in zip("BCD", years):
            put(ws, f"{col}{r}", value, USDM, BLUE)
        put(ws, f"E{r}", f"=SUM(B{r}:D{r})", USDM)
        ws.cell(row=r, column=6, value="Assumption")
    ws["A8"].value, ws["A8"].font = "Total", BOLD
    for col in "BCDE":
        put(ws, f"{col}8", f"=SUM({col}4:{col}7)", USDM, BOLD)
    for col in "ABCDEF":
        ws[f"{col}8"].border = TOP
    widths(ws, {"A": 36, "B": 13, "C": 13, "D": 13, "E": 13, "F": 14})


# ---------------------------------------------------------------------------
# Scenarios: three cases over three years (Tables 7.5 and 7.6)
# ---------------------------------------------------------------------------
SCEN_BLOCKS = {  # name -> (first row of block, Inputs row of multipliers, adoption rows)
    "Conservative": (12, 37, (19, 20, 21)),
    "Base": (18, 38, (19, 20, 21)),
    "Upside": (24, 39, (19, 20, 21)),
    "Base with slow adoption (sensitivity)": (30, 38, (22, 23, 24)),
}


def build_scenarios(ws):
    ws["A1"].value, ws["A1"].font = "Scenarios: three cases over three years", TITLE
    put(ws, "A2", "Each scenario is a pair of multipliers over the base (Inputs sheet). "
        "NPV uses the spreadsheet's NPV function (end-of-year discounting).", font=NOTE)
    header(ws, 3, ["", "Year 1", "Year 2", "Year 3", "Total"])
    ws["A4"].value = "Run-rate benefit at full adoption"
    ws["A5"].value = "Adoption"
    ws["A6"].value = "Program cost (Costs sheet)"
    for col, arow, crow in zip("BCD", (19, 20, 21), "BCD"):
        put(ws, f"{col}4", "=Levers!$E$8", USDM)
        put(ws, f"{col}5", f"=Inputs!B{arow}", PCT)
        put(ws, f"{col}6", f"=Costs!{crow}8", USDM)
    put(ws, "E6", "=SUM(B6:D6)", USDM)

    put(ws, "A8", "Benefit multiplier / cost multiplier per scenario: Inputs!B37:C39", font=NOTE)

    for name, (s, mrow, adoption) in SCEN_BLOCKS.items():
        ws.cell(row=s, column=1, value=name).font = BOLD
        ws.cell(row=s + 1, column=1, value="Benefit")
        ws.cell(row=s + 2, column=1, value="Cost")
        ws.cell(row=s + 3, column=1, value="Net").font = BOLD
        ws.cell(row=s + 4, column=1, value="Cumulative net")
        for col, arow in zip("BCD", adoption):
            put(ws, f"{col}{s + 1}", f"=Levers!$E$8*Inputs!B{arow}*Inputs!$B${mrow}", USDM)
            put(ws, f"{col}{s + 2}", f"={col}$6*Inputs!$C${mrow}", USDM)
            put(ws, f"{col}{s + 3}", f"={col}{s + 1}-{col}{s + 2}", USDM, BOLD)
        put(ws, f"B{s + 4}", f"=B{s + 3}", USDM)
        put(ws, f"C{s + 4}", f"=B{s + 4}+C{s + 3}", USDM)
        put(ws, f"D{s + 4}", f"=C{s + 4}+D{s + 3}", USDM)
        for k in (1, 2, 3):
            put(ws, f"E{s + k}", f"=SUM(B{s + k}:D{s + k})", USDM, BOLD if k == 3 else None)

    put(ws, "A36", "Scenario summary (Table 7.6)", font=BOLD)
    header(ws, 37, ["Scenario", "Three-year net", "NPV", "Payback (months)"])
    for i, (name, (s, _, _)) in enumerate(SCEN_BLOCKS.items()):
        r = 38 + i
        net, cum = s + 3, s + 4
        ws.cell(row=r, column=1, value=name)
        put(ws, f"B{r}", f"=E{net}", USDM)
        put(ws, f"C{r}", f"=NPV(Inputs!$B$17,B{net}:D{net})", USDM)
        put(ws, f"D{r}",
            f'=IF(B{cum}>=0,0,IF(C{cum}>=0,12+12*(-B{cum})/C{net},'
            f'IF(D{cum}>=0,24+12*(-C{cum})/D{net},"Beyond year 3")))', "0.0")
    ws["A43"].value = "Slow adoption: change in NPV against the base"
    put(ws, "C43", "=C41-C39", USDM, BOLD)
    widths(ws, {"A": 40, "B": 15, "C": 15, "D": 17, "E": 15})


# ---------------------------------------------------------------------------
# Summary: pool, benefit and capture by lever (Tables 7.2 and 7.4)
# ---------------------------------------------------------------------------
def build_summary(ws):
    ws["A1"].value, ws["A1"].font = "Business case for dispute transformation (illustrative)", TITLE
    put(ws, "A2", "Every figure traces to Table 1.2 or to a labeled assumption on the Inputs "
        "and Costs sheets. Synthetic, illustrative values.", font=NOTE)
    header(ws, 3, ["Lever", "Net loss", "Operating cost", "Cost pool", "Benefit (run-rate)",
                   "Share of pool captured", "Share of total pool", "Benefit within pool?"])
    for i, lever in enumerate(LEVERS):
        r = 4 + i
        ws.cell(row=r, column=1, value=lever)
        put(ws, f"B{r}", f"=Inputs!$B$6*Inputs!B{28 + i}", USDM)
        put(ws, f"C{r}", f"=Inputs!$B$7*Inputs!C{28 + i}", USDM)
        put(ws, f"D{r}", f"=B{r}+C{r}", USDM)
        put(ws, f"E{r}", f"=Levers!E{4 + i}", USDM)
        put(ws, f"F{r}", f"=IF(D{r}=0,0,E{r}/D{r})", PCT)
        put(ws, f"G{r}", f"=IF($D$8=0,0,D{r}/$D$8)", PCT)
        put(ws, f"H{r}", f'=IF(E{r}<=D{r},"OK","EXCEEDS POOL")')
    ws["A8"].value, ws["A8"].font = "Total", BOLD
    for col in "BCDE":
        put(ws, f"{col}8", f"=SUM({col}4:{col}7)", USDM, BOLD)
    put(ws, "F8", "=IF(D8=0,0,E8/D8)", PCT, BOLD)
    put(ws, "G8", "=SUM(G4:G7)", PCT, BOLD)
    for col in "ABCDEFGH":
        ws[f"{col}8"].border = TOP

    put(ws, "A10", "Headline figures", font=BOLD)
    lines = [
        ("Quantified cost pool (net loss + operating cost)", "=D8", USDM),
        ("Run-rate benefit, levers in timeline order", "=Levers!E8", USDM),
        ("Naive benefit, each lever on the full caseload", "=Levers!E19", USDM),
        ("Overlap removed by sequencing", "=Levers!E20", USDM),
        ("Program cost over three years", "=Costs!E8", USDM),
        ("Base case: three-year net", "=Scenarios!B39", USDM),
        ("Base case: NPV at the discount rate", "=Scenarios!C39", USDM),
        ("Base case: payback (months)", "=Scenarios!D39", "0.0"),
        ("Conservative: three-year net", "=Scenarios!B38", USDM),
        ("Upside: three-year net", "=Scenarios!B40", USDM),
        ("Check: allocation shares sum to 100%",
         '=IF(AND(Inputs!B33="OK",Inputs!C33="OK"),"OK","CHECK")', None),
        ("Check: no lever's benefit exceeds its pool",
         '=IF(COUNTIF(H4:H7,"OK")=4,"OK","CHECK")', None),
    ]
    for i, (label, formula, fmt) in enumerate(lines):
        r = 11 + i
        ws.cell(row=r, column=1, value=label)
        put(ws, f"B{r}", formula, fmt, BOLD)
    widths(ws, {"A": 48, "B": 16, "C": 15, "D": 14, "E": 17, "F": 14, "G": 14, "H": 16})


def main():
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    sheets = {name: wb.create_sheet(name) for name in ("Inputs", "Levers", "Costs", "Scenarios")}
    build_inputs(sheets["Inputs"])
    build_levers(sheets["Levers"])
    build_costs(sheets["Costs"])
    build_scenarios(sheets["Scenarios"])
    build_summary(summary)
    for ws in wb.worksheets:
        ws.freeze_panes = "A4"
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    wb.save(OUT)
    print(f"wrote {OUT.name}: sheets {wb.sheetnames}")


if __name__ == "__main__":
    main()
