"""Features for the win model, each registered with the moment it becomes known.

Listing 10.1. The decision view refuses any column that is not known when the
contest is decided, and the registry names the columns only the simulator knows.
"""
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import (FunctionTransformer, OneHotEncoder,
                                   StandardScaler)

# Every column, and the moment it becomes known
AVAILABLE_AT = {
    "amount": "decision", "network": "decision", "reason": "decision",
    "mcc_group": "decision", "liability_shift": "decision",
    "ce3_eligible": "decision",
    "merchant_tracking": "decision", "merchant_responded": "decision",
    "merchant_rep_rate": "decision", "merchant_win_rate": "decision",
    "days_to_file": "decision", "evidence_completeness": "decision",
    "first_party_score": "decision", "prior_disputes_12m": "decision",
    "contested": "decision", "exploration": "decision",
    "won": "outcome", "won_if_contested": "simulator", "p_true": "simulator",
}
# Identifiers and the outcome stage, also in contest_history.csv
AVAILABLE_AT.update({"case_id": "decision", "decided_at": "decision",
                     "outcome_stage": "outcome"})

CATEGORICAL = ["network", "reason", "mcc_group", "merchant_tracking"]
FLAGS = ["liability_shift", "ce3_eligible", "merchant_responded"]
NUMERIC = ["amount", "merchant_rep_rate", "merchant_win_rate", "days_to_file",
           "evidence_completeness", "first_party_score", "prior_disputes_12m"]
FEATURES = CATEGORICAL + FLAGS + NUMERIC


def decision_view(df, columns=FEATURES):
    late = [c for c in columns if AVAILABLE_AT.get(c) != "decision"]
    if late:
        raise ValueError(f"not known when the contest is decided: {late}")
    return df[columns]


def preprocessor(dense=False):
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("flag", OneHotEncoder(drop="if_binary"), FLAGS),
        ("num", make_pipeline(
            FunctionTransformer(np.log1p, feature_names_out="one-to-one"),
            StandardScaler()), NUMERIC),
    ], sparse_threshold=0 if dense else 0.3)
