"""Outcomes and errors by customer segment (Listing 15.2)."""
import pandas as pd


def fairness_report(df, segment, reference, flag="flag", truth="misuse", min_n=200):
    """Flag rates and error rates by segment, with ratios to a reference group."""
    rows = []
    for name, g in df.groupby(segment):
        rows.append({
            "segment": name, "n": len(g),
            "flag_rate": g[flag].mean(),
            "wrongly_flagged": g.loc[~g[truth], flag].mean(),    # false positive rate
            "misuse_found": g.loc[g[truth], flag].mean(),        # true positive rate
        })
    out = pd.DataFrame(rows).set_index("segment")
    ref = out.loc[reference]
    out["flag_ratio"] = out.flag_rate / ref.flag_rate
    out["error_ratio"] = out.wrongly_flagged / ref.wrongly_flagged
    out["enough_data"] = out.n >= min_n
    return out.round(3)
