"""
Small exact statistics used by the analysis, with no third-party dependency.

  clopper_pearson(k, n)   exact two-sided confidence interval for a proportion
  fisher_exact(a, b, c, d) two-sided Fisher exact test for a 2 x 2 table
"""
from __future__ import annotations

from math import comb


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (Clopper-Pearson) confidence interval for k successes in n trials."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= k <= n:
        raise ValueError("k must be between 0 and n")

    def bisect(f, target):
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    # Upper: the p at which P(X <= k) falls to alpha/2. P(X <= k) decreases as p grows.
    upper = 1.0 if k == n else bisect(lambda p: _binom_cdf(k, n, p), alpha / 2)
    # Lower: the p at which P(X >= k) = 1 - P(X <= k-1) rises to alpha/2.
    lower = 0.0 if k == 0 else _lower(k, n, alpha)
    return lower, upper


def _lower(k: int, n: int, alpha: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 1 - _binom_cdf(k - 1, n, mid) < alpha / 2:  # still too unlikely to see k or more: raise p
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """
    Two-sided Fisher exact p-value for the table [[a, b], [c, d]]:
    the total probability of all tables with the same margins that are no more likely than the observed one.
    """
    row1, row2, col1 = a + b, c + d, a + c
    total = row1 + row2
    if total == 0:
        return 1.0

    def prob(x: int) -> float:
        return comb(row1, x) * comb(row2, col1 - x) / comb(total, col1)

    observed = prob(a)
    low, high = max(0, col1 - row2), min(row1, col1)
    p = sum(prob(x) for x in range(low, high + 1) if prob(x) <= observed * (1 + 1e-9))
    return min(1.0, p)