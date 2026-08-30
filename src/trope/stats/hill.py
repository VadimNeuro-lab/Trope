"""Hill tail-index estimator, its k-sensitivity plot and its asymptotic CI."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.special import ndtri


@dataclass(frozen=True, slots=True)
class HillResult:
    alpha: float
    k: int
    n_used: int
    n_dropped: int
    n_ties: int


def _positive(x) -> tuple[np.ndarray, int]:
    values = np.asarray(x, dtype=float).ravel()
    keep = np.isfinite(values) & (values > 0.0)
    return values[keep], int(values.size - keep.sum())


def default_k(n_used: int, exponent: float = 2.0 / 3.0) -> int:
    """k = floor(n ** 2/3), the paper's intermediate sequence, on the kept points."""
    return max(1, min(n_used - 1, int(math.floor(n_used**exponent))))


def hill_estimate(x, k: int | None = None) -> HillResult:
    """Hill estimate of the tail index from the k largest order statistics."""
    values, n_dropped = _positive(x)
    n_used = values.size
    if n_used < 3:
        raise ValueError(f"need at least 3 positive observations, got {n_used}")

    k = default_k(n_used) if k is None else int(k)
    if not 1 <= k <= n_used - 1:
        raise ValueError(f"k must lie in [1, {n_used - 1}], got {k}")

    ordered = np.sort(values)[::-1]
    threshold = ordered[k]
    h = float(np.mean(np.log(ordered[:k])) - math.log(threshold))
    n_ties = int(np.count_nonzero(values == threshold))
    alpha = math.inf if h <= 0.0 else 1.0 / h
    return HillResult(alpha=alpha, k=k, n_used=n_used, n_dropped=n_dropped, n_ties=n_ties)


def hill_plot(x, ks=None) -> tuple[np.ndarray, np.ndarray]:
    """alpha_hat as a function of k -- the sensitivity plot the paper promises."""
    values, _ = _positive(x)
    n_used = values.size
    if n_used < 3:
        raise ValueError(f"need at least 3 positive observations, got {n_used}")
    ks_array = (
        np.arange(1, n_used, dtype=int)
        if ks is None
        else np.asarray(ks, dtype=int).ravel()
    )
    if ks_array.size == 0 or ks_array.min() < 1 or ks_array.max() > n_used - 1:
        raise ValueError(f"every k must lie in [1, {n_used - 1}]")

    logs = np.log(np.sort(values)[::-1])
    running = np.cumsum(logs)
    h = running[ks_array - 1] / ks_array - logs[ks_array]
    with np.errstate(divide="ignore"):
        alpha = np.where(h > 0.0, 1.0 / h, np.inf)
    return ks_array, alpha


def hill_ci(x, k: int | None = None, level: float = 0.95) -> tuple[float, float]:
    """Asymptotic normal interval: sqrt(k)(alpha_hat - alpha)/alpha -> N(0, 1)."""
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must lie in (0, 1), got {level}")
    result = hill_estimate(x, k)
    if not math.isfinite(result.alpha):
        return math.inf, math.inf
    z = float(ndtri(0.5 + level / 2.0))
    half = z * result.alpha / math.sqrt(result.k)
    return result.alpha - half, result.alpha + half
