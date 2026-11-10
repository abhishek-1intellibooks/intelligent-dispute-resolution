"""Run fight_or_accept on the chapter's four cases (Table 10.8) and test the rules.

The first case is the $249 not-received claim that Chapter 9 routed to the
merchant disputes team: the merchant answered with a tracking number showing
delivery without a signature, answers about six chargebacks in ten and wins
about half of those it answers.
"""
import pandas as pd

from fight_or_accept import CONTEST_COST, TIME_LIMIT_DAYS, fight_or_accept

BASE = dict(network="visa", mcc_group="retail", liability_shift=False,
            ce3_eligible=False, merchant_tracking="none", merchant_responded=True,
            merchant_rep_rate=0.60, merchant_win_rate=0.50, days_to_file=18,
            evidence_completeness=0.70, first_party_score=0.10,
            prior_disputes_12m=0)

CASES = {
    "Worked example: not received, tracking, merchant answered":
        dict(BASE, reason="not_received", amount=249.00, merchant_tracking="tracking"),
    "Same claim, merchant silent and no tracking":
        dict(BASE, reason="not_received", amount=249.00, merchant_responded=False),
    "Card-not-present fraud with liability shift":
        dict(BASE, reason="fraud_cnp", amount=62.40, liability_shift=True),
    "Duplicate charge, travel merchant":
        dict(BASE, reason="duplicate", amount=1180.00, mcc_group="travel"),
}


def show(cases, decided):
    table = pd.DataFrame({
        "Amount": cases.amount.map("${:,.2f}".format),
        "p_win": decided.p_win.map("{:.3f}".format),
        "Expected value": decided.expected_value.map("${:,.2f}".format),
        "Threshold": decided.threshold.map("${:,.2f}".format),
        "Decision": decided.decision.str.capitalize(),
        "Reason": decided.reason,
    })
    print(table.to_string())


def main():
    cases = pd.DataFrame.from_dict(CASES, orient="index")
    decided = fight_or_accept(cases)
    print(f"Table 10.8: fight_or_accept on four cases (cost ${CONTEST_COST:.0f})")
    show(cases, decided)

    wx = cases.iloc[[0]]
    avg_ev = 0.42 * wx.amount.iloc[0] - CONTEST_COST
    print(f"\nWorked example: average-rate expected value ${avg_ev:,.2f}; "
          f"model expected value ${decided.expected_value.iloc[0]:,.2f}")
    fp = fight_or_accept(wx, attrition=0.05, value=600)
    print(f"First-party path (attrition 5% on a $600 relationship): expected value "
          f"${fp.expected_value.iloc[0]:,.2f}, decision {fp.decision.iloc[0]}")

    # The rules tested directly: time limit, review band and capacity
    print("\nRule checks")
    late = cases.iloc[[3]].assign(days_to_file=TIME_LIMIT_DAYS + 5)
    print("  duplicate filed late ->", fight_or_accept(late)[["decision", "reason"]]
          .iloc[0].to_dict())
    capped = fight_or_accept(cases, capacity=1)
    print("  capacity of one contest ->", capped.decision.to_dict())
    print("  model version:", decided.model_version.iloc[0])


if __name__ == "__main__":
    main()
