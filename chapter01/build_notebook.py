"""Build chapter01/explore.ipynb with nbformat.

Run:  python build_notebook.py
then: python -m nbconvert --to notebook --execute --inplace explore.ipynb
"""
from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).resolve().parent

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = [
    md("# Chapter 1: Understanding the Dispute Landscape in Modern Payments\n\n"
       "This notebook loads `disputes_sample.csv` (5,000 synthetic card disputes, "
       "one year at a representative mid-sized US issuer, scaled down 144 times) and "
       "reproduces the chapter's tables and data figures:\n\n"
       "1. Headline figures and **Table 1.2** (annual dispute profile)\n"
       "2. The three families (**Figure 1.1**, as counts and value)\n"
       "3. Where the money goes (**Figure 1.3** waterfall)\n"
       "4. The baseline **Dispute Ledger** (Table 1.3 levers), the chapter artifact\n\n"
       "All data are synthetic and all amounts illustrative."),
    md("## Cell 1: load the data and the headline figures"),
    code('import pandas as pd\n'
         'disputes = pd.read_csv("disputes_sample.csv",\n'
         '    parse_dates=["opened_at", "closed_at"])\n'
         'summary = {\n'
         '    "cases": len(disputes),\n'
         '    "first_party_share": (disputes["family"] == "first_party").mean(),\n'
         '    "contested_share": disputes["represented"].mean(),\n'
         '    "win_rate": disputes.loc[disputes["represented"],\n'
         '        "outcome"].eq("won").mean(),\n'
         '    "avg_amount": disputes["amount"].mean(),\n'
         '}\n'
         'print(summary)'),
    md("### Table 1.2: annual dispute profile of the representative issuer\n\n"
       "The sample covers one year; each sample case stands for 144 cases at an issuer "
       "with about 4 million active cards."),
    code('SCALE = 144   # 5,000 sample cases -> 720,000 cases a year\n'
         'net_loss = disputes["net_loss"].sum() * SCALE\n'
         'operating = disputes["handling_cost"].sum() * SCALE\n'
         'table_1_2 = pd.DataFrame({"Value": [\n'
         '    f"{summary[\'cases\'] * SCALE:,}",\n'
         '    f"{summary[\'first_party_share\']:.0%}",\n'
         '    f"${disputes[\'handling_cost\'].mean():,.0f}",\n'
         '    f"{summary[\'contested_share\']:.0%}",\n'
         '    f"{summary[\'win_rate\']:.0%}",\n'
         '    f"${summary[\'avg_amount\']:,.0f}",\n'
         '    f"${net_loss / 1e6:,.0f} million",\n'
         '    f"${operating / 1e6:,.0f} million",\n'
         ']}, index=["Dispute cases per year",\n'
         '           "Share classified as first-party misuse",\n'
         '           "Average handling cost per case",\n'
         '           "Cases contested through representment",\n'
         '           "Win rate on contested cases",\n'
         '           "Average disputed amount",\n'
         '           "Net annual dispute loss (unrecovered)",\n'
         '           "Annual operating cost"])\n'
         'table_1_2.index.name = "Metric"\n'
         'table_1_2'),
    md("## The three families (Figure 1.1, in numbers)"),
    code('families = (disputes.groupby("family")\n'
         '            .agg(cases=("case_id", "size"), value=("amount", "sum"),\n'
         '                 net_loss=("net_loss", "sum"))\n'
         '            .reindex(["unauthorized", "defective", "first_party"]))\n'
         'families["share_of_cases"] = families["cases"] / families["cases"].sum()\n'
         'families["annual_cases"] = families["cases"] * SCALE\n'
         'families["annual_net_loss_$m"] = families["net_loss"] * SCALE / 1e6\n'
         'families.round(3)'),
    md("## Cell 2: where the money goes (Figure 1.3)\n\n"
       "From gross disputed value to net loss. *Denied* claims are re-billed to the "
       "cardholder; *accepted* chargebacks are recovered from the merchant; chargebacks "
       "whose representment failed are also recovered. What remains, written-off claims "
       "and claims where the merchant's representment succeeded, is the net loss."),
    code('import matplotlib.pyplot as plt\n'
         '\n'
         'by_outcome = disputes.groupby("outcome")["amount"].sum() * SCALE / 1e6\n'
         'gross = disputes["amount"].sum() * SCALE / 1e6\n'
         'steps = [\n'
         '    ("Gross disputed value", gross),\n'
         '    ("Denied, re-billed\\nto cardholder", -by_outcome["denied"]),\n'
         '    ("Chargebacks accepted\\nby merchant", -by_outcome["accepted"]),\n'
         '    ("Representment failed,\\nrecovered", -by_outcome["lost"]),\n'
         ']\n'
         'net = gross + sum(v for _, v in steps[1:])\n'
         'waterfall = pd.DataFrame(steps + [("Net loss", net)], columns=["step", "$m"])\n'
         'print(waterfall.assign(step=waterfall["step"].str.replace("\\n", " ")).round(1).to_string(index=False))\n'
         '\n'
         'fig, ax = plt.subplots(figsize=(8, 4))\n'
         'running = 0.0\n'
         'for i, (label, v) in enumerate(steps + [("Net loss", net)]):\n'
         '    if i == 0 or label == "Net loss":\n'
         '        bottom, height, color = 0, v, "#2a6fdb" if i == 0 else "#c2410c"\n'
         '        running = v\n'
         '    else:\n'
         '        bottom, height, color = running + v, -v, "#9ca3af"\n'
         '        running += v\n'
         '    ax.bar(i, height, bottom=bottom, color=color, width=0.6)\n'
         '    ax.text(i, bottom + height + 2, f"${abs(v):,.1f}M", ha="center", fontsize=9)\n'
         'ax.set_xticks(range(len(steps) + 1), [s for s, _ in steps] + ["Net loss"], fontsize=8)\n'
         'ax.set_ylabel("$ millions per year")\n'
         'ax.set_title("Where the money goes: gross disputed value to net loss (illustrative)")\n'
         'ax.spines[["top", "right"]].set_visible(False)\n'
         'ax.grid(axis="y", color="#e5e7eb"); ax.set_axisbelow(True)\n'
         'plt.tight_layout(); plt.show()'),
    md("## Cell 3: the baseline Dispute Ledger\n\n"
       "Every dollar of the combined loss and operating cost is assigned to exactly one "
       "lever. The assignment rules used for the baseline:\n\n"
       "| Cost | Lever | Why |\n|---|---|---|\n"
       "| Written-off loss on **unauthorized** claims | Prevent | stoppable at authorization |\n"
       "| Written-off loss on **defective** claims | Deflect | resolvable by refund or merchant contact before it is formal |\n"
       "| Written-off loss on **first-party** claims | Decide | a customer-treatment decision to accept rather than contest |\n"
       "| Handling cost of every case | Decide | classification, auto-decisioning, evidence automation |\n"
       "| Loss where the merchant's representment succeeded | Recover | contest quality and contest-or-accept rules |"),
    code('def lever(row):\n'
         '    if row["outcome"] == "written_off":\n'
         '        return {"unauthorized": "Prevent", "defective": "Deflect",\n'
         '                "first_party": "Decide"}[row["family"]]\n'
         '    if row["outcome"] == "won":\n'
         '        return "Recover"\n'
         '    return None\n'
         '\n'
         'loss_lever = disputes.apply(lever, axis=1)\n'
         'ledger = (disputes.assign(lever=loss_lever)\n'
         '          .groupby("lever")["net_loss"].sum() * SCALE / 1e6)\n'
         'ledger["Decide"] += disputes["handling_cost"].sum() * SCALE / 1e6\n'
         'ledger = (ledger.reindex(["Prevent", "Deflect", "Decide", "Recover"])\n'
         '          .rename("annual_cost_$m").to_frame())\n'
         'ledger["share"] = ledger["annual_cost_$m"] / ledger["annual_cost_$m"].sum()\n'
         'ledger["chapters"] = ["6, 7", "3, 13", "8, 9, 11, 12", "10, 12"]\n'
         'print(f"Combined loss and operating cost: ${ledger[\'annual_cost_$m\'].sum():,.1f}M")\n'
         'ledger.round(3)'),
    code('fig, ax = plt.subplots(figsize=(7, 2.8))\n'
         'ax.barh(ledger.index[::-1], ledger["annual_cost_$m"][::-1], color="#2a6fdb", height=0.55)\n'
         'for y, (v, s) in enumerate(zip(ledger["annual_cost_$m"][::-1], ledger["share"][::-1])):\n'
         '    ax.text(v + 0.5, y, f"${v:,.1f}M ({s:.0%})", va="center", fontsize=9)\n'
         'ax.set_xlabel("$ millions per year")\n'
         'ax.set_title("Baseline Dispute Ledger (illustrative)")\n'
         'ax.spines[["top", "right"]].set_visible(False)\n'
         'ax.set_xlim(0, ledger["annual_cost_$m"].max() * 1.35)\n'
         'plt.tight_layout(); plt.show()'),
    md("Save the baseline Ledger, the chapter artifact that later chapters update."),
    code('ledger.round(4).to_csv("baseline_ledger.csv")\n'
         'print(open("baseline_ledger.csv").read())'),
]

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nbf.write(nb, HERE / "explore.ipynb")
print("wrote explore.ipynb")
