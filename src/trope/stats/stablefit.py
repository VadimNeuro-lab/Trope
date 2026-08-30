"""Parameter estimation for the symmetric alpha-stable family."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import minimize

from trope.sampling.stable import (
    ALPHA_MAX,
    folded_stable_ppf,
    skew_stable_logpdf,
    stable_logpdf,
)

TABLE_ALPHA_MIN = 0.8
_TABLE_STEP = 0.05


@dataclass(frozen=True, slots=True)
class StableParams:
    alpha: float
    beta: float
    gamma: float
    delta: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.alpha, self.beta, self.gamma, self.delta


@lru_cache(maxsize=1)
def _quantile_table() -> tuple[np.ndarray, np.ndarray, CubicSpline]:
    """McCulloch's nu_alpha index, recomputed from our own quantile function."""
    alphas = np.round(np.arange(TABLE_ALPHA_MIN, ALPHA_MAX + 1e-9, _TABLE_STEP), 10)
    q95 = np.array([float(folded_stable_ppf(0.90, a)) for a in alphas])
    q75 = np.array([float(folded_stable_ppf(0.50, a)) for a in alphas])
    index = q95 / q75
    order = np.argsort(index)
    return index[order], alphas[order], CubicSpline(index[order], alphas[order])


def nu_alpha(alpha: float) -> float:
    """McCulloch's shape index (x_.95 - x_.05) / (x_.75 - x_.25) at this alpha."""
    return float(folded_stable_ppf(0.90, alpha) / folded_stable_ppf(0.50, alpha))


def nu_scale(alpha: float) -> float:
    """(x_.75 - x_.25) at unit scale; the divisor that turns the IQR into gamma."""
    return float(2.0 * folded_stable_ppf(0.50, alpha))


def _alpha_from_nu(observed: float) -> float:
    grid, alphas, spline = _quantile_table()
    if observed <= grid[0]:
        return float(alphas[0])
    if observed >= grid[-1]:
        return float(alphas[-1])
    return float(spline(observed))


def mccullough_fit(x) -> StableParams:
    """Quantile estimator for the symmetric family (McCulloch 1986, beta = 0)."""
    values = np.asarray(x, dtype=float).ravel()
    if values.size < 20:
        raise ValueError(f"quantile estimation needs at least 20 points, got {values.size}")
    q05, q25, q50, q75, q95 = np.percentile(values, [5.0, 25.0, 50.0, 75.0, 95.0])
    iqr = float(q75 - q25)
    if iqr <= 0.0:
        raise ValueError("interquartile range is zero; the sample is degenerate")
    alpha = _alpha_from_nu(float(q95 - q05) / iqr)
    return StableParams(alpha, 0.0, iqr / nu_scale(alpha), float(q50))


def fixed_alpha_fit(x, alpha: float) -> StableParams:
    """Scale and location by quantile matching with alpha held at the target."""
    values = np.asarray(x, dtype=float).ravel()
    q25, q50, q75 = np.percentile(values, [25.0, 50.0, 75.0])
    iqr = float(q75 - q25)
    if iqr <= 0.0:
        raise ValueError("interquartile range is zero; the sample is degenerate")
    return StableParams(float(alpha), 0.0, iqr / nu_scale(alpha), float(q50))


def stable_nll(x, params: StableParams) -> float:
    """Negative log-likelihood of a stable fit; inf where undefined."""
    if params.gamma <= 0.0:
        return math.inf
    if abs(params.beta) < 1e-12:
        logpdf = stable_logpdf(x, params.alpha, params.gamma, params.delta)
    else:
        logpdf = skew_stable_logpdf(
            x, params.alpha, params.beta, params.gamma, params.delta
        )
    total = float(np.sum(logpdf))
    return -total if math.isfinite(total) else math.inf


