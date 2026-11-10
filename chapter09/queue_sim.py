"""Replay a dispute queue one business day at a time.

The team starts as many claims each business day as its capacity allows, in
the order a policy sets; each claim then takes its effort in business days to
decide. Capacity varies with leave, summer holidays, the Christmas weeks and
overtime (or other work) as the backlog moves away from its usual level.
Because every claim costs one start whatever its order, the backlog, and so
the capacity, is the same under every ordering policy: only who waits changes.

Used by make_triage_data.py (the historical first-in-first-out year) and by
sla_risk.py (the replay of November and December under four policies).
"""
import heapq
import zlib

import numpy as np
import pandas as pd

CLOCK_DAYS = 10            # business days from receipt to decision (Chapter 2)
DAILY_STARTS = 88          # nominal starts per business day: converts a queue into days
BASE_STARTS = 94           # staffed starts per business day before adjustments
TARGET_BACKLOG = 490       # the backlog the team usually carries
ADJUST = 0.12              # share of the gap to target closed each day (overtime / other work)


def as_day(ts):
    """Timestamps (Series, array or scalar) to numpy calendar days."""
    s = pd.to_datetime(pd.Series(ts))
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_localize(None)
    return s.to_numpy().astype("datetime64[D]")


def available_day(created):
    """Cases created after 17:00, or on a weekend, are first workable the next business day."""
    created = pd.to_datetime(pd.Series(created))
    late = (created.dt.hour >= 17).astype(int).to_numpy()
    return np.busday_offset(as_day(created), late, roll="forward")


def due_day(received):
    return np.busday_offset(as_day(received), CLOCK_DAYS, roll="backward")


def capacity(day, backlog):
    """Starts available on a business day, given the backlog waiting that morning."""
    day = pd.Timestamp(day)
    season = 1.0
    if day.month in (7, 8):
        season = 0.92                                   # summer holidays
    if (day.month == 12 and day.day >= 22) or (day.month == 1 and day.day <= 2):
        season = 0.88                                   # Christmas weeks
    noise = np.random.default_rng(zlib.crc32(str(day.date()).encode())).uniform(0.0, 0.08)
    return max(0, int(round(BASE_STARTS * season * (1 - noise) + ADJUST * (backlog - TARGET_BACKLOG))))


def run(avail, key, capacity_by_day=None, start=None, started=None):
    """Simulate the queue.

    avail            business day each claim becomes workable (datetime64[D])
    key              sort key per claim; lowest is started first
    capacity_by_day  dict day -> starts; if None, capacity() is used and logged
    start            first day simulated; claims already in `started` keep their start
    Returns (start day per claim, queue depth when each claim joined, capacity used).
    """
    avail = np.asarray(avail, dtype="datetime64[D]")
    key = np.asarray(key)
    n = len(avail)
    starts = np.full(n, np.datetime64("NaT"), dtype="datetime64[D]")
    depth = np.zeros(n, dtype=int)
    if started is not None:
        starts[:] = started
    todo = np.flatnonzero(np.isnat(starts))
    order = todo[np.lexsort((key[todo], avail[todo]))]
    day = np.busday_offset(start if start is not None else avail[order[0]], 0, roll="forward")
    heap, i, used = [], 0, {}
    while i < len(order) or heap:
        while i < len(order) and avail[order[i]] <= day:
            j = order[i]
            depth[j] = len(heap)
            heapq.heappush(heap, (key[j], j))
            i += 1
        cap = (capacity_by_day.get(day, BASE_STARTS) if capacity_by_day is not None
               else capacity(day, len(heap)))
        used[day] = cap
        for _ in range(min(cap, len(heap))):
            starts[heapq.heappop(heap)[1]] = day
        day = np.busday_offset(day, 1)
    return starts, depth, used


def decided_day(start, work_days):
    return np.busday_offset(start, np.asarray(work_days, dtype=int))
