"""Listing 7.1: chapter07/business_case.py

The lever logic of business_case.xlsx in plain Python, used as an independent
test of the workbook. Levers are applied in timeline order, each working on
the caseload the lever before it left. Defaults are the assumptions of
Table 7.3; the constants come from Table 1.2. All figures are illustrative.
"""

N0, COST_CASE, LOSS_CASE, AMOUNT = 720_000, 28.0, 61e6 / 720_000, 186.0


def run_levers(avoid=0.04, deflect=0.06, decide_share=0.62, decide_saving=9.0,
               contested=0.31, win_from=0.42, win_to=0.50, deflect_cost=10.0):
    out, n = {}, N0
    avoided = n * avoid                                   # Prevent: cases never raised
    out["Prevent"] = avoided * (COST_CASE + LOSS_CASE)
    n -= avoided
    resolved = n * deflect                                # Deflect: resolved informally
    out["Deflect"] = resolved * (COST_CASE - deflect_cost + LOSS_CASE)
    n -= resolved
    out["Decide"] = n * decide_share * decide_saving      # Decide: cheaper handling
    out["Recover"] = n * contested * (win_to - win_from) * AMOUNT
    return out


if __name__ == "__main__":
    benefits = run_levers()
    for lever, value in benefits.items():
        print(f"{lever:8s} ${value:,.0f}")
    print(f"Total    ${sum(benefits.values()):,.0f}")
