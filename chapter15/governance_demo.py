"""Chapter 15 results: fairness, reason codes, redaction, audit log, model card.

1. Generates 20,000 synthetic claims with an age band and a language preference,
   in which first-party misuse is equally common in every segment, and trains a
   first-party review flag in two versions: with two proxy features (narrative
   length, app tenure) and without them (Table 15.4, Figure 15.3).
2. Explains one flagged claim with reason codes (Listing 15.1, Figure 15.2).
3. Tests three redactors on 2,000 synthetic narratives (Table 15.7).
4. Writes 100,000 decision records to the hash-chained audit log, edits one,
   and verifies (Listing 15.4).
5. Checks model_card.yaml for the sections of Table 15.8.

Run:  python governance_demo.py
"""
from __future__ import annotations

import copy
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from audit import GENESIS, AuditLog, MemoryStore, WriteOnceCheckpoints, _digest, verify
from fairness import fairness_report
from reasons import contributions, reason_codes
from redact import luhn_ok, redact, redact_v1, redact_v2

HERE = Path(__file__).resolve().parent
SEED = 20
N_CLAIMS = 20_000
N_TEST = 8_079                     # the latest claims, held out
FLAG_SHARE = 0.10                  # share of claims sent to first-party review
MISUSE_RATE = 0.083                # equal in every segment, by construction
AGE_BANDS, AGE_P = ["18-34", "35-64", "65+"], [0.30, 0.50, 0.20]
LANGS, LANG_P = ["English", "Other"], [0.85, 0.15]
BASE_FEATURES = ["days_to_file", "prior_disputes_12m", "amount", "new_device"]
PROXIES = ["narrative_words", "app_tenure_months"]
# Generator strengths (log-scale shifts). Misuse shortens narratives and tenure;
# so do writing in another language and being 65 or over.
GEN = dict(prior_misuse=0.95, words_misuse=0.30, words_other_language=0.90, words_sd=0.36,
           tenure_misuse=0.40, tenure_65_plus=1.8, tenure_sd=0.48)


# ------------------------------------------------------------------ data
def make_claims(n=N_CLAIMS, seed=SEED) -> pd.DataFrame:
    """Misuse depends on nothing about the customer. Narrative length and app
    tenure depend on misuse AND on segment: second-language writers write
    shorter narratives, and older customers have used the app for less time."""
    r = np.random.default_rng(seed)
    age = r.choice(AGE_BANDS, n, p=AGE_P)
    lang = r.choice(LANGS, n, p=LANG_P)
    m = r.random(n) < MISUSE_RATE
    other, older = lang == "Other", age == "65+"
    df = pd.DataFrame({
        "claim_id": [f"FP-{i:05d}" for i in range(n)],
        "filed_on": pd.to_datetime("2025-01-01") + pd.to_timedelta(np.sort(r.integers(0, 365, n)), "D"),
        "age_band": age, "language": lang, "misuse": m,
    })
    p = GEN
    df["prior_disputes_12m"] = r.poisson(0.25 + p["prior_misuse"] * m)
    df["days_to_file"] = np.where(m, r.gamma(3, 15, n), r.gamma(2, 9, n)).round().clip(1, 120)
    df["amount"] = np.exp(r.normal(4.3 + 0.3 * m, 0.8)).round(2)
    df["new_device"] = (r.random(n) < 0.08 + 0.25 * m).astype(int)
    df["narrative_words"] = np.exp(r.normal(np.log(60) - p["words_misuse"] * m - p["words_other_language"] * other,
                                            p["words_sd"])).round().clip(3)
    df["app_tenure_months"] = np.exp(r.normal(np.log(30) - p["tenure_misuse"] * m - p["tenure_65_plus"] * older,
                                              p["tenure_sd"])).round(1)
    return df


def train_flag(train, features):
    scaler = StandardScaler().fit(train[features].to_numpy(float))
    model = LogisticRegression(max_iter=1000).fit(scaler.transform(train[features].to_numpy(float)),
                                                  train.misuse)
    return model, scaler


def score(model, scaler, df, features):
    return model.predict_proba(scaler.transform(df[features].to_numpy(float)))[:, 1]


# ------------------------------------------------------------------ narratives
OPENERS = ["I never received the order.", "The item arrived broken.", "I was charged twice.",
           "I cancelled this subscription in March.", "This is not a purchase I made.",
           "The merchant promised a refund that never came."]


def card_number(r: random.Random) -> str:
    kind = r.choice(["visa", "visa", "mc", "amex", "discover"])
    if kind == "visa":
        body, length = "4", 16
    elif kind == "mc":
        body, length = str(r.randint(51, 55)), 16
    elif kind == "amex":
        body, length = r.choice(["34", "37"]), 15
    else:
        body, length = "6011", 16
    while len(body) < length - 1:
        body += str(r.randint(0, 9))
    for check in "0123456789":
        if luhn_ok(body + check):
            return body + check


def formatted(digits: str, r: random.Random) -> str:
    sep = r.choice([" ", "-"])
    if len(digits) == 15:
        return sep.join([digits[:4], digits[4:10], digits[10:]])
    return sep.join(digits[i:i + 4] for i in range(0, len(digits), 4))


