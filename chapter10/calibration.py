"""A trained model plus a calibration map fitted on unbiased cases (Listing 10.3)."""
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p)).reshape(-1, 1)


class Calibrated:
    """A trained model plus a calibration map fitted on unbiased cases."""

    def __init__(self, model, method="platt"):
        self.model, self.method = model, method

    def fit(self, X, y):
        raw = self.model.predict_proba(X)[:, 1]
        if self.method == "platt":               # two numbers: slope, shift
            self.map = LogisticRegression(C=1e6).fit(logit(raw), y)
        else:                                      # any monotone curve
            self.map = IsotonicRegression(out_of_bounds="clip").fit(raw, y)
        return self

    def predict_proba(self, X):
        raw = self.model.predict_proba(X)[:, 1]
        if self.method == "platt":
            return self.map.predict_proba(logit(raw))[:, 1]
        return self.map.predict(raw)


def expected_calibration_error(y, p, bins=10):
    """Mean gap between predicted and observed win rates, by bin size."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    return sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).mean()
               for b in range(bins) if (idx == b).any())
