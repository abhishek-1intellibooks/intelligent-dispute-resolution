"""Specific reasons from a logistic model's score (Listing 15.1).

A logistic regression's log-odds is a sum of one term per feature, so each
feature's contribution to one case is its coefficient times the case's
standardized value: how far the case lies from the average, in the model's
units. reason_codes returns at most k reasons that RAISED the score, each in
words a customer can understand and act on.
"""
REASON_TEXT = {
    "days_to_file": "The claim was made {value:.0f} days after the purchase",
    "prior_disputes_12m": "{value:.0f} other disputes were made in the last 12 months",
    "amount": "The amount of the transaction",
    "new_device": "The claim was made from a device not used before on the account",
    # The two proxy features of the first model version (Table 15.4); kept so the
    # earlier version can be explained too. Neither is used by the live flag.
    "narrative_words": "The description of the problem was {value:.0f} words long",
    "app_tenure_months": "The mobile application had been used for {value:.0f} months",
}


def reason_codes(model, scaler, features, row, k=3, floor=0.10):
    """Specific reasons that raised this case's score, largest first."""
    x = scaler.transform(row[features].astype(float).to_numpy().reshape(1, -1))[0]
    contrib = x * model.coef_[0]                   # exact for a logistic model
    ranked = sorted(zip(features, contrib), key=lambda kv: -kv[1])
    return [{"feature": f, "contribution": round(float(c), 3),
             "text": REASON_TEXT[f].format(value=row[f])}
            for f, c in ranked[:k] if c >= floor]


def contributions(model, scaler, features, row):
    """Every feature's contribution to the log-odds (for Figure 15.2)."""
    x = scaler.transform(row[features].astype(float).to_numpy().reshape(1, -1))[0]
    return {f: round(float(c), 3) for f, c in zip(features, x * model.coef_[0])}
