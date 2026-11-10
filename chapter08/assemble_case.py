"""Assemble one case record per claim from four feeds (Listing 8.3).

Run:  python assemble_case.py
Reads the four CSV feeds, links each claim to clearing, authorization and
merchant order records, and writes sources and cases to dispute.db.
"""
import pandas as pd

from linking import link_claim, match
from store import load_sources, save

# (source table, id column, amount column, timestamp column)
SECONDARY = [("authorization", "auth_id", "amount", "authorized_at"),
             ("merchant_order", "order_id", "order_total", "ordered_at")]


def assemble(src, rule_version="link-rules-1.0"):
    clearing = src["clearing"].set_index("arn", drop=False)
    cases, links, first_for = [], [], {}
    for n, claim in enumerate(src["crm_claim"].sort_values("claim_received_at").itertuples(), 1):
        case_id = f"CASE{n:05d}"
        arn, how, conf, close = link_claim(claim, src["clearing"])
        links.append((case_id, "crm_claim", claim.claim_id, "key", 1.0))
        row = dict(case_id=case_id, claim_id=claim.claim_id, arn=arn,
                   auth_id=None, order_id=None, completeness=int(arn is not None),
                   claim_received_at=claim.claim_received_at,
                   needs_review=int(close or arn is None),
                   duplicate_of=first_for.get(arn) if arn else None,
                   rule_version=rule_version)
        if arn:
            first_for.setdefault(arn, case_id)
            links.append((case_id, "clearing", arn, how, conf))
            clr = next(clearing.loc[[arn]].itertuples())
            for table, col, amt, ts in SECONDARY:
                found, how2, conf2 = match(clr, src[table], col, amt, ts)
                row[col] = found
                row["completeness"] += found is not None
                links.append((case_id, table, found, how2, conf2))
        cases.append(row)
    names = ["case_id", "source", "source_id", "match_method", "confidence"]
    return pd.DataFrame(cases), pd.DataFrame(links, columns=names)


if __name__ == "__main__":
    src = load_sources()
    cases, links = assemble(src)
    save(src, cases, links)
    print(len(cases), "cases;", cases.completeness.value_counts().sort_index().to_dict())