def mle_fit(
    x,
    x0: StableParams | None = None,
    bounds: tuple[tuple[float, float], ...] | None = None,
    *,
    maxiter: int = 600,
) -> StableParams:
    """Maximum likelihood over (alpha, gamma, delta) with beta held at zero."""
    values = np.asarray(x, dtype=float).ravel()
    if values.size < 10:
        raise ValueError(f"maximum likelihood needs at least 10 points, got {values.size}")
    start = x0 if x0 is not None else mccullough_fit(values)
    if bounds is None:
        spread = float(np.percentile(values, 75.0) - np.percentile(values, 25.0)) or 1.0
        bounds = (
            (TABLE_ALPHA_MIN, ALPHA_MAX),
            (1e-6 * spread, 1e6 * spread),
            (float(np.min(values)), float(np.max(values))),
        )

    def objective(theta: np.ndarray) -> float:
        alpha, gamma, delta = (float(v) for v in theta)
        return stable_nll(values, StableParams(alpha, 0.0, gamma, delta))

    theta0 = np.array(
        [
            min(max(start.alpha, bounds[0][0]), bounds[0][1]),
            min(max(start.gamma, bounds[1][0]), bounds[1][1]),
            min(max(start.delta, bounds[2][0]), bounds[2][1]),
        ]
    )
    result = minimize(
        objective,
        theta0,
        method="Nelder-Mead",
        bounds=bounds,
        options={"maxiter": maxiter, "xatol": 1e-4, "fatol": 1e-6},
    )
    alpha, gamma, delta = (float(v) for v in result.x)
    fitted = StableParams(alpha, 0.0, gamma, delta)
    return fitted if stable_nll(values, fitted) <= stable_nll(values, start) else start


def mle_fit_full(x, x0: StableParams | None = None, *, maxiter: int = 900) -> StableParams:
    """Maximum likelihood over all four parameters, beta included."""
    values = np.asarray(x, dtype=float).ravel()
    if values.size < 10:
        raise ValueError(f"maximum likelihood needs at least 10 points, got {values.size}")
    start = x0 if x0 is not None else mle_fit(values)
    spread = float(np.percentile(values, 75.0) - np.percentile(values, 25.0)) or 1.0
    bounds = (
        (TABLE_ALPHA_MIN, ALPHA_MAX),
        (-1.0, 1.0),
        (1e-6 * spread, 1e6 * spread),
        (float(np.min(values)), float(np.max(values))),
    )

    def objective(theta: np.ndarray) -> float:
        alpha, beta, gamma, delta = (float(v) for v in theta)
        if abs(alpha - 1.0) < 1e-6:
            return math.inf
        return stable_nll(values, StableParams(alpha, beta, gamma, delta))

    theta0 = np.array(
        [
            min(max(start.alpha, bounds[0][0]), bounds[0][1]),
            0.0,
            min(max(start.gamma, bounds[2][0]), bounds[2][1]),
            min(max(start.delta, bounds[3][0]), bounds[3][1]),
        ]
    )
    result = minimize(
        objective,
        theta0,
        method="Nelder-Mead",
        bounds=bounds,
        options={"maxiter": maxiter, "xatol": 1e-4, "fatol": 1e-6},
    )
    alpha, beta, gamma, delta = (float(v) for v in result.x)
    fitted = StableParams(alpha, beta, gamma, delta)
    return fitted if stable_nll(values, fitted) <= stable_nll(values, start) else start


def fixed_alpha_mle_fit(x, alpha: float, *, maxiter: int = 400) -> StableParams:
    """Maximum likelihood over (gamma, delta) with alpha held at the target."""
    values = np.asarray(x, dtype=float).ravel()
    if values.size < 10:
        raise ValueError(f"maximum likelihood needs at least 10 points, got {values.size}")
    start = fixed_alpha_fit(values, alpha)
    spread = float(np.percentile(values, 75.0) - np.percentile(values, 25.0)) or 1.0
    bounds = (
        (1e-6 * spread, 1e6 * spread),
        (float(np.min(values)), float(np.max(values))),
    )

    def objective(theta: np.ndarray) -> float:
        gamma, delta = (float(v) for v in theta)
        return stable_nll(values, StableParams(float(alpha), 0.0, gamma, delta))

    theta0 = np.array(
        [
            min(max(start.gamma, bounds[0][0]), bounds[0][1]),
            min(max(start.delta, bounds[1][0]), bounds[1][1]),
        ]
    )
    result = minimize(
        objective,
        theta0,
        method="Nelder-Mead",
        bounds=bounds,
        options={"maxiter": maxiter, "xatol": 1e-4, "fatol": 1e-6},
    )
    gamma, delta = (float(v) for v in result.x)
    fitted = StableParams(float(alpha), 0.0, gamma, delta)
    return fitted if stable_nll(values, fitted) <= stable_nll(values, start) else start


def gaussian_fit(x) -> StableParams:
    """The alpha = 2 submodel by its closed-form MLE, in stable coordinates."""
    values = np.asarray(x, dtype=float).ravel()
    if values.size < 2:
        raise ValueError("Gaussian fit needs at least 2 points")
    sd = float(np.std(values))
    if sd <= 0.0:
        raise ValueError("sample has zero variance")
    return StableParams(2.0, 0.0, sd / math.sqrt(2.0), float(np.mean(values)))
