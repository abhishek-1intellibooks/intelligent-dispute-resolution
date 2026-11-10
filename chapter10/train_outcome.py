"""Train and calibrate the win model (Listing 10.2, Table 10.3, Figures 10.2 and 10.3).

Decisions from January to August are used for learning, September to December
for testing. Within the learning months the analysts' contested cases train
the models (many labels, biased) and the exploration cases fit the calibration
map (few labels, unbiased).

Writes outcome_logistic_platt.joblib, the calibrated model that
fight_or_accept.py loads, and figures/ for the reliability diagram.
"""
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline

from calibration import Calibrated, expected_calibration_error
from outcome_features import decision_view, preprocessor

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
FIGURES = HERE / "figures"
MODEL_FILE = HERE / "outcome_logistic_platt.joblib"


def load_splits():
    df = pd.read_csv(HERE / "contest_history.csv", parse_dates=["decided_at"])
    early = df.decided_at < "2025-09-01"
    train = df[early & df.contested & ~df.exploration]   # many labels, biased
    calib = df[early & df.exploration]                   # few labels, unbiased
    test = df[~early & df.contested]                     # September to December
    test_x = df[~early & df.exploration]                 # unbiased test labels
    return df, train, calib, test, test_x


def make_models():
    return {
        "Logistic regression": make_pipeline(
            preprocessor(), LogisticRegression(C=1.0, max_iter=2000)),
        "Gradient-boosted trees": make_pipeline(
            preprocessor(dense=True), HistGradientBoostingClassifier(
                max_iter=250, learning_rate=0.05, max_leaf_nodes=15,
                l2_regularization=1.0, random_state=10)),
    }


def evaluate(name, model, test, test_x):
    p_rank = model.predict_proba(decision_view(test))
    p = model.predict_proba(decision_view(test_x))
    p_rank = p_rank[:, 1] if p_rank.ndim == 2 else p_rank
    p = p[:, 1] if p.ndim == 2 else p
    y = test_x.won.to_numpy()
    return {"model": name,
            "AUC": roc_auc_score(test.won, p_rank),
            "Brier": brier_score_loss(y, p),
            "Log loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)),
            "ECE": expected_calibration_error(y, p),
            "Mean predicted": p.mean(), "Observed": y.mean()}


def reliability(y, p, bins=6):
    order = np.argsort(p)
    groups = np.array_split(order, bins)               # bins of equal size
    return (np.array([p[g].mean() for g in groups]),
            np.array([y[g].mean() for g in groups]))


def main():
    df, train, calib, test, test_x = load_splits()
    print(f"train {len(train):,} | calib {len(calib):,} | "
          f"test {len(test):,} | test_x {len(test_x):,}")
    print(f"Win rate: analysts' contested cases {df[df.contested & ~df.exploration].won.mean():.1%}, "
          f"exploration sample {df[df.exploration].won.mean():.1%}  (Figure 10.2)")

    rows, fitted = [], {}
    for name, model in make_models().items():
        model.fit(decision_view(train), train.won.astype(int))
        rows.append(evaluate(name, model, test, test_x))
        for method, label in (("platt", "  + Platt scaling"),
                              ("isotonic", "  + isotonic regression")):
            cal = Calibrated(model, method).fit(decision_view(calib),
                                                calib.won.astype(int))
            fitted[(name, method)] = cal
            rows.append(evaluate(label, cal, test, test_x))

    table = pd.DataFrame(rows).set_index("model")
    fmt = {"AUC": "{:.3f}", "Brier": "{:.3f}", "Log loss": "{:.3f}", "ECE": "{:.3f}",
           "Mean predicted": "{:.1%}", "Observed": "{:.1%}"}
    print("\nTable 10.3: discrimination and calibration on the test months")
    print(table.apply(lambda c: c.map(fmt[c.name].format)).to_string())

    best = fitted[("Logistic regression", "platt")]
    slope, shift = best.map.coef_[0, 0], best.map.intercept_[0]
    print(f"\nPlatt map for logistic regression: slope {slope:.2f}, shift {shift:+.2f}")
    joblib.dump(best, MODEL_FILE)
    print(f"saved {MODEL_FILE.name}")

    # Figure 10.3: reliability on the test exploration cases
    FIGURES.mkdir(exist_ok=True)
    raw_model = best.model
    y = test_x.won.to_numpy()
    raw = raw_model.predict_proba(decision_view(test_x))[:, 1]
    cal = best.predict_proba(decision_view(test_x))
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], ls=":", color="grey")
    for p, label, marker in ((raw, "Before calibration", "o"),
                             (cal, "After Platt scaling", "s")):
        px, py = reliability(y, p)
        ax.plot(px, py, marker=marker, label=label)
    ax.set_xlabel("Predicted win rate")
    ax.set_ylabel("Observed win rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    ax.set_title(f"Reliability on {len(test_x):,} test exploration cases")
    fig.tight_layout()
    fig.savefig(FIGURES / "fig10_3_reliability.png", dpi=120)
    print("saved figures/fig10_3_reliability.png")


if __name__ == "__main__":
    main()
