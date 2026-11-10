"""Generate chapter05/ops_log.csv: a synthetic operations log of closed cases.

One row per closed dispute case with the five timestamps of Table 5.2
(claim_received_at, case_created_at, first_touch_at, decision_at, closed_at),
the intake channel and the disputed amount. The generator is seeded, so the
file is reproducible byte for byte.

How the timestamps are built (all illustrative):
  * Claims arrive over twelve weeks, at any hour of any day. The last three
    weeks carry a surge: more arrivals and heavier queue waits.
  * Intake lag: app claims become cases within about a minute; web claims
    within minutes; telephone and branch claims are keyed later, about 13-14
    hours on average.
  * Queue wait: gamma-distributed, heavier during the surge. Analysts work
    weekdays 08:00-18:00 only, so a first touch that would fall outside those
    hours moves to the next working morning.
  * Work elapsed and closing lag: right-skewed, also snapped to working hours.

    python make_ops_log.py
"""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "ops_log.csv"

SEED = 20260505
N_CASES = 5_000
START = datetime(2026, 1, 5)            # a Monday
WEEKS = 12
SURGE_WEEKS = 3                         # the final three weeks
SURGE_ARRIVAL_WEIGHT = 1.15             # relative daily volume during the surge
SURGE_QUEUE_FACTOR = 1.15              # queue waits are this much heavier

CHANNELS = {"app": 0.55, "web": 0.15, "phone": 0.20, "branch": 0.10}
INTAKE_HOURS = {"app": 0.02, "web": 0.35, "phone": 13.5, "branch": 13.8}   # mean lag

QUEUE_SHAPE, QUEUE_SCALE = 1.1, 3.273   # days, before snapping to working hours
WORK_MEDIAN, WORK_SIGMA = 1.3, 0.66     # days, lognormal
CLOSE_MEAN = 0.30                       # days, exponential
DAY_START, DAY_END = 8, 18              # analysts' working hours


def to_working_time(ts: datetime, rng) -> datetime:
    """Move a timestamp that falls outside weekday working hours to the next
    working morning, with a short random offset."""
    if ts.weekday() < 5 and DAY_START <= ts.hour < DAY_END:
        return ts
    day = ts.date() if ts.hour < DAY_START else ts.date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, DAY_START) + timedelta(minutes=float(rng.uniform(0, 150)))


def make_log(seed: int = SEED, n: int = N_CASES) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = WEEKS * 7
    surge_start = days - SURGE_WEEKS * 7
    weights = np.ones(days)
    weights[surge_start:] = SURGE_ARRIVAL_WEIGHT
    weekday = np.array([(START + timedelta(days=d)).weekday() for d in range(days)])
    weights[weekday >= 5] *= 0.7                       # fewer claims at weekends
    day_idx = rng.choice(days, size=n, p=weights / weights.sum())
    # arrival hour: mostly daytime and evening
    hours = np.clip(rng.normal(14.0, 4.5, size=n), 0, 23.99)

    channels = rng.choice(list(CHANNELS), size=n, p=list(CHANNELS.values()))
    amounts = np.round(rng.lognormal(np.log(112.8), 1.0, size=n), 2)

    rows = []
    for i in range(n):
        claim = START + timedelta(days=int(day_idx[i]), hours=float(hours[i]))
        claim = claim.replace(second=0, microsecond=0)
        ch = channels[i]
        mean_h = INTAKE_HOURS[ch]
        lag_h = rng.gamma(2.0, mean_h / 2.0) if ch in ("phone", "branch") else rng.exponential(mean_h)
        created = claim + timedelta(hours=float(lag_h))

        surge = day_idx[i] >= surge_start
        wait = rng.gamma(QUEUE_SHAPE, QUEUE_SCALE) * (SURGE_QUEUE_FACTOR if surge else 1.0)
        first_touch = to_working_time(created + timedelta(days=float(wait)), rng)

        work = rng.lognormal(np.log(WORK_MEDIAN), WORK_SIGMA)
        decision = to_working_time(first_touch + timedelta(days=float(work)), rng)

        close = rng.exponential(CLOSE_MEAN)
        closed = to_working_time(decision + timedelta(days=float(close)), rng)

        rows.append({
            "case_id": f"OPS-{i + 1:05d}",
            "channel": ch,
            "amount": amounts[i],
            "claim_received_at": claim,
            "case_created_at": created,
            "first_touch_at": first_touch,
            "decision_at": decision,
            "closed_at": closed,
        })

    log = pd.DataFrame(rows).sort_values("claim_received_at").reset_index(drop=True)
    log["case_id"] = [f"OPS-{i + 1:05d}" for i in range(len(log))]
    for col in ["claim_received_at", "case_created_at", "first_touch_at", "decision_at", "closed_at"]:
        log[col] = log[col].dt.floor("min")
    return log


def main():
    log = make_log()
    log.to_csv(OUT, index=False, date_format="%Y-%m-%d %H:%M")
    print(f"wrote {OUT.name}: {len(log):,} closed cases, "
          f"{log['claim_received_at'].min():%Y-%m-%d} to {log['claim_received_at'].max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
