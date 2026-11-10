"""Minute-by-minute simulation of a normal day and a peak day (Chapter 14).

Compares a synchronous monolith with an event-driven design at intake, then
simulates the drafting stage behind the queue under four worker policies
(Table 14.4), prices a claim (Table 14.6) and draws Figures 14.3 to 14.6.

All parameters are illustrative and set at the top of the file.
Run:  python peak_day.py            (writes figures/ and peak_day_results.csv)
"""
from __future__ import annotations

import heapq
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- parameters
SEED = 14
NORMAL_DAY_CLAIMS = 40_327
PEAK_DAY_CLAIMS = 159_803

# Intraday arrival shapes: a constant floor plus a late-morning and an evening
# bump (minutes after midnight). The peak day is sharper and later-morning heavy.
NORMAL_SHAPE = dict(floor=0.12, morning=675, morning_sd=135,
                    evening_weight=0.65, evening=1200, evening_sd=135)
PEAK_SHAPE = dict(floor=0.1387, morning=652.9, morning_sd=128.5,
                  evening_weight=0.8018, evening=1193.8, evening_sd=109.6)

# Intake designs
MONOLITH_SECONDS = 6.5        # validate + classify + first draft, in the request
MONOLITH_THREADS = 16
INTAKE_SECONDS = 0.040        # validate, write claim and event, reply
INTAKE_WORKERS = 160
APP_TIMEOUT_SECONDS = 30      # the mobile application gives up after this

# Drafting stage behind the queue
DRAFT_SECONDS = 6.0           # drafting work per claim
DRAFTS_PER_WORKER_MINUTE = 60 / DRAFT_SECONDS
TOKENS_PER_MINUTE = 1_000_000  # model provider limit
TOKENS_PER_CLAIM = 5_000       # -> 200 drafts a minute
AT_RISK_SHARE = 0.20           # claims Chapter 9 marks as at risk of missing a deadline
SLA_MINUTES = 15
FIXED_NORMAL_WORKERS = 14
FIXED_PEAK_WORKERS = 40
MIN_REPLICAS, MAX_REPLICAS, CAPPED_MAX_REPLICAS = 2, 40, 20
LAG_PER_REPLICA = 50           # KEDA lagThreshold (deploy/writer-scaledobject.yaml)
WORKER_START_MINUTES = 2
COOLDOWN_MINUTES = 5           # scale in slowly
RATE_TARGET_UTILIZATION = 0.9  # second trigger: claims arriving per minute / (10 x 0.9)

# Illustrative unit prices and per-claim usage (Table 14.6)
PRICE_INPUT_PER_M = 3.00
PRICE_OUTPUT_PER_M = 15.00
PRICE_PER_1000_PAGES = 1.50
PRICE_GB_MONTH = 0.023
PRICE_CPU_HOUR = 0.04
AGENT_STEPS, AGENT_IN, AGENT_OUT = 5.4, 3_000, 300
DRAFT_IN, DRAFT_OUT = 4_000, 1_000
STORAGE_MB, STORAGE_YEARS = 4, 7
PAGES_PER_CLAIM = 3.6
OBSERVABILITY_PER_CLAIM = 0.0040   # logs, metrics and traces (assumed)
CPU_SECONDS_PER_CLAIM = 45         # services and the small models of Ch. 9 and 10


# ---------------------------------------------------------------- arrivals
def arrival_rate(shape: dict, total: int) -> np.ndarray:
    t = np.arange(1440) + 0.5
    g = lambda mu, sd: np.exp(-0.5 * ((t - mu) / sd) ** 2)
    s = (shape["floor"] + g(shape["morning"], shape["morning_sd"])
         + shape["evening_weight"] * g(shape["evening"], shape["evening_sd"]))
    return total * s / s.sum()


def minute_counts(shape: dict, total: int, rng) -> np.ndarray:
    """Claims per minute: exactly `total` claims, spread as the shape says."""
    rate = arrival_rate(shape, total)
    return rng.multinomial(total, rate / rate.sum())


def arrival_seconds(counts: np.ndarray, rng) -> np.ndarray:
    minutes = np.repeat(np.arange(len(counts)), counts)
    return np.sort(minutes * 60 + rng.uniform(0, 60, len(minutes)))


