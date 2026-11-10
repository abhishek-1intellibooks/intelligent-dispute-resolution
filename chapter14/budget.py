"""A shared token budget with a priority lane (Listing 14.4).

`TokenBudget` is the listing. Running the module shows the priority lane at
work: the bucket starts empty, 40 normal and 10 urgent drafting requests of
5,000 tokens arrive together, and urgent requests are served first.

Run:  python budget.py
"""
import asyncio
import time


class TokenBudget:
    """Share a provider's tokens-per-minute limit; urgent work goes first."""

    def __init__(self, tokens_per_minute):
        self.rate = tokens_per_minute / 60
        self.capacity = tokens_per_minute
        self.tokens = tokens_per_minute
        self.updated = time.monotonic()
        self.urgent_waiting = 0
        self.lock = asyncio.Lock()

    def _refill(self):
        now = time.monotonic()
        self.tokens = min(self.capacity,
                          self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    async def acquire(self, tokens, urgent=False):
        if urgent:
            self.urgent_waiting += 1
        try:
            while True:
                async with self.lock:
                    self._refill()
                    may_go = urgent or self.urgent_waiting == 0
                    if may_go and self.tokens >= tokens:
                        self.tokens -= tokens
                        return
                    short = max(tokens - self.tokens, 0)
                await asyncio.sleep(max(short / self.rate, 0.05))
        finally:
            if urgent:
                self.urgent_waiting -= 1


async def demo(tokens_per_minute=6_000_000, per_request=5_000, normal=40, urgent=10):
    """A fast-forward demonstration: 6M tokens a minute is 100,000 a second,
    so 50 requests of 5,000 tokens take about 2.5 seconds to admit."""
    budget = TokenBudget(tokens_per_minute)
    budget.tokens = 0                       # start with an empty bucket
    start = time.monotonic()
    order, waited = [], {"urgent": [], "normal": []}

    async def request(i, is_urgent):
        await budget.acquire(per_request, urgent=is_urgent)
        kind = "urgent" if is_urgent else "normal"
        order.append(kind)
        waited[kind].append(time.monotonic() - start)

    tasks = [request(i, False) for i in range(normal)] + [request(i, True) for i in range(urgent)]
    await asyncio.gather(*tasks)
    first_ten = order[:urgent]
    return order, waited, first_ten


def main():
    order, waited, first = asyncio.run(demo())
    mean = lambda xs: sum(xs) / len(xs)
    print(f"admitted {len(order)} requests; first {len(first)} admitted: "
          f"{first.count('urgent')} urgent, {first.count('normal')} normal")
    print(f"mean wait: urgent {mean(waited['urgent']):.2f}s, normal {mean(waited['normal']):.2f}s "
          f"(last request admitted at {max(waited['normal'] + waited['urgent']):.2f}s)")


if __name__ == "__main__":
    main()
