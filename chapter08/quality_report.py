"""Quality rules, link scoring and the worked example (Tables 8.4, 8.5, 8.6).

Run after assemble_case.py:  python quality_report.py
Every check is a query against dispute.db, so it can run after every load.
Link accuracy is scored against truth_links.csv, written by make_sources.py.
Also demonstrates the null-key trap: a pandas join on a column containing
missing values matches missing to missing.
"""
import warnings
from pathlib import Path

import pandas as pd

from store import DB_PATH, connect, load_sources

warnings.filterwarnings("ignore", category=DeprecationWarning)
HERE = Path(__file__).resolve().parent

QUALITY_RULES = [
    ("Completeness", "Cases with clearing, authorization, and order all linked",
     "SELECT SUM(completeness = 3), COUNT(*) FROM case_record"),
    ("Completeness", "Clearing records with an authorization code",
     "SELECT SUM(auth_code IS NOT NULL), COUNT(*) FROM clearing"),
    ("Completeness", "Merchant orders with an authorization code",
     "SELECT SUM(auth_code IS NOT NULL), COUNT(*) FROM merchant_order"),
    ("Validity", "Clearing records dated before their own authorization (violations)",
     """SELECT SUM(c.cleared_at < a.authorized_at), COUNT(*) FROM clearing c
        JOIN authorization a ON a.auth_code = c.auth_code AND a.merchant_id = c.merchant_id"""),
    ("Consistency", "Linked claims whose amount differs from cleared by more than 1%",
     """SELECT SUM(ABS(cl.claimed_amount - r.amount) > 0.01 * r.amount), COUNT(*)
        FROM case_record k JOIN crm_claim cl ON cl.claim_id = k.claim_id
        JOIN clearing r ON r.arn = k.arn"""),
    ("Uniqueness", "Live cases sharing an ARN (violations)",
     """SELECT COUNT(*), (SELECT COUNT(*) FROM case_record WHERE duplicate_of IS NOT NULL)
        FROM (SELECT arn FROM case_record WHERE arn IS NOT NULL AND duplicate_of IS NULL
              GROUP BY arn HAVING COUNT(*) > 1)"""),
]


def quality(con):
    rows = []
    for dim, rule, sql in QUALITY_RULES:
        a, b = con.execute(sql).fetchone()
        rows.append((dim, rule, a, b))
    return pd.DataFrame(rows, columns=["dimension", "rule", "count", "of"])


def score(con, truth):
    """Claim links are scored against the claim's true record; authorization and
    order links against the true records behind the clearing record linked."""
    cases = pd.read_sql("SELECT * FROM case_record", con)
    links = pd.read_sql("SELECT * FROM case_source_link", con)
    claim_truth = truth[truth.claim_id.notna()][["claim_id", "arn"]]
    record_truth = truth[truth.claim_id.isna()].set_index("arn")
    df = cases.merge(claim_truth, on="claim_id", suffixes=("", "_true"))
    df["auth_id_true"] = df.arn.map(record_truth.auth_id)
    df["order_id_true"] = df.arn.map(record_truth.order_id)
    out = []
    for source, col in [("clearing", "arn"), ("authorization", "auth_id"), ("merchant_order", "order_id")]:
        lk = links[links.source == source].set_index("case_id")
        made = df[df[col].notna()]
        correct = (made[col] == made[f"{col}_true"]).sum()
        methods = lk.match_method.value_counts().to_dict()
        base = len(df) if source == "clearing" else df.arn.notna().sum()
        out.append(dict(link=source, linked=len(made), of=base,
                        by_key_or_name=methods.get("key", 0) + methods.get("name", 0),
                        by_fallback=methods.get("fuzzy", 0) + methods.get("amount_only", 0),
                        unlinked=base - len(made), correct=int(correct),
                        accuracy=round(float(correct / len(made)), 3)))
    linkable = df.arn_true.notna().sum()
    right = (df.arn == df.arn_true).sum()
    wrong = df[df.arn.notna() & (df.arn != df.arn_true)]
    review = df[df.needs_review == 1]
    ambiguous = review[review.arn.notna()]
    summary = dict(linkable=int(linkable), linked_correctly=int(right),
                   recall=round(float(right / linkable), 3), wrong_links=len(wrong),
                   wrong_links_flagged=int(wrong.needs_review.sum()),
                   flagged_for_review=len(review), ambiguous=len(ambiguous),
                   unlinked=int(df.arn.isna().sum()))
    return pd.DataFrame(out), summary


def null_key_trap(src):
    clr, orders = src["clearing"], src["merchant_order"]
    naive = clr.merge(orders, on=["auth_code", "merchant_id"])          # NaN matches NaN
    safe = clr.dropna(subset=["auth_code"]).merge(
        orders.dropna(subset=["auth_code"]), on=["auth_code", "merchant_id"])
    return len(naive), len(safe)


def worked_example(con, claim_id="C00001"):
    case_id = con.execute("SELECT case_id FROM case_record WHERE claim_id = ?", (claim_id,)).fetchone()[0]
    flat = pd.read_sql("SELECT * FROM case_flat WHERE case_id = ?", con, params=(case_id,))
    prov = pd.read_sql("SELECT source, source_id, match_method, confidence FROM case_source_link "
                       "WHERE case_id = ?", con, params=(case_id,))
    return case_id, flat.T, prov


if __name__ == "__main__":
    pd.set_option("display.width", 140, "display.max_columns", 20, "display.max_colwidth", 70)
    src = load_sources()
    truth = pd.read_csv(HERE / "truth_links.csv")
    con = connect(DB_PATH)
    print("Table 8.4  Quality rules")
    print(quality(con).to_string(index=False))
    naive, safe = null_key_trap(src)
    print(f"\nNull-key trap: clearing-to-order join on (auth_code, merchant_id) gives "
          f"{naive:,} rows with nulls matched, {safe:,} without")
    table, summary = score(con, truth)
    print("\nTable 8.5  How each link was made (scored against truth_links.csv)")
    print(table.to_string(index=False))
    print("\nClaim-to-clearing summary:", summary)
    case_id, flat, prov = worked_example(con)
    print(f"\nTable 8.6  The assembled record for {case_id} (claim C00001)")
    print(flat.to_string(header=False))
    print(prov.to_string(index=False))
    con.close()
