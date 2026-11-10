"""Linking rules for the dispute case record (Listing 8.2).

Every link is attempted deterministically first and by a fallback second, and
every link reports the method that produced it and a confidence. The rules
and their thresholds live here, in one module, so they can be versioned and
tested against the truth file written by make_sources.py.
"""
import difflib

import pandas as pd


def norm(text):
    return "".join(ch for ch in str(text).lower() if ch.isalpha())


def similar(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def link_claim(claim, clearing, window_days=120, min_sim=0.6):
    near = clearing[(clearing.card_token == claim.card_token)
        & ((clearing.amount - claim.claimed_amount).abs() <= 0.10 * claim.claimed_amount)
        & (clearing.cleared_at <= claim.claim_received_at)
        & (clearing.cleared_at >= claim.claim_received_at - pd.Timedelta(days=window_days))]
    scored = sorted(((similar(claim.merchant_stated, d.descriptor), d.cleared_at, d.arn)
                     for d in near.itertuples()), reverse=True)
    if scored and scored[0][0] >= min_sim:
        close = len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05
        return scored[0][2], "name", round(scored[0][0], 2), close
    if len(scored) == 1:
        return scored[0][2], "amount_only", 0.30, False
    return None, "none", 0.0, False


def match(clr, pool, id_col, amt_col, ts_col, days=4, tol=0.01):
    if pd.notna(clr.auth_code):                       # never join on a null key
        hit = pool[(pool.auth_code == clr.auth_code)
                   & (pool.merchant_id == clr.merchant_id)]
        if len(hit) == 1:
            return hit.iloc[0][id_col], "key", 1.0
    cand = pool[(pool.merchant_id == clr.merchant_id)
        & ((pool[amt_col] - clr.amount).abs() <= tol * clr.amount)
        & (pool[ts_col] <= clr.cleared_at)
        & (pool[ts_col] >= clr.cleared_at - pd.Timedelta(days=days))]
    if "card_token" in pool.columns:
        cand = cand[cand.card_token == clr.card_token]
    if len(cand):
        best = (clr.cleared_at - cand[ts_col]).abs().idxmin()
        return cand.loc[best, id_col], "fuzzy", 0.7
    return None, "none", 0.0
