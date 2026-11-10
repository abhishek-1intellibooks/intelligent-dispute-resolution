"""Train and evaluate the family classifier (Listings 9.2 and 9.3).

Run:  python train_classifier.py
Splits claims_closed.csv by time (train Jan-Aug, validation Sep-Oct, test
Nov-Dec), compares two rule baselines with logistic regression and gradient-
boosted trees on the test months (Table 9.4), measures what each feature
group adds (Table 9.6) and the abstention trade-off (Table 9.7), and saves
the logistic regression as triage_model.joblib with its version.
"""
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score
from sklearn.pipeline import make_pipeline

from features import CATEGORICAL, FLAGS, NUMERIC, TEXT, intake_view, preprocessor

warnings.filterwarnings("ignore", category=DeprecationWarning)
HERE = Path(__file__).resolve().parent
MODEL_VERSION = "triage-family-1.0"

FAMILIES = ["unauthorized", "defective", "first_party"]
COST = np.array([[0, 60, 150],      # true unauthorized predicted as each family
                 [35, 0, 80],       # true defective
                 [45, 25, 0]])      # true first-party (illustrative dollars)
REASON_RULE = {"fraud": "unauthorized", "not_recognized": "unauthorized"}

df = pd.read_csv(HERE / "claims_closed.csv", parse_dates=["claim_received_at"])
when = df.claim_received_at
train = df[when < "2025-09-01"]
valid = df[(when >= "2025-09-01") & (when < "2025-11-01")]
test = df[when >= "2025-11-01"]


def reason_rule(d):
    return d.intake_reason.map(REASON_RULE).fillna("defective")


def rule_plus_points(d):
    pred = reason_rule(d).copy()
    pattern = (d.prior_disputes_12m >= 2) & (d.delivery_status == "confirmed")
    pred[pattern & (d.intake_reason != "fraud")] = "first_party"
    return pred


def report(name, y, pred):
    cm = confusion_matrix(y, pred, labels=FAMILIES)
    recall = recall_score(y, pred, labels=FAMILIES, average=None)
    return {"model": name, "accuracy": accuracy_score(y, pred),
            "macro_f1": f1_score(y, pred, average="macro"),
            "recall": dict(zip(FAMILIES, recall)),
            "cost_per_1000": (cm * COST).sum() / len(y) * 1000,
            "confusion": cm.tolist()}


def logit_pipeline(columns=None):
    return make_pipeline(preprocessor(columns), LogisticRegression(C=2.0, max_iter=3000))


ALL = CATEGORICAL + FLAGS + NUMERIC + [TEXT]
ABLATIONS = {
    "All features": ALL,
    "Without the narrative": [c for c in ALL if c != TEXT],
    "Narrative only": [TEXT],
    "Without intake_reason": [c for c in ALL if c != "intake_reason"],
    "Without customer history": [c for c in ALL if c not in
                                 ("tenure_months", "prior_disputes_12m", "security_alert_7d")],
    "Without linkage (Chapter 8)": [c for c in ALL if c not in
                                    ("delivery_status", "link_completeness", "needs_review")],
}


def main():
    print(f"train {len(train):,}  valid {len(valid):,}  test {len(test):,} claims")
    print("family shares, whole year:", df.family.value_counts(normalize=True).round(3).to_dict())

    logit = make_pipeline(preprocessor(), LogisticRegression(C=2.0, max_iter=3000))
    logit.fit(intake_view(train), train.family)
    boost = make_pipeline(preprocessor(), HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, random_state=9))
    boost.set_params(columntransformer__sparse_threshold=0,
                     columntransformer__text__max_features=300)
    boost.fit(intake_view(train), train.family)

    X_valid = intake_view(valid)
    print(f"validation accuracy: logistic {accuracy_score(valid.family, logit.predict(X_valid)):.3f}, "
          f"boosted {accuracy_score(valid.family, boost.predict(X_valid)):.3f}")

    X_test, y_test = intake_view(test), test.family
    results = [report("Reason-code rule", y_test, reason_rule(test)),
               report("Rule + first-party points", y_test, rule_plus_points(test)),
               report("Logistic regression", y_test, logit.predict(X_test)),
               report("Gradient-boosted trees", y_test, boost.predict(X_test))]

    print(f"\nTable 9.4  Four classifiers on the test months ({len(test):,} claims, "
          f"{(y_test == 'first_party').sum():,} first-party)")
    print(f"{'Approach':28s} {'Acc':>6s} {'MacroF1':>8s} {'R unauth':>9s} {'R defect':>9s} "
          f"{'R 1st-p':>8s} {'Cost/1000':>10s}")
    for r in results:
        rc = r["recall"]
        print(f"{r['model']:28s} {r['accuracy']:6.1%} {r['macro_f1']:8.2f} {rc['unauthorized']:9.1%} "
              f"{rc['defective']:9.1%} {rc['first_party']:8.1%} {r['cost_per_1000']:10,.0f}")
    print("\nConfusion, logistic regression (rows: family at closure; columns: predicted)")
    print(pd.DataFrame(results[2]["confusion"], index=FAMILIES, columns=FAMILIES).to_string())
    print("Confusion, reason-code rule")
    print(pd.DataFrame(results[0]["confusion"], index=FAMILIES, columns=FAMILIES).to_string())

    # abstention: route the least confident claims to a person
    proba = logit.predict_proba(X_test)
    conf, pred = proba.max(axis=1), logit.classes_[proba.argmax(axis=1)]
    right = pred == y_test.to_numpy()
    curve = []
    for tau in np.round(np.arange(0.34, 0.96, 0.01), 2):
        auto = conf >= tau                         # confident enough to route
        curve.append({"tau": float(tau), "coverage": float(auto.mean()),
                      "accuracy": float(right[auto].mean())})
    print("\nTable 9.7  Coverage against accuracy (test months)")
    print(f"{'tau':>5s} {'routed':>8s} {'accuracy':>9s} {'review':>8s}")
    for c in curve:
        if c["tau"] in (0.5, 0.6, 0.7, 0.8, 0.9):
            print(f"{c['tau']:5.1f} {c['coverage']:8.1%} {c['accuracy']:9.1%} {1 - c['coverage']:8.1%}")

    print("\nTable 9.6  What each feature group adds (logistic regression, test months)")
    ablation = []
    for name, cols in ABLATIONS.items():
        m = logit if name == "All features" else logit_pipeline(cols).fit(
            intake_view(train, cols), train.family)
        p = m.predict(intake_view(test, cols))
        a, f1 = accuracy_score(y_test, p), f1_score(y_test, p, average="macro")
        ablation.append({"features": name, "accuracy": a, "macro_f1": f1})
        print(f"  {name:30s} {a:6.1%} {f1:6.3f}")

    joblib.dump({"family": logit, "version": MODEL_VERSION}, HERE / "triage_model.joblib")
    with open(HERE / "classifier_results.json", "w") as fh:
        json.dump({"results": results, "abstention": curve, "ablation": ablation}, fh, indent=1)
    print(f"\nsaved triage_model.joblib ({MODEL_VERSION}) and classifier_results.json")


if __name__ == "__main__":
    main()
