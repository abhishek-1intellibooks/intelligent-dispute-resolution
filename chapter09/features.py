"""Intake features shared by training and serving (Listing 9.1).

AVAILABLE_AT registers the moment each column becomes known; intake_view
refuses any column that is not known when the claim is received, so a late
feature fails loudly at training time instead of silently in production.
"""
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import (FunctionTransformer, OneHotEncoder,
                                   StandardScaler)

# Every column, and the moment it becomes known
AVAILABLE_AT = {
    "channel": "intake", "product": "intake", "amount": "intake",
    "intake_reason": "intake", "narrative": "intake", "mcc_group": "intake",
    "card_present": "intake", "three_ds": "intake", "device_known": "intake",
    "recurring": "intake", "security_alert_7d": "intake",
    "days_since_txn": "intake", "tenure_months": "intake",
    "prior_disputes_12m": "intake", "delivery_status": "intake",
    "link_completeness": "intake", "needs_review": "intake",
    "first_touch_on": "investigation", "work_days": "decision",
    "decided_on": "decision", "family": "decision", "breached": "decision",
}
CATEGORICAL = ["channel", "product", "intake_reason", "mcc_group",
               "delivery_status"]
FLAGS = ["card_present", "three_ds", "device_known", "recurring",
         "security_alert_7d", "needs_review"]
NUMERIC = ["amount", "days_since_txn", "tenure_months", "prior_disputes_12m",
           "link_completeness"]
TEXT = "narrative"
STOP = ["a", "an", "and", "the", "my", "i", "it", "on", "of", "to", "was",
        "this", "is", "but"]                # "not" is kept on purpose


def intake_view(df, columns=CATEGORICAL + FLAGS + NUMERIC + [TEXT]):
    late = [c for c in columns if AVAILABLE_AT.get(c) != "intake"]
    if late:
        raise ValueError(f"not known at intake: {late}")
    return df[columns]


def preprocessor(columns=None):
    """The four feature groups as one matrix. `columns` (optional) keeps only
    those inputs, which train_classifier.py uses to measure each group."""
    keep = (lambda cols: cols) if columns is None else (
        lambda cols: [c for c in cols if c in columns])
    parts = [
        ("cat", OneHotEncoder(handle_unknown="ignore"), keep(CATEGORICAL)),
        ("flag", OneHotEncoder(drop="if_binary"), keep(FLAGS)),
        ("num", make_pipeline(
            FunctionTransformer(np.log1p, feature_names_out="one-to-one"),
            StandardScaler()), keep(NUMERIC)),
        ("text", TfidfVectorizer(ngram_range=(1, 2), min_df=5,
                                 stop_words=STOP, sublinear_tf=True), TEXT),
    ]
    if columns is not None and TEXT not in columns:
        parts = parts[:3]
    return ColumnTransformer([p for p in parts if p[0] == "text" or p[2]])
