"""Check the Python lever logic (business_case.py) against business_case.xlsx.

The workbook's Inputs are read with openpyxl and fed to run_levers(); the
workbook's own formulas are recomputed with tests/xlcalc.py. Both must agree
to the dollar, and both must reproduce the chapter's figures.
"""

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CH = HERE.parent
sys.path.insert(0, str(CH))
sys.path.insert(0, str(HERE))

import business_case as bc  # noqa: E402
import sensitivity  # noqa: E402
from xlcalc import Workbook  # noqa: E402

XLSX = CH / "business_case.xlsx"
LEVERS = ["Prevent", "Deflect", "Decide", "Recover"]


@pytest.fixture(scope="module")
def wb():
    if not XLSX.exists():
        subprocess.run([sys.executable, str(CH / "make_business_case.py")], check=True, cwd=CH)
    return Workbook(XLSX)


def inp(wb, row):
    return wb.value("Inputs", f"B{row}")


def test_sheets(wb):
    assert wb.wb.sheetnames == ["Summary", "Inputs", "Levers", "Costs", "Scenarios"]


def test_levers_use_real_formulas(wb):
    for r in range(4, 9):
        assert str(wb.wb["Levers"][f"E{r}"].value).startswith("=")
    assert wb.wb["Levers"]["C4"].value == "=B4*Inputs!B12"
    assert wb.wb["Levers"]["D4"].value == "=Inputs!B5+Inputs!B6/Inputs!B4"
    assert wb.wb["Scenarios"]["C39"].value == "=NPV(Inputs!$B$17,B21:D21)"


def test_constants_match_table_1_2(wb):
    assert inp(wb, 4) == bc.N0 == 720_000
    assert inp(wb, 5) == bc.COST_CASE == 28
    assert inp(wb, 6) / inp(wb, 4) == pytest.approx(bc.LOSS_CASE)
    assert inp(wb, 6) == 61_000_000 and inp(wb, 7) == 20_000_000
    assert inp(wb, 10) == bc.AMOUNT == 186
    assert (inp(wb, 8), inp(wb, 9)) == (0.31, 0.42)


def test_python_levers_match_workbook(wb):
    py = bc.run_levers(avoid=inp(wb, 12), deflect=inp(wb, 13), decide_share=inp(wb, 15),
                       decide_saving=inp(wb, 16), contested=inp(wb, 8), win_from=inp(wb, 9),
                       win_to=inp(wb, 18), deflect_cost=inp(wb, 14))
    for i, lever in enumerate(LEVERS):
        assert wb.value("Levers", f"E{4 + i}") == pytest.approx(py[lever], abs=1.0)
    assert wb.value("Levers", "E8") == pytest.approx(sum(py.values()), abs=1.0)
    # the workbook's inputs are the defaults of Listing 7.1
    assert py == bc.run_levers()


def test_book_figures():
    out = bc.run_levers()
    assert round(out["Prevent"]) == 3_246_400
    assert round(out["Deflect"]) == 4_260_096
    assert round(out["Decide"]) == 3_625_482
    assert round(out["Recover"]) == 2_997_065
    assert round(sum(out.values())) == 14_129_044


def test_pool_and_capture(wb):
    pools = [wb.value("Summary", f"D{4 + i}") / 1e6 for i in range(4)]
    assert [round(p, 2) for p in pools] == [18.30, 11.15, 29.25, 22.30]
    assert wb.value("Summary", "D8") == pytest.approx(81e6)
    capture = [wb.value("Summary", f"F{4 + i}") for i in range(4)]
    assert [round(c, 3) for c in capture] == [0.177, 0.382, 0.124, 0.134]
    assert round(wb.value("Summary", "F8"), 3) == 0.174
    assert wb.value("Summary", "B21") == "OK" and wb.value("Summary", "B22") == "OK"


def test_overlap(wb):
    assert round(wb.value("Levers", "E19") / 1e6, 2) == 15.02
    assert round(wb.value("Levers", "E20") / 1e6, 2) == 0.89


def test_scenarios_match_tables_7_5_and_7_6(wb):
    net = [round(wb.value("Scenarios", f"{c}21") / 1e6, 2) for c in "BCD"]
    assert net == [-2.05, 6.60, 10.63]
    expected = {38: (-0.32, -1.05), 39: (15.17, 11.57), 40: (21.11, 16.34)}
    for r, (total, npv) in expected.items():
        assert round(wb.value("Scenarios", f"B{r}") / 1e6, 2) == pytest.approx(total, abs=0.011)
        assert round(wb.value("Scenarios", f"C{r}") / 1e6, 2) == pytest.approx(npv, abs=0.011)
    assert wb.value("Scenarios", "D38") == "Beyond year 3"
    assert round(wb.value("Scenarios", "D39")) == 16
    assert round(wb.value("Scenarios", "D40")) == 13


def test_python_scenarios_match_workbook(wb):
    s = sensitivity.scenarios(sum(bc.run_levers().values()))
    for r, name in zip((38, 39, 40), ("Conservative", "Base", "Upside")):
        assert wb.value("Scenarios", f"C{r}") == pytest.approx(s[name]["npv"], abs=1.0)
    assert wb.value("Scenarios", "C43") == pytest.approx(
        sensitivity.tornado()[1][0][1], abs=1.0)


def test_slow_adoption_is_largest_swing():
    base, rows = sensitivity.tornado()
    assert rows[0][0].startswith("Adoption")
    assert round(rows[0][1] / 1e6, 1) == -6.4