def make_narratives(n=2_000, seed=SEED):
    r = random.Random(seed)
    rows = []
    for i in range(n):
        parts, cards, orders = [r.choice(OPENERS)], [], []
        if r.random() < 0.30:
            o = "".join(str(r.randint(0, 9)) for _ in range(16))
            label = r.choice(["Order #", "order: ", "Order ", "invoice ", "Invoice #", "tracking: ",
                              "ref ", "Reference: "])
            parts.append(f"{label}{o} was placed online.")
            orders.append(o)
        if r.random() < 0.29:
            c = card_number(r)
            shown = c if r.random() < 0.535 else formatted(c, r)
            parts.append(r.choice([f"My card {shown} was charged.", f"It went on card {shown} last week.",
                                   f"The charge is on {shown}, please check."]))
            cards.append(shown)
        if r.random() < 0.15:
            parts.append(f"Email me at {r.choice(['sam', 'lee.k', 'pat_r'])}{r.randint(1, 99)}@example.com.")
        if r.random() < 0.15:
            parts.append(f"Call me on ({r.randint(200, 989)}) {r.randint(200, 989)}-{r.randint(1000, 9999)}.")
        rows.append({"narrative_id": i, "text": " ".join(parts), "cards": cards, "orders": orders})
    return rows


def redaction_table(rows):
    """A number counts as removed when the exact text the customer typed is gone."""
    out = []
    n_cards = sum(len(x["cards"]) for x in rows)
    n_orders = sum(len(x["orders"]) for x in rows)
    for version, fn, rule in ((1, redact_v1, "Any run of 12 to 19 digits"),
                              (2, redact_v2, "Digits with optional spaces or dashes, passing the card checksum"),
                              (3, redact, "As 2, plus a card-network prefix, and not labelled as an order or reference")):
        removed = destroyed = 0
        for x in rows:
            red = fn(x["text"])
            removed += sum(shown not in red for shown in x["cards"])
            destroyed += sum(shown not in red for shown in x["orders"])
        out.append({"version": version, "rule": rule,
                    "card_numbers_removed": f"{removed / n_cards:.1%} of {n_cards}",
                    "order_numbers_destroyed": f"{destroyed / n_orders:.1%} of {n_orders}"})
    return pd.DataFrame(out)


# ------------------------------------------------------------------ audit
def audit_demo(n=100_000, edit_at=42_017, seed=SEED):
    r = np.random.default_rng(seed)
    store, checkpoints = MemoryStore(), WriteOnceCheckpoints()
    log = AuditLog(store, checkpoints)
    scores = r.random(n).round(3)
    t0 = time.perf_counter()
    for i in range(n):
        log.append({"case_id": f"C-2025-{100000 + i}", "decision": "recovery.decided",
                    "actor": "model outcome-1.0", "versions": {"model": "outcome-1.0", "rules": "2025.10"},
                    "inputs_sha256": f"{i:064x}", "score": float(scores[i]),
                    "reasons": ["expected value"], "business_day": int(i % 10) + 1})
    write_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    clean = verify(store.entries, checkpoints)
    verify_s = time.perf_counter() - t0
    tampered = copy.deepcopy(store.entries)
    tampered[edit_at]["record"]["score"] = 0.999
    found = verify(tampered, checkpoints)
    # A forger with database access recomputes every hash after the edit.
    prev = tampered[edit_at - 1]["hash"] if edit_at else GENESIS
    for e in tampered[edit_at:]:
        e["prev"], e["hash"] = prev, _digest(prev, e["record"])
        prev = e["hash"]
    forged_without = verify(tampered)
    forged_with = verify(tampered, checkpoints)
    return {"records": n, "write_seconds": round(write_s, 2), "verify_seconds": round(verify_s, 2),
            "clean_chain": clean, "edited_record_found_at": found,
            "forged_chain_without_checkpoints": forged_without,
            "forged_chain_with_checkpoints": forged_with, "checkpoints": len(checkpoints)}


# ------------------------------------------------------------------ model card
CARD_SECTIONS = {
    "Identity": ["model", "version", "owner", "tier"],
    "Intended use and limits": ["intended_use", "not_for"],
    "Data": ["training_data", "calibration_data"],
    "Performance": ["test_results"],
    "Fairness": ["fairness"],
    "Limitations and monitoring": ["known_limitations", "monitoring"],
    "Approval and history": ["approved"],
}


def check_model_card(path=HERE / "model_card.yaml"):
    card = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = {s: [k for k in keys if not card.get(k)] for s, keys in CARD_SECTIONS.items()}
    return card, {s: m for s, m in missing.items() if m}


