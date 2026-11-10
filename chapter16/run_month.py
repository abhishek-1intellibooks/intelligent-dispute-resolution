"""The capstone: one synthetic month of 60,000 claims, platform vs manual (Listing 16.2).

run_month() is the listing. In the book, Platform and load_month come from a
dispute_platform package and compare from a reporting module; here they are
defined in this file so that the capstone is self-contained and does not import
the code of earlier chapters. Each component is represented by the rate, limit
or time that its chapter measured, taken as a named constant below with its
source; new assumptions are labelled as such (Table 16.5). Parameters can be
overridden in config/production-like.yaml.

Run:  python run_month.py      (writes claims_month.jsonl on first run)
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SEED = 16

# ---------------------------------------------------------------- parameters (Table 16.5)
CLAIMS_PER_MONTH = 60_000              # Ch. 5: the representative issuer's 720,000 claims a year / 12
FAMILY_MIX = {"unauthorized": 0.45, "merchant": 0.47, "processing": 0.08}     # assumption
FIRST_PARTY_REVIEW_RATE = 0.10         # Ch. 15: the first-party review flag sends 10% of claims to review
FIRST_PARTY_THRESHOLD = 0.21           # Ch. 15: score threshold of the live flag (Figure 15.2)
FIRST_PARTY_MINUTES = 12               # assumption: person-time per first-party review
# Ch. 13 (Table 13.6, policy gate): merchant-related claims finished by the agent,
# escalated because the outcome is adverse to the customer, and other escalations.
AGENT_FINISHED, AGENT_ADVERSE, AGENT_OTHER_ESCALATION = 0.713, 0.221, 0.065
# Ch. 13 (evaluation of 2,000 claims): what merchants did after the agent's inquiry.
MERCHANT_RESPONSE = {"refund": 570 / 2000, "evidence_sufficient": 498 / 2000,
                     "silent": 518 / 2000, "weak_or_none": 414 / 2000}
ISSUER_LIABILITY_SHARE = 0.35          # assumption: unauthorized claims absorbed automatically
AGENT_CHARGEBACK_LIMIT = 500.0         # Ch. 13: chargebacks above $500 need a person's approval
CONTEST_COST = 40.0                    # Ch. 10 model card: contest cost; smaller claims are credited
ESCALATION_MINUTES = 8                 # Ch. 13: person-time per escalation
LETTER_APPROVAL_MINUTES = 3            # Ch. 12: person-time to approve a checked draft
MANUAL_MINUTES_PER_CLAIM = 25          # Ch. 13 (illustrative): an analyst works a claim by hand
PLATFORM_COST_PER_CLAIM = 0.118        # Ch. 14 (Table 14.6): 11.8 cents a claim
ANALYST_COST_PER_HOUR = 45.0           # assumption
ANALYST_HOURS_PER_MONTH = 140          # assumption: productive hours per full-time analyst
MERCHANT_INQUIRY_WINDOW_DAYS = 5       # assumption: the agent's inquiry window (step in Figure 16.6)
AMOUNT_MEDIAN, AMOUNT_SIGMA = 95.0, 1.2  # assumption: claim amounts, lognormal
# Timing assumptions (calendar days) --------------------------------------------
PLATFORM_TIMES = dict(
    absorbed=(0.0, 0.3),                # credit made final on the day (uniform)
    declaration_mean=1.0,               # unauthorized: cardholder declaration returned (0.5 + exponential)
    clearing=(1.0, 3.0),                # processing errors: clearing data arrives (uniform)
    reply_median=1.3, reply_sigma=0.7,  # merchant reply time, lognormal, within the window
    refund_clearing=(0.5, 1.5),         # a promised refund appears in clearing (uniform)
    person_queue=(0.3, 1.5),            # an escalation waits for a person (uniform)
    review_queue=(0.5, 2.0),            # a first-party review waits for a person (uniform)
    after_lapse=(0.0, 1.0),             # silent merchant: chargeback filed at the next run after the window
)
MANUAL_TIMES = dict(
    first_touch_mean=3.5, first_touch_shape=3.0,      # queue before an analyst opens the claim (gamma)
    investigate=(3.5, 7.5),                            # unauthorized and processing work (uniform)
    merchant_window_days=10,                           # manual inquiries allow the merchant ten days
    reply_median=3.0, reply_sigma=0.6,
    noticed_mean=1.8,                                  # until someone notices the reply (exponential)
)
MANUAL_ACTIVITY_SHARE = {               # assumption: how the 25 manual minutes are spent (Figure 16.3)
    "Reading documents and assembling the case": 0.54,
    "Writing letters": 0.25,
    "Decisions on the outcome": 0.13,
    "Merchant correspondence": 0.08,
}
REASON_TEXT = {                         # Ch. 15, Listing 15.1
    "days_to_file": "The claim was made {value:.0f} days after the purchase",
    "prior_disputes_12m": "{value:.0f} other disputes were made in the last 12 months",
    "new_device": "The claim was made from a device not used before on the account",
}
FP_COEF = {"days_to_file": 0.055, "prior_disputes_12m": 1.0, "new_device": 1.1}   # assumption
FP_MEAN = {"days_to_file": 22.0, "prior_disputes_12m": 0.35, "new_device": 0.10}
FP_INTERCEPT = -4.47


# ---------------------------------------------------------------- the month's claims
def make_month(path: Path, n=CLAIMS_PER_MONTH, seed=SEED):
    """Write one synthetic month of claims, with the facts of the world each claim meets."""
    r = np.random.default_rng(seed)
    fams = list(FAMILY_MIX)
    family = r.choice(fams, n, p=list(FAMILY_MIX.values()))
    amount = np.round(np.exp(r.normal(math.log(AMOUNT_MEDIAN), AMOUNT_SIGMA, n)), 2)
    response = r.choice(list(MERCHANT_RESPONSE), n, p=list(MERCHANT_RESPONSE.values()))
    days_to_file = np.clip(np.round(r.gamma(2, 11, n)), 1, 120)
    prior = r.poisson(FP_MEAN["prior_disputes_12m"], n)
    new_device = (r.random(n) < FP_MEAN["new_device"]).astype(int)
    filed_day = np.sort(r.uniform(0, 30, n))
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for i in range(n):
            claim = {"claim_id": f"M-{i:05d}", "filed_day": round(float(filed_day[i]), 3),
                     "family": str(family[i]), "amount": float(amount[i]),
                     "days_to_file": int(days_to_file[i]), "prior_disputes_12m": int(prior[i]),
                     "new_device": int(new_device[i])}
            if family[i] == "merchant":
                claim["merchant_response"] = str(response[i])
            f.write(json.dumps(claim, separators=(",", ":")) + "\n")


def load_month(path):
    path = Path(path) if Path(path).is_absolute() else HERE / path
    if not path.exists():
        make_month(path)
    with path.open(encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


# ---------------------------------------------------------------- audit trail (Ch. 15, Listing 15.4)
GENESIS = "0" * 64


def _digest(prev, record):
    body = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + body).encode()).hexdigest()


class AuditTrail:
    def __init__(self, every=10_000):
        self.entries, self.checkpoints, self.every, self.prev = [], {}, every, GENESIS

    def append(self, record):
        h = _digest(self.prev, record)
        self.entries.append({"record": record, "prev": self.prev, "hash": h})
        self.prev = h
        if len(self.entries) % self.every == 0:
            self.checkpoints[len(self.entries)] = h
        return h

    def verify(self):
        """Return the position of the first broken record, or None."""
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e["prev"] != prev or _digest(prev, e["record"]) != e["hash"]:
                return i
            if self.checkpoints.get(i + 1) not in (None, e["hash"]):
                return i
            prev = e["hash"]
        return None


# ---------------------------------------------------------------- the platform
@dataclass
class Case:
    claim: dict
    case_id: str
    family: str = ""
    priority: str = "normal"
    flagged: bool = False
    fp_score: float = 0.0
    reasons: list = field(default_factory=list)
    clock_due_day: float = 0.0
    tasks: list = field(default_factory=list)       # (activity, minutes) done by people


class Platform:
    def __init__(self, params: dict, seed=SEED):
        self.p = params
        self.rng = np.random.default_rng(seed + 1)
        self.audit = AuditTrail()

    @classmethod
    def from_config(cls, config):
        params = {k: v for k, v in globals().items() if k.isupper()}
        path = Path(config) if Path(config).is_absolute() else HERE / config
        if path.exists():
            import yaml
            overrides = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            unknown = set(overrides) - set(params)
            if unknown:
                raise KeyError(f"unknown parameters in {path.name}: {sorted(unknown)}")
            params.update(overrides)
        return cls(params)

    # -- record and acknowledge (Ch. 8, 14)
    def intake(self, claim):
        case = Case(claim=claim, case_id=f"C-{claim['claim_id']}")
        self._log(case, "claim.received", "intake")
        return case

    # -- clocks as data (Ch. 2): ten business days, about fourteen calendar days
    def start_clocks(self, case):
        case.clock_due_day = case.claim["filed_day"] + 14
        self._log(case, "clock.started", "case", due_day=round(case.clock_due_day, 3))

    # -- family and priority (Ch. 9)
    def classify(self, case):
        case.family = case.claim["family"]
        case.priority = "high" if case.claim["amount"] > AGENT_CHARGEBACK_LIMIT else "normal"
        self._log(case, "claim.classified", "triage-1.0", family=case.family, priority=case.priority)

    # -- first-party review flag with reason codes (Ch. 6, 15)
    def first_party_flag(self, case):
        c = case.claim
        contrib = {f: FP_COEF[f] * (c[f] - FP_MEAN[f]) for f in FP_COEF}
        z = FP_INTERCEPT + sum(FP_COEF[f] * c[f] for f in FP_COEF)
        case.fp_score = 1 / (1 + math.exp(-z))
        case.flagged = case.fp_score >= self.p["FIRST_PARTY_THRESHOLD"]
        if case.flagged:
            ranked = sorted(contrib.items(), key=lambda kv: -kv[1])
            case.reasons = [REASON_TEXT[f].format(value=c[f]) for f, v in ranked[:3] if v >= 0.10]
        return case.flagged

    def queue_for_review(self, case, reasons=True):
        case.tasks.append(("First-party review", self.p["FIRST_PARTY_MINUTES"]))
        self._log(case, "case.queued_for_review", "first-party-flag-2.0",
                  score=round(case.fp_score, 3), reasons=case.reasons if reasons else [])

    # -- resolution along the family's path (Ch. 4, 10, 11, 12, 13)
    def resolve(self, case):
        p, r, t = self.p, self.rng, self.p["PLATFORM_TIMES"]
        c = case.claim
        if case.family == "unauthorized":
            if r.random() < p["ISSUER_LIABILITY_SHARE"]:
                ending, days = "credit final: issuer liability", r.uniform(*t["absorbed"])
            elif c["amount"] <= p["CONTEST_COST"]:
                ending, days = "credit final: too small to contest", r.uniform(*t["absorbed"])
            else:
                days = 0.5 + r.exponential(t["declaration_mean"])
                if c["amount"] > p["AGENT_CHARGEBACK_LIMIT"]:
                    ending = "person: chargeback over the agent's limit"
                    days += r.uniform(*t["person_queue"])
                else:
                    ending = "chargeback filed automatically"
        elif case.family == "processing":
            ending, days = "resolved from clearing data", r.uniform(*t["clearing"])
        else:                                                 # merchant-related: the agent (Ch. 13)
            resp = c["merchant_response"]
            reply = min(np.exp(r.normal(math.log(t["reply_median"]), t["reply_sigma"])),
                        p["MERCHANT_INQUIRY_WINDOW_DAYS"])
            if resp == "silent":
                reply = p["MERCHANT_INQUIRY_WINDOW_DAYS"] + r.uniform(*t["after_lapse"])
            p_adverse = p["AGENT_ADVERSE"] / p["MERCHANT_RESPONSE"]["evidence_sufficient"]
            other_left = p["AGENT_OTHER_ESCALATION"] - (p["MERCHANT_RESPONSE"]["evidence_sufficient"]
                                                        - p["AGENT_ADVERSE"])
            p_other = other_left / (1 - p["MERCHANT_RESPONSE"]["evidence_sufficient"])
            if resp == "evidence_sufficient":
                adverse = r.random() < p_adverse
                ending = "person: evidence favours the merchant" if adverse else "person: other escalation"
                days = reply + r.uniform(*t["person_queue"])
            elif r.random() < p_other:
                ending, days = "person: other escalation", reply + r.uniform(*t["person_queue"])
            elif resp == "refund":
                ending, days = "refund confirmed in clearing", reply + r.uniform(*t["refund_clearing"])
            else:
                ending, days = ("chargeback filed: merchant silent" if resp == "silent"
                                else "chargeback filed: weak evidence"), reply
        if ending.startswith("person"):
            case.tasks.append(("Decisions on escalated cases" if "merchant" in ending or "limit" in ending
                               else "Other escalations", p["ESCALATION_MINUTES"]))
        if case.flagged:
            days = max(days, r.uniform(*t["review_queue"]))
        if ending.startswith("person") or case.flagged:            # one letter, approved by a person
            case.tasks.append(("Approving letters", p["LETTER_APPROVAL_MINUTES"]))
        self._log(case, "case.resolved", "platform", ending=ending, days=round(float(days), 3))
        return {"ending": ending, "days": float(days)}

    def summary(self, case, ending):
        minutes = sum(m for _, m in case.tasks)
        return {"case_id": case.case_id, "family": case.family, "ending": ending["ending"],
                "days": ending["days"], "minutes": minutes, "flagged": case.flagged,
                "touched": bool(case.tasks), "tasks": case.tasks,
                "cost": minutes / 60 * self.p["ANALYST_COST_PER_HOUR"] + self.p["PLATFORM_COST_PER_CLAIM"]}

    def manual_estimate(self, case):
        """The same claim worked by hand: queue, investigation, merchant wait."""
        p, r, t = self.p, self.rng, self.p["MANUAL_TIMES"]
        days = r.gamma(t["first_touch_shape"], t["first_touch_mean"] / t["first_touch_shape"])
        if case.family == "merchant":
            if case.claim["merchant_response"] == "silent":
                days += t["merchant_window_days"]
            else:
                days += min(np.exp(r.normal(math.log(t["reply_median"]), t["reply_sigma"])),
                            t["merchant_window_days"])
            days += r.exponential(t["noticed_mean"])
        else:
            days += r.uniform(*t["investigate"])
        minutes = p["MANUAL_MINUTES_PER_CLAIM"]
        return {"case_id": case.case_id, "days": float(days), "minutes": minutes, "touched": True,
                "tasks": [(a, s * minutes) for a, s in p["MANUAL_ACTIVITY_SHARE"].items()],
                "cost": minutes / 60 * p["ANALYST_COST_PER_HOUR"]}

    def _log(self, case, decision, actor, **data):
        self.audit.append({"case_id": case.case_id, "decision": decision, "actor": actor, **data})


# ---------------------------------------------------------------- reporting
def compare(baseline, results):
    out = {}
    for name, rows in (("Manual baseline", baseline), ("Platform", results)):
        df = pd.DataFrame(rows)
        hours = df.minutes.sum() / 60
        out[name] = {
            "Analyst hours": f"{hours:,.0f}",
            f"Equivalent full-time analysts ({ANALYST_HOURS_PER_MONTH} hours a month)":
                f"{hours / ANALYST_HOURS_PER_MONTH:.1f}",
            "Analyst minutes per claim": f"{df.minutes.mean():.1f}",
            "Handling cost per claim, including platform": f"${df.cost.mean():.2f}",
            "Median days from claim to resolution or decision": f"{df.days.median():.1f}",
            "Slowest 10% of claims (days)": f"{df.days.quantile(0.9):.1f} or more",
            "Claims taking more than 14 calendar days": f"{(df.days > 14).mean():.1%}",
            "Claims touched by a person": f"{df.touched.mean():.1%}",
        }
    return pd.DataFrame(out)


def activity_table(baseline, results):
    rows = {}
    for name, data in (("Manual baseline", baseline), ("Platform", results)):
        c = Counter()
        for r in data:
            for activity, minutes in r["tasks"]:
                c[activity] += minutes
        rows[name] = {k: round(v / 60) for k, v in c.items()}
    return pd.DataFrame(rows).fillna(0).astype(int)


def run_month(path="claims_month.jsonl", config="config/production-like.yaml"):
    platform = Platform.from_config(config)          # services and settings, Ch. 14
    baseline, results = [], []
    for claim in load_month(path):                   # 60,000 synthetic claims
        case = platform.intake(claim)                # record and acknowledge, Ch. 8, 14
        platform.start_clocks(case)                  # Ch. 2
        platform.classify(case)                      # family, priority, Ch. 9
        if platform.first_party_flag(case):          # Ch. 6, 15
            platform.queue_for_review(case, reasons=True)
        ending = platform.resolve(case)              # rail (Ch. 4), recovery (Ch. 10),
                                                     # evidence (Ch. 11), letters (Ch. 12),
                                                     # agent (Ch. 13)
        results.append(platform.summary(case, ending))   # days, minutes, cost
        baseline.append(platform.manual_estimate(case))
    assert platform.audit.verify() is None           # the trail is intact, Ch. 15
    run_month.details = (platform, baseline, results)
    return compare(baseline, results)


def main():
    table = run_month()
    platform, baseline, results = run_month.details
    df = pd.DataFrame(results)
    n = len(df)
    by_person = df.ending.str.startswith("person")
    print(f"{n:,} claims; family mix {df.family.value_counts().to_dict()}")
    print(f"\nFigure 16.5: where the claims ended")
    print(df.ending.value_counts().to_string())
    print(f"\nFinished without a person: {(~by_person).sum():,} ({(~by_person).mean():.1%}); "
          f"reached a person: {by_person.sum():,}; flagged for first-party review: {df.flagged.sum():,} "
          f"({df.flagged.mean():.1%}); touched by a person in all: {df.touched.sum():,} ({df.touched.mean():.1%})")
    print(f"\nTable 16.6: one month, manual baseline against the platform (synthetic data)")
    print(table.to_string())
    print(f"\nFigure 16.3: analyst hours by activity")
    print(activity_table(baseline, results).to_string())
    print(f"\nAudit trail: {len(platform.audit.entries):,} records, hash chain verified intact "
          f"({len(platform.audit.checkpoints)} checkpoints)")
    days = pd.DataFrame({"manual": [b["days"] for b in baseline], "platform": df.days})
    bins = [0, 1, 2, 3, 4, 5, 6, 7, 10, 14, 21, 60]
    dist = days.apply(lambda s: pd.cut(s, bins, right=False).value_counts(normalize=True).sort_index())
    print("\nFigure 16.6: share of claims by days from claim to resolution or decision")
    print((dist * 100).round(1).to_string())
    summary = table.copy()
    summary.to_csv(HERE / "month_summary.csv")
    print("\nWrote month_summary.csv")


if __name__ == "__main__":
    main()
