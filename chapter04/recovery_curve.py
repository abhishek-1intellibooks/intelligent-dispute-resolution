"""The recovery curve of Figure 4.3: share recoverable = 0.5 ** (t / h).

Prints the worked figures used in the chapter for a $64,000 payment under an
illustrative six-hour half-life.
"""


def recoverable_share(hours: float, half_life: float = 6.0) -> float:
    return 0.5 ** (hours / half_life)


if __name__ == "__main__":
    amount = 64_000.0
    for t in (0.5, 1, 4, 12, 24):
        share = recoverable_share(t)
        print(f"after {t:>4} h: {share:6.1%}  ${amount * share:>9,.0f}")
