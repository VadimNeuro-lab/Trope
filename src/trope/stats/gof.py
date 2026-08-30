"""Goodness of fit for the radicality distribution."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import chi2

from trope.sampling.stable import sample_stable, stable_cdf
from trope.stats.stablefit import (
    StableParams,
    fixed_alpha_fit,
    fixed_alpha_mle_fit,
    gaussian_fit,
    mccullough_fit,
    mle_fit,
    mle_fit_full,
    stable_nll,
)

MLE = "mle"
QUANTILE = "quantile"
NO_ESTIMATOR = "none"

BOUNDARY_NOTE = (
    "chi2(2) is not the correct asymptotic reference: alpha = 2 lies on the "
    "boundary of the stable parameter space and beta is unidentified there, so "
    "Wilks' theorem does not apply (Self & Liang 1987; Davies 1987). The true "
    "reference is a mixture, and chi2(2) under-rejects -- it is biased against "
    "the heavy-tail conclusion, not towards it. p_boot is the defensible number. "
    "Lambda itself is non-negative by construction: the Gaussian fit is a point "
    "of the stable family, so it bounds the stable supremum from above. The "
    "stable null is fitted with all four parameters free, so df = 2 is the "
    "nominal count the appendix gives; the boundary is the reason it is still "
    "the wrong reference."
)

ESTIMATOR_NOTE = (
    "The statistic is computed against the maximum-likelihood fit and the "
    "p-value from 10,000 resamples drawn from that fitted distribution, which "
    "is what the Statistical Methodology appendix specifies. The resamples are "
    "scored against the same fitted law rather than being refitted one by one, "
    "and that has a measured direction. The observed statistic is in the "
    "estimated-parameter case, where fitting pulls the CDF towards the sample "
    "and the statistic comes out small; a resample scored against a law it was "
    "not fitted to is in the fully-specified case, where it comes out larger. "
    "So p is biased UPWARD: at alpha = 1.6, n = 400, the printed procedure "
    "returns a mean p of 0.76 against 0.57 for the refitted null over the same "
    "eight samples. Upward means biased towards accepting heavy-tail "
    "consistency, which is the paper's own conclusion, so a large p_KS here is "
    "weaker evidence than it looks. This is the Lilliefors problem, and "
    "refit=True is the correction: it refits every resample before scoring it, "
    "with the McCulloch quantile estimator, because 10,000 simplex fits over "
    "numerically integrated stable densities take about ten hours where the "
    "quantile refit takes 156 s."
)

@dataclass(frozen=True, slots=True)
class KSResult:
    stat: float
    pvalue: float
    n_boot: int
    refit: bool
    params: StableParams
    point_estimator: str = MLE
    bootstrap_estimator: str = NO_ESTIMATOR


@dataclass(frozen=True, slots=True)
class LRResult:
    statistic: float
    p_chi2: float
    p_boot: float
    df: int
    note: str


def ks_statistic(x, cdf) -> float:
    """Two-sided KS distance between the sample and a fully specified CDF."""
    ordered = np.sort(np.asarray(x, dtype=float).ravel())
    n = ordered.size
    if n == 0:
        raise ValueError("empty sample")
    values = np.asarray(cdf(ordered), dtype=float)
    steps = np.arange(1, n + 1) / n
    return float(max(np.max(steps - values), np.max(values - (steps - 1.0 / n))))


def _fit_for(x, alpha: float | None, estimator: str) -> StableParams:
    if estimator == MLE:
        return mle_fit(x) if alpha is None else fixed_alpha_mle_fit(x, alpha)
    if estimator == QUANTILE:
        return mccullough_fit(x) if alpha is None else fixed_alpha_fit(x, alpha)
    raise ValueError(f"unknown stable estimator {estimator!r}; use {MLE!r} or {QUANTILE!r}")


def _cdf_of(params: StableParams):
    return lambda t: stable_cdf(t, params.alpha, params.gamma, params.delta)


def ks_test_stable(
    x,
    alpha: float | None = None,
    n_boot: int = 10_000,
    rng: np.random.Generator | None = None,
    refit: bool = False,
    point_fit: str = MLE,
) -> KSResult:
    """KS test against a fitted symmetric stable law, p-value by bootstrap."""
    values = np.asarray(x, dtype=float).ravel()
    params = _fit_for(values, alpha, point_fit)
    stat = ks_statistic(values, _cdf_of(params))
    if n_boot <= 0:
        return KSResult(stat, float("nan"), 0, refit, params, point_fit, NO_ESTIMATOR)
    if rng is None:
        raise ValueError("a bootstrap p-value needs an explicit np.random.Generator")

    bootstrap_fit = QUANTILE if refit else NO_ESTIMATOR
    n = values.size
    exceed = 0
    for _ in range(n_boot):
        sample = sample_stable(rng, params.alpha, 0.0, params.gamma, params.delta, size=n)
        null = _fit_for(sample, alpha, bootstrap_fit) if refit else params
        boot = ks_statistic(sample, _cdf_of(null))
        exceed += boot >= stat
    return KSResult(
        stat,
        (1.0 + exceed) / (1.0 + n_boot),
        int(n_boot),
        refit,
        params,
        point_fit,
        bootstrap_fit,
    )


def lr_gaussian_vs_stable(
    x, n_boot: int = 0, rng: np.random.Generator | None = None
) -> LRResult:
    """Likelihood ratio of the Gaussian submodel against the stable family."""
    values = np.asarray(x, dtype=float).ravel()
    statistic = _lr_statistic(values)
    p_chi2 = float(chi2.sf(statistic, 2))

    p_boot = float("nan")
    if n_boot > 0:
        if rng is None:
            raise ValueError("a bootstrap p-value needs an explicit np.random.Generator")
        null = gaussian_fit(values)
        sd = null.gamma * math.sqrt(2.0)
        exceed = 0
        for _ in range(n_boot):
            sample = rng.normal(null.delta, sd, size=values.size)
            exceed += _lr_statistic(sample) >= statistic
        p_boot = (1.0 + exceed) / (1.0 + n_boot)

    return LRResult(statistic, p_chi2, p_boot, 2, BOUNDARY_NOTE)


def _lr_statistic(x: np.ndarray) -> float:
    gauss = gaussian_fit(x)
    nll_gauss = stable_nll(x, gauss)
    nll_stable = min(stable_nll(x, mle_fit_full(x)), nll_gauss)
    statistic = 2.0 * (nll_gauss - nll_stable)
    if not math.isfinite(statistic):
        raise ValueError("neither the Gaussian nor the stable fit has a finite likelihood")
    return max(statistic, 0.0)
