"""Expected effort, the SLA-risk model, priority bands and the queue replay.

Run after train_classifier.py:  python sla_risk.py
  * Table 9.8: average effort by family, delivery record and review flag
  * the SLA-risk logistic regression on slack, queue and expected effort,
    with its ranking power and calibration on the test months (Figure 9.5)
  * Table 9.9: priority bands on the test months
  * Table 9.10: November and December replayed under four ordering policies,
    with the backlog as it stood on 1 November and the same capacity
Saves sla_model.joblib (model, effort table and version).
"""
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict

import queue_sim as qs
from features import intake_view
from priority import FAMILIES, SLA_FEATURES, band, expected_work, sla_frame

warnings.filterwarnings("ignore", category=DeprecationWarning)
HERE = Path(__file__).resolve().parent
SLA_VERSION = "triage-sla-1.0"
SWITCH = "2025-11-01"


def load():
    df = pd.read_csv(HERE / "claims_closed.csv",
                     parse_dates=["claim_received_at", "case_created_at", "first_touch_on",
                                  "decided_on", "due_on"])
    when = df.claim_received_at
    return df, df[when < "2025-09-01"], df[when >= SWITCH]


def family_proba(model, d, out_of_fold=False):
    if out_of_fold:              # training rows: probabilities from models that did not see them
        p = cross_val_predict(model, intake_view(d), d.family, cv=5, method="predict_proba")
    else:
        p = model.predict_proba(intake_view(d))
    return pd.DataFrame(p, columns=model.classes_, index=d.index)


def effort_table(train):
    contact = train.delivery_status.isin(["not_found", "no_link"]).rename("contact")
    return train.groupby(["family", contact, train.needs_review.astype(bool)]).work_days.mean()


def replay(df, p_effort, policy, capacity):
    """Run the queue from SWITCH under a policy; claims already started keep their start."""
    avail = qs.available_day(df.case_created_at)
    due = qs.due_day(df.claim_received_at)
    due_idx = np.busday_count(np.datetime64("2025-01-01"), due).astype(float)
    started = np.where(df.first_touch_on < SWITCH, df.first_touch_on.to_numpy().astype("datetime64[D]"),
                       np.datetime64("NaT"))
    key = {"First in, first out": df.case_created_at.astype("int64").to_numpy().astype(float),
           "Earliest due date": due_idx,
           "Least slack (predicted effort)": due_idx - p_effort,
           "Least slack (perfect foresight)": due_idx - df.work_days.to_numpy()}[policy]
    start, _, _ = qs.run(avail, key, capacity, start=np.datetime64(SWITCH), started=started)
    decided = qs.decided_day(start, df.work_days)
    return pd.DataFrame({"start": pd.to_datetime(start), "breached": decided > due}, index=df.index)


def main():
    df, train, test = load()
    model = joblib.load(HERE / "triage_model.joblib")["family"]

    effort = effort_table(train)
    grid = effort.unstack(["contact", "needs_review"]).round(1)
    grid.columns = [f"{'missing' if c else 'in hand'}{', review' if r else ''}" for c, r in grid.columns]
    print("Table 9.8  Average effort in business days (training months)")
    print(grid.loc[["defective", "first_party", "unauthorized"]].to_string())

    p_train = family_proba(model, train, out_of_fold=True)
    p_test = family_proba(model, test)
    X_train, X_test = sla_frame(train, p_train, effort), sla_frame(test, p_test, effort)
    sla = LogisticRegression(max_iter=1000).fit(X_train[SLA_FEATURES], train.breached)
    print("\nSLA-risk model coefficients:",
          {f: round(float(c), 2) for f, c in zip(SLA_FEATURES, sla.coef_[0])},
          "intercept", round(float(sla.intercept_[0]), 2))

    risk = sla.predict_proba(X_test[SLA_FEATURES])[:, 1]
    y = test.breached.to_numpy()
    top = risk >= np.quantile(risk, 0.9)
    print(f"Test months: AUC {roc_auc_score(y, risk):.2f}; riskiest 10% hold "
          f"{y[top].sum() / y.sum():.0%} of the {y.sum()} breaches")
    bands = pd.cut(risk, [0, 0.05, 0.2, 0.5, 1.0], labels=["<5%", "5-20%", "20-50%", ">=50%"],
                   include_lowest=True)
    calib = pd.DataFrame({"band": bands, "risk": risk, "breached": y}).groupby("band", observed=False).agg(
        claims=("risk", "size"), predicted=("risk", "mean"), observed=("breached", "mean"))
    print("Calibration by risk band (test months)")
    print(calib.to_string(float_format=lambda v: f"{v:.3f}"))
    # left panel of Figure 9.5: risk against queue, slack held at nine days
    for work in (2, 3.5, 5):
        q = np.arange(0, 12.5, 0.5)
        r = sla.predict_proba(pd.DataFrame({"slack_days": 9, "queue_days": q, "expected_work": work}))[:, 1]
        even = q[np.argmax(r >= 0.5)] if (r >= 0.5).any() else None
        print(f"  slack 9, effort {work} days: even odds of breaching at a queue of {even} days")

    fam_pred = p_test.idxmax(axis=1)
    test_bands = [band(r, f, a, s) for r, f, a, s in
                  zip(risk, fam_pred, test.amount, test.security_alert_7d)]
    tb = pd.DataFrame({"band": test_bands, "breached": y})
    summary = tb.groupby("band").agg(claims=("breached", "size"), fifo_breaches=("breached", "sum"))
    summary["share"] = (summary.claims / len(tb)).map("{:.1%}".format)
    print("\nTable 9.9  Priority bands on the test months")
    print(summary.to_string())

    capacity = {np.datetime64(d): int(s) for d, s in
                pd.read_csv(HERE / "capacity.csv").itertuples(index=False)}
    p_all = family_proba(model, df)
    work_hat = expected_work(df, p_all, effort)
    in_test = (df.claim_received_at >= SWITCH).to_numpy()
    print(f"\nTable 9.10  Replaying November and December under four policies ({in_test.sum():,} claims)")
    print(f"{'Policy':34s} {'Breaches':>9s} {'Rate':>6s} {'Unauth.':>8s} {'P95 wait':>9s}")
    rows = []
    for policy in ["First in, first out", "Earliest due date", "Least slack (predicted effort)",
                   "Least slack (perfect foresight)"]:
        out = replay(df, work_hat, policy, capacity)[in_test]
        wait = (out.start - df.claim_received_at[in_test].dt.normalize()).dt.days
        unauth = (out.breached & (df.family[in_test] == "unauthorized")).sum()
        rows.append(dict(policy=policy, breaches=int(out.breached.sum()), rate=float(out.breached.mean()),
                         unauthorized=int(unauth), p95_wait_days=float(np.percentile(wait, 95))))
        print(f"{policy:34s} {out.breached.sum():9d} {out.breached.mean():6.1%} {unauth:8d} "
              f"{np.percentile(wait, 95):9.0f}")

    joblib.dump({"sla": sla, "effort": effort, "version": SLA_VERSION}, HERE / "sla_model.joblib")
    with open(HERE / "sla_results.json", "w") as fh:
        json.dump({"auc": roc_auc_score(y, risk), "bands": summary.reset_index().to_dict("records"),
                   "replay": rows}, fh, indent=1, default=str)
    print(f"\nsaved sla_model.joblib ({SLA_VERSION}) and sla_results.json")


if __name__ == "__main__":
    main()
