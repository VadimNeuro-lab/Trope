"""The inference behind the paper's tables: paired tests, bootstrap CIs, Holm."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps

_BOOT_CHUNK = 1000


def _apply_rows(statistic: Callable[[np.ndarray], float], rows: np.ndarray) -> np.ndarray:
    """Row-wise statistic, vectorised when the callable understands `axis`."""
    try:
        return np.asarray(statistic(rows, axis=1), dtype=float)
    except TypeError:
        return np.apply_along_axis(statistic, 1, rows)


@dataclass(frozen=True, slots=True)
class WilcoxonResult:
    statistic: float
    pvalue: float
    n: int
    n_nonzero: int


def paired_wilcoxon(a, b, alternative: str = "two-sided") -> WilcoxonResult:
    """Wilcoxon signed-rank test on paired scores."""
    first = np.asarray(a, dtype=float).ravel()
    second = np.asarray(b, dtype=float).ravel()
    if first.shape != second.shape:
        raise ValueError(f"paired inputs must match: {first.shape} vs {second.shape}")
    n = first.size
    diff = first - second
    n_nonzero = int(np.count_nonzero(diff))
    if n_nonzero == 0:
        return WilcoxonResult(0.0, 1.0, n, 0)
    result = sps.wilcoxon(first, second, alternative=alternative)
    return WilcoxonResult(float(result.statistic), float(result.pvalue), n, n_nonzero)


def bootstrap_ci(
    values,
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_boot: int = 10_000,
    level: float = 0.95,
    rng: np.random.Generator | None = None,
) -> tuple[float, float, float]:
    """Percentile bootstrap interval, returned as (point estimate, lo, hi)."""
    sample = np.asarray(values, dtype=float).ravel()
    if sample.size < 2:
        raise ValueError("bootstrap needs at least 2 observations")
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must lie in (0, 1), got {level}")
    if rng is None:
        raise ValueError("bootstrap resampling needs an explicit np.random.Generator")

    draws = np.empty(n_boot, dtype=float)
    for lo_i in range(0, n_boot, _BOOT_CHUNK):
        idx = rng.integers(0, sample.size, size=(min(_BOOT_CHUNK, n_boot - lo_i), sample.size))
        draws[lo_i : lo_i + idx.shape[0]] = _apply_rows(statistic, sample[idx])
    tail = (1.0 - level) / 2.0
    lo, hi = np.percentile(draws, [100.0 * tail, 100.0 * (1.0 - tail)])
    return float(statistic(sample)), float(lo), float(hi)


def paired_bootstrap_diff(
    a,
    b,
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_boot: int = 10_000,
    level: float = 0.95,
    rng: np.random.Generator | None = None,
) -> tuple[float, float, float]:
    """Bootstrap interval for the paired difference; pairs resample together."""
    first = np.asarray(a, dtype=float).ravel()
    second = np.asarray(b, dtype=float).ravel()
    if first.shape != second.shape:
        raise ValueError(f"paired inputs must match: {first.shape} vs {second.shape}")
    return bootstrap_ci(first - second, statistic, n_boot, level, rng)


def spearman(a, b) -> float:
    """Spearman rank correlation, the reference-LM sensitivity number."""
    first = np.asarray(a, dtype=float).ravel()
    second = np.asarray(b, dtype=float).ravel()
    if first.shape != second.shape:
        raise ValueError(f"inputs must match: {first.shape} vs {second.shape}")
    return float(sps.spearmanr(first, second).statistic)


def holm_bonferroni(pvalues) -> np.ndarray:
    """Holm step-down adjusted p-values, in the order the inputs came in."""
    raw = np.asarray(pvalues, dtype=float).ravel()
    if raw.size == 0:
        return raw.copy()
    if np.any(raw < 0.0) or np.any(raw > 1.0):
        raise ValueError("p-values must lie in [0, 1]")
    order = np.argsort(raw, kind="stable")
    m = raw.size
    scaled = (m - np.arange(m)) * raw[order]
    adjusted = np.empty(m, dtype=float)
    adjusted[order] = np.minimum(np.maximum.accumulate(scaled), 1.0)
    return adjusted