# ------------------------------------------------------------------ main
def main():
    df = make_claims()
    df.to_csv(HERE / "governance_claims.csv", index=False)
    train, test = df.iloc[:-N_TEST].copy(), df.iloc[-N_TEST:].copy()
    print(f"{len(df):,} synthetic claims; misuse rate {df.misuse.mean():.1%}; "
          f"by age band: {df.groupby('age_band').misuse.mean().round(3).to_dict()}; "
          f"by language: {df.groupby('language').misuse.mean().round(3).to_dict()}")

    versions = {"With proxy features": BASE_FEATURES + PROXIES, "Proxies removed": BASE_FEATURES}
    table, live = {}, None
    for name, feats in versions.items():
        model, scaler = train_flag(train, feats)
        s = score(model, scaler, test, feats)
        thr = float(np.quantile(s, 1 - FLAG_SHARE))
        t = test.assign(score=s, flag=s >= thr)
        by_age = fairness_report(t, "age_band", "35-64")
        by_lang = fairness_report(t, "language", "English")
        table[name] = {
            "Area under the ROC curve": f"{roc_auc_score(t.misuse, s):.3f}",
            "Share of misuse flagged": f"{t.loc[t.misuse, 'flag'].mean():.1%}",
            "Wrongly flagged, 35 to 64": f"{by_age.loc['35-64', 'wrongly_flagged']:.1%}",
            "Wrongly flagged, 65 and over": f"{by_age.loc['65+', 'wrongly_flagged']:.1%}",
            "Wrongly flagged, English": f"{by_lang.loc['English', 'wrongly_flagged']:.1%}",
            "Wrongly flagged, other language": f"{by_lang.loc['Other', 'wrongly_flagged']:.1%}",
            "Flag-rate ratio, 65 and over to 35 to 64": f"{by_age.loc['65+', 'flag_ratio']:.2f}",
            "Flag-rate ratio, other language to English": f"{by_lang.loc['Other', 'flag_ratio']:.2f}",
            "Wrong-flag ratio, 65 and over to 35 to 64": f"{by_age.loc['65+', 'error_ratio']:.2f}",
            "Wrong-flag ratio, other language to English": f"{by_lang.loc['Other', 'error_ratio']:.2f}",
            "Score threshold": f"{thr:.3f}",
        }
        if name == "Proxies removed":
            live = (model, scaler, feats, thr, t, by_age, by_lang)
    print(f"\nTable 15.4: the first-party review flag on {len(test):,} test claims "
          f"({FLAG_SHARE:.0%} flagged)")
    print(pd.DataFrame(table).to_string())

    model, scaler, feats, thr, t, by_age, by_lang = live
    report = pd.concat([by_age.assign(attribute="age_band"), by_lang.assign(attribute="language")])
    report.to_csv(HERE / "fairness_report.csv")
    print("\nFairness report for the live flag (proxies removed), fairness.py:")
    print(report.to_string())

    # Reason codes for one flagged claim (Figure 15.2)
    flagged = t[t.flag]
    # A claim like the book's: one earlier dispute, a known device, filed about 58 days after purchase.
    like = flagged[(flagged.prior_disputes_12m == 1) & (flagged.new_device == 0)]
    row = like.assign(d=(like.days_to_file - 58).abs()).sort_values(["d", "score"]).iloc[0]
    print(f"\nFigure 15.2: claim {row.claim_id}, filed {row.days_to_file:.0f} days after purchase, "
          f"{row.prior_disputes_12m} earlier dispute(s); score {row.score:.2f} against a threshold of {thr:.2f}")
    print("  contributions to the log-odds:", contributions(model, scaler, feats, row))
    for r in reason_codes(model, scaler, feats, row):
        print(f"  reason: {r['text']} (+{r['contribution']})")

    # Redaction (Table 15.7)
    rows = make_narratives()
    pd.DataFrame([{"narrative_id": x["narrative_id"], "text": x["text"]} for x in rows]).to_csv(
        HERE / "narratives.csv", index=False)
    print(f"\nTable 15.7: redacting card numbers from {len(rows):,} synthetic narratives")
    print(redaction_table(rows).to_string(index=False))
    emails = sum("[email]" in redact(x["text"]) for x in rows)
    phones = sum("[phone]" in redact(x["text"]) for x in rows)
    print(f"Version 3 also removed {emails} email addresses and {phones} telephone numbers.")
    example = "Order #4111111111111111 never came. My card 4111 1111 1111 1111 was charged; call 555-201-3344."
    print("  before:", example)
    print("  after: ", redact(example))

    # Audit log
    res = audit_demo()
    print(f"\nAudit log: {res['records']:,} records written in {res['write_seconds']}s, "
          f"verified in {res['verify_seconds']}s (clean chain -> {res['clean_chain']})")
    print(f"  record 42,017 edited (score -> 0.999): verification stops at {res['edited_record_found_at']:,}")
    print(f"  forger recomputes every later hash: without checkpoints -> {res['forged_chain_without_checkpoints']}; "
          f"with {res['checkpoints']} write-once checkpoints -> stops at {res['forged_chain_with_checkpoints']:,}")

    # Model card
    card, missing = check_model_card()
    print(f"\nModel card {card['model']} {card['version']} (tier {card['tier']}): "
          f"{'all sections of Table 15.8 present' if not missing else 'missing ' + str(missing)}; "
          f"approved: {card['approved']}")
    print("\nWrote governance_claims.csv, fairness_report.csv and narratives.csv")


if __name__ == "__main__":
    main()
