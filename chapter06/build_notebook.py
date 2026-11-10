"""Build first_party_signals.ipynb, the signal notebook referenced in the chapter's Further reading.

Run:  python build_notebook.py
Then: python -m nbconvert --to notebook --execute --inplace first_party_signals.ipynb
"""
from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).resolve().parent

cells = [
    nbf.v4.new_markdown_cell(
        "# Chapter 6: First-party signals\n\n"
        "This notebook walks through `first_party_signals.py` on the extended synthetic dataset "
        "(`disputes_extended.csv`, built by `make_data.py`). It covers dispute concentration, per-cardholder "
        "signals, tiers with reasons, and the contest threshold of Table 6.3. All data are synthetic."
    ),
    nbf.v4.new_code_cell(
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n"
        "from first_party_signals import (AS_OF, load, first_party_only, concentration, build_signals,\n"
        "                                 score_signals, contest_threshold, threshold_table)\n"
        "pd.set_option('display.width', 140)\n"
        "disputes = load()\n"
        "print(f\"Disputes: {len(disputes):,}; disputing cardholders: {disputes['card_id'].nunique():,}\")\n"
        "disputes.head()"
    ),
    nbf.v4.new_markdown_cell("## Concentration: a few cardholders raise a large share of disputes"),
    nbf.v4.new_code_cell(
        "print(f'Top 3% of disputing cardholders raise {concentration(disputes):.1%} of all disputes')\n"
        "counts = disputes['card_id'].value_counts().sort_values(ascending=False)\n"
        "share = counts.cumsum() / counts.sum()\n"
        "ax = (share.reset_index(drop=True)\n"
        "      .set_axis((pd.RangeIndex(len(share)) + 1) / len(share))\n"
        "      .plot(figsize=(6, 4)))\n"
        "ax.set_xlabel('Share of disputing cardholders (ranked)')\n"
        "ax.set_ylabel('Cumulative share of disputes')\n"
        "ax.set_title('Dispute concentration (synthetic)')\n"
        "plt.show()"
    ),
    nbf.v4.new_markdown_cell(
        "## Signals and tiers\n\n"
        "Signals are built on first-party claims only, over a 90-day window. "
        "Without that family gate, bursts of unauthorized claims from compromised cards would look like misuse."
    ),
    nbf.v4.new_code_cell(
        "scored = score_signals(build_signals(first_party_only(disputes), AS_OF))\n"
        "print(f'Cardholders scored as of {AS_OF[:10]}: {len(scored):,}')\n"
        "scored['tier'].value_counts().reindex(['standard', 'clarify', 'review'])"
    ),
    nbf.v4.new_code_cell(
        "cols = ['claims', 'not_received_share', 'top_merchant_share', 'proof_rate',\n"
        "        'median_gap_days', 'points', 'tier']\n"
        "# Table 6.5: sample output of the signal pipeline\n"
        "scored.loc[['c741', 'c2677', 'c3578'], cols].round(2)"
    ),
    nbf.v4.new_code_cell(
        "# Worked example: four not-received claims at four merchants\n"
        "scored.loc[['c1024'], cols + ['reasons']].round(2)"
    ),
    nbf.v4.new_code_cell(
        "ax = scored['points'].value_counts().sort_index().plot.bar(figsize=(6, 3.5))\n"
        "ax.set_xlabel('Signal points'); ax.set_ylabel('Cardholders')\n"
        "ax.set_title('Distribution of signal points (synthetic)')\n"
        "plt.show()"
    ),
    nbf.v4.new_markdown_cell(
        "## Contest threshold\n\n"
        "Contest a claim of amount A only when p_win × A exceeds the handling cost plus the expected loss of "
        "relationship value: A > (c + q·V) / p."
    ),
    nbf.v4.new_code_cell(
        "print(f'Threshold with no relationship value: ${contest_threshold(0.42, 40, 0.05, 0):,.0f}')\n"
        "threshold_table()  # Table 6.3 (c = $40, q = 0.05)"
    ),
]

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(nb, HERE / "first_party_signals.ipynb")
print("wrote first_party_signals.ipynb")