# ---------------------------------------------------------------- intake
def fcfs_response_times(arrivals: np.ndarray, servers: int, mean_s: float, rng) -> np.ndarray:
    """Exact FCFS multi-server queue: response = wait + exponential service."""
    service = rng.exponential(mean_s, len(arrivals))
    free = [0.0] * servers
    heapq.heapify(free)
    out = np.empty(len(arrivals))
    for i, (a, s) in enumerate(zip(arrivals, service)):
        start = max(a, heapq.heappop(free))
        heapq.heappush(free, start + s)
        out[i] = start + s - a
    return out


def intake_summary(name, resp, arrivals):
    over = resp > APP_TIMEOUT_SECONDS
    behind = None
    if over.any():
        # first minute in which most claims waited past a minute
        mins = (arrivals // 60).astype(int)
        late = pd.Series(resp > 60).groupby(mins).mean()
        hit = late[late > 0.5]
        behind = int(hit.index[0]) if len(hit) else None
    return {
        "design": name,
        "mean_s": resp.mean(), "median_s": np.median(resp),
        "p99_s": np.percentile(resp, 99), "max_s": resp.max(),
        "over_timeout": int(over.sum()), "over_timeout_share": over.mean(),
        "falls_behind_at": f"{behind // 60:02d}:{behind % 60:02d}" if behind is not None else "-",
    }


# ---------------------------------------------------------------- drafting
@dataclass
class Policy:
    name: str
    min_workers: int
    max_workers: int
    autoscale: bool
    priority: bool


POLICIES = [
    Policy("Fixed, normal size", FIXED_NORMAL_WORKERS, FIXED_NORMAL_WORKERS, False, False),
    Policy("Fixed, peak size", FIXED_PEAK_WORKERS, FIXED_PEAK_WORKERS, False, False),
    Policy("Autoscaled", MIN_REPLICAS, MAX_REPLICAS, True, False),
    Policy("Autoscaled with priority", MIN_REPLICAS, MAX_REPLICAS, True, True),
    Policy("Autoscaled, capped at 20", MIN_REPLICAS, CAPPED_MAX_REPLICAS, True, False),
]


def simulate_drafting(counts: np.ndarray, at_risk: np.ndarray, policy: Policy):
    """Minute-level queue for the drafting stage.

    Each minute: arrivals join the queue; the autoscaler (if any) reads the lag
    and the arrival rate and starts or stops workers: the target is the larger
    of lag / 50 (the Kafka trigger of Listing 14.3) and arrivals per minute /
    (10 x 0.9) (a rate trigger, see deploy/writer-scaledobject-rate.yaml); new
    workers are ready after two minutes, and scale-in uses the largest target
    of the last five minutes. Then up to
    min(ready workers x 10, token budget / 5,000) claims are drafted, at-risk
    claims first when the priority lane is on. The day ends at midnight; the
    queue left then is drained afterwards (no new arrivals) to measure waits.
    """
    urgent, normal = deque(), deque()
    ready = policy.min_workers
    starting = deque()                 # (ready_at_minute, n)
    recent_targets = deque(maxlen=COOLDOWN_MINUTES)
    tokens = TOKENS_PER_MINUTE
    waits, risk_waits = [], []
    backlog, workers_series = [], []
    worker_minutes = 0
    idx = 0
    m = 0
    n_minutes = len(counts)
    while m < n_minutes or urgent or normal:
        arrived_last = counts[m] if m < n_minutes else 0
        if m < n_minutes:
            flags = at_risk[idx: idx + counts[m]]
            idx += counts[m]
            for f in flags:
                (urgent if (f and policy.priority) else normal).append((m, f))
        # workers that finished starting
        while starting and starting[0][0] <= m:
            ready += starting.popleft()[1]
        if policy.autoscale:
            lag = len(urgent) + len(normal)
            by_lag = math.ceil(lag / LAG_PER_REPLICA)
            by_rate = math.ceil(arrived_last / (DRAFTS_PER_WORKER_MINUTE * RATE_TARGET_UTILIZATION))
            desired = min(policy.max_workers, max(policy.min_workers, by_lag, by_rate))
            recent_targets.append(desired)
            target = max(recent_targets)
            total = ready + sum(n for _, n in starting)
            if target > total:
                starting.append((m + WORKER_START_MINUTES, target - total))
            elif target < total:
                surplus = total - target
                while surplus and starting:            # cancel pending starts first
                    r, n = starting.pop()
                    k = min(n, surplus)
                    surplus -= k
                    if n - k:
                        starting.append((r, n - k))
                ready -= surplus
        pods = ready + sum(n for _, n in starting)
        if m < n_minutes:
            worker_minutes += pods
        # token bucket refills continuously; at most one minute's worth held
        tokens = min(TOKENS_PER_MINUTE, tokens + TOKENS_PER_MINUTE)
        capacity = min(int(ready * DRAFTS_PER_WORKER_MINUTE), tokens // TOKENS_PER_CLAIM)
        served = 0
        while served < capacity and (urgent or normal):
            arrived, flag = (urgent or normal).popleft()
            w = m - arrived + DRAFT_SECONDS / 60      # minutes from claim to draft
            waits.append(w)
            if flag:
                risk_waits.append(w)
            served += 1
        tokens -= served * TOKENS_PER_CLAIM
        if m < n_minutes:
            backlog.append(len(urgent) + len(normal))
            workers_series.append(pods)
        if m == n_minutes - 1:
            at_midnight = len(urgent) + len(normal)
        m += 1
    waits, risk_waits = np.array(waits), np.array(risk_waits)
    return {
        "policy": policy.name,
        "workers": (f"{policy.min_workers}" if not policy.autoscale
                    else f"{policy.min_workers} to {policy.max_workers}"),
        "within_15": (waits <= SLA_MINUTES).mean(),
        "at_risk_within_15": (risk_waits <= SLA_MINUTES).mean(),
        "at_risk_within_1": (risk_waits <= 1).mean(),
        "p95_wait_min": np.percentile(waits, 95),
        "at_risk_p95_wait_min": np.percentile(risk_waits, 95),
        "largest_backlog": int(max(backlog)),
        "waiting_at_midnight": int(at_midnight),
        "worker_hours": worker_minutes / 60,
        "_backlog": np.array(backlog),
        "_workers": np.array(workers_series),
    }


# ---------------------------------------------------------------- latency vs load
def erlang_c(c: int, a: float) -> float:
    """Probability of waiting in an M/M/c queue with offered load a = lambda/mu."""
    term, s = 1.0, 1.0
    for k in range(1, c):
        term *= a / k
        s += term
    term *= a / c
    last = term * c / (c - a)
    return last / (s + last)


def mmc_p99(c: int, mean_s: float, rho: float) -> float:
    mu = 1 / mean_s
    lam = rho * c * mu
    C = erlang_c(c, lam / mu)
    theta = c * mu - lam

    def tail(x):
        if abs(theta - mu) < 1e-12:
            sw = math.exp(-mu * x) * (1 + mu * x)
        else:
            sw = (theta * math.exp(-mu * x) - mu * math.exp(-theta * x)) / (theta - mu)
        return (1 - C) * math.exp(-mu * x) + C * sw

    lo, hi = 0.0, 1.0
    while tail(hi) > 0.01:
        hi *= 2
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if tail(mid) > 0.01 else (lo, mid)
    return hi


# ---------------------------------------------------------------- cost
def cost_per_claim() -> pd.DataFrame:
    tok = lambda i, o: (i * PRICE_INPUT_PER_M + o * PRICE_OUTPUT_PER_M) / 1e6
    rows = [
        ("Agent (Ch. 13)", f"{AGENT_STEPS} steps of {AGENT_IN:,} input and {AGENT_OUT} output tokens",
         AGENT_STEPS * tok(AGENT_IN, AGENT_OUT)),
        ("Drafting (Ch. 12)", f"{DRAFT_IN:,} input and {DRAFT_OUT:,} output tokens", tok(DRAFT_IN, DRAFT_OUT)),
        ("Storage", f"{STORAGE_MB} MB of documents and records kept {STORAGE_YEARS} years",
         STORAGE_MB / 1000 * STORAGE_YEARS * 12 * PRICE_GB_MONTH),
        ("Document reading (Ch. 11)", f"{PAGES_PER_CLAIM} pages", PAGES_PER_CLAIM * PRICE_PER_1000_PAGES / 1000),
        ("Observability", "Logs, metrics and traces", OBSERVABILITY_PER_CLAIM),
        ("Compute", "Services and the models of Ch. 9 and 10", CPU_SECONDS_PER_CLAIM / 3600 * PRICE_CPU_HOUR),
    ]
    df = pd.DataFrame(rows, columns=["component", "assumption", "dollars"])
    df["cents"] = (df.dollars * 100).round(2)
    df["share"] = (df.dollars / df.dollars.sum()).round(3)
    return df


# ---------------------------------------------------------------- figures
def draw_figures(normal, peak, drafting_peak, cost, curves, outdir: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover
        print("matplotlib not installed; skipping figures")
        return
    outdir.mkdir(exist_ok=True)
    hours = np.arange(1440) / 60
    capacity = MONOLITH_THREADS * 60 / MONOLITH_SECONDS

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(hours, normal, lw=0.8, label=f"Normal day ({normal.sum():,} claims)")
    ax.plot(hours, peak, lw=0.8, label=f"Peak day ({peak.sum():,} claims)")
    ax.axhline(capacity, ls="--", c="k", lw=1, label=f"Monolith capacity ({capacity:.0f}/min)")
    ax.axhline(TOKENS_PER_MINUTE / TOKENS_PER_CLAIM, ls=":", c="r", lw=1, label="Token limit (200 drafts/min)")
    ax.set(xlabel="Hour of day", ylabel="Claims per minute", xlim=(0, 24), title="Figure 14.3: A normal day and a peak day")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(outdir / "fig14_3_arrivals.png", dpi=120); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4))
    for r in drafting_peak:
        style = {"Fixed, normal size": "-", "Fixed, peak size": "--", "Autoscaled": ":"}
        if r["policy"] in style:
            ax.plot(hours, r["_backlog"], ls=style[r["policy"]], lw=1.5, label=r["policy"])
    ax.set(xlabel="Hour of day", ylabel="Claims waiting to be drafted", xlim=(0, 24),
           title="Figure 14.4: The drafting backlog through the peak day")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(outdir / "fig14_4_backlog.png", dpi=120); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    c = cost.iloc[::-1]
    ax.barh(c.component, c.cents)
    for y, v in enumerate(c.cents):
        ax.text(v + 0.05, y, f"{v:.2f}¢", va="center", fontsize=8)
    ax.set(xlabel="Cents per claim", title=f"Figure 14.5: Cost per claim ({cost.cents.sum():.1f}¢)")
    fig.tight_layout(); fig.savefig(outdir / "fig14_5_cost.png", dpi=120); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    for name, (rhos, ratios) in curves.items():
        ax.plot(rhos * 100, ratios, label=name)
    ax.set(xlabel="Load, % of capacity", ylabel="Slowest 1% of replies, relative to idle", ylim=(0.9, 4),
           title="Figure 14.6: Latency against load")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(outdir / "fig14_6_latency.png", dpi=120); plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    rng = np.random.default_rng(SEED)
    normal = minute_counts(NORMAL_SHAPE, NORMAL_DAY_CLAIMS, rng)
    peak = minute_counts(PEAK_SHAPE, PEAK_DAY_CLAIMS, rng)
    print(f"Normal day: {normal.sum():,} claims, busiest minute {normal.max()}")
    print(f"Peak day:   {peak.sum():,} claims, busiest minute {peak.max()} "
          f"({peak.sum() / normal.sum():.2f}x the normal day)")

    # --- intake: synchronous monolith vs event-driven intake
    print(f"\nMonolith capacity: {MONOLITH_THREADS * 60 / MONOLITH_SECONDS:.0f} claims/min; "
          f"event-driven intake capacity: {INTAKE_WORKERS / INTAKE_SECONDS:,.0f} claims/s "
          f"({INTAKE_WORKERS / INTAKE_SECONDS * 60 / peak.max():.0f}x the peak day's busiest minute)")
    intake = []
    for day, counts in (("normal", normal), ("peak", peak)):
        arr = arrival_seconds(counts, rng)
        for name, servers, mean_s in (("monolith", MONOLITH_THREADS, MONOLITH_SECONDS),
                                      ("event-driven", INTAKE_WORKERS, INTAKE_SECONDS)):
            r = intake_summary(name, fcfs_response_times(arr, servers, mean_s, rng), arr)
            r["day"] = day
            intake.append(r)
    intake_df = pd.DataFrame(intake)[["day", "design", "mean_s", "median_s", "p99_s", "max_s",
                                      "over_timeout", "over_timeout_share", "falls_behind_at"]]
    with pd.option_context("display.float_format", "{:,.2f}".format, "display.width", 140):
        print("\nIntake: seconds from submission to reply")
        print(intake_df.to_string(index=False))

    # --- drafting behind the queue
    results = []
    for day, counts in (("peak", peak), ("normal", normal)):
        at_risk = rng.random(counts.sum()) < AT_RISK_SHARE
        for p in POLICIES:
            r = simulate_drafting(counts, at_risk, p)
            r["day"] = day
            results.append(r)
    table = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in results])
    peak_tbl = table[table.day == "peak"].set_index("policy").drop(columns="day")
    show = peak_tbl.copy()
    for col in ("within_15", "at_risk_within_15", "at_risk_within_1"):
        show[col] = (show[col] * 100).map("{:.1f}%".format)
    for col in ("p95_wait_min", "at_risk_p95_wait_min", "worker_hours"):
        show[col] = show[col].map("{:.0f}".format)
    print(f"\nTable 14.4: the drafting stage on the peak day ({peak.sum():,} claims)")
    print(show.T.to_string())
    normal_tbl = table[table.day == "normal"].set_index("policy")
    print("\nWorker-hours on the normal day:")
    print(normal_tbl.worker_hours.round(0).to_string())
    a = peak_tbl.loc["Autoscaled", "worker_hours"]; f = peak_tbl.loc["Fixed, peak size", "worker_hours"]
    print(f"Autoscaled / peak-sized pool worker-hours on the peak day: {a / f:.0%}")

    # --- latency against load (Figure 14.6)
    rhos = np.array([0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995])
    curves = {}
    print("\nFigure 14.6: p99 reply time relative to idle")
    for name, c, s in (("Monolith (16 x 6.5 s)", MONOLITH_THREADS, MONOLITH_SECONDS),
                       ("Event-driven intake (160 x 0.04 s)", INTAKE_WORKERS, INTAKE_SECONDS)):
        idle = mmc_p99(c, s, 1e-6)
        ratios = np.array([mmc_p99(c, s, r) / idle for r in rhos])
        curves[name] = (rhos, ratios)
        print(f"  {name:36s} idle p99 {idle:6.2f}s | " +
              " ".join(f"{int(r * 1000) / 10:g}%:{x:.2f}" for r, x in zip(rhos, ratios)))

    # --- cost per claim (Table 14.6)
    cost = cost_per_claim()
    print("\nTable 14.6: cost per claim (illustrative unit prices)")
    print(cost[["component", "assumption", "cents"]].to_string(index=False))
    total = cost.dollars.sum()
    tokens_share = cost.dollars.iloc[:2].sum() / total
    print(f"Total {total * 100:.1f} cents; language-model tokens {tokens_share:.0%}, agent alone "
          f"{cost.dollars.iloc[0] / total:.0%}")

    # --- outputs
    out = table.copy()
    out.to_csv(HERE / "peak_day_results.csv", index=False, float_format="%.4f")
    pd.DataFrame({"minute": np.arange(1440), "normal_day": normal, "peak_day": peak}).to_csv(
        HERE / "arrivals_by_minute.csv", index=False)
    draw_figures(normal, peak, [r for r in results if r["day"] == "peak"], cost, curves, HERE / "figures")
    print("\nWrote peak_day_results.csv, arrivals_by_minute.csv and figures/")


if __name__ == "__main__":
    main()
