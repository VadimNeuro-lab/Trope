"""Symmetric alpha-stable sampling, densities and quantiles."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.special import gammaln, ndtr

ALPHA_MIN = 0.4
ALPHA_MAX = 2.0

_SPECIAL_TOL = 1e-12

_TINY = float(np.finfo(float).tiny)
_LOG_CUTOFF = 36.0
_PANELS_PER_CYCLE = 4
_GL_ORDER = 8
_SPLINE_NODES = 320
_MAX_TAIL_TERMS = 60


def _check_alpha(alpha: float) -> float:
    alpha = float(alpha)
    if not ALPHA_MIN <= alpha <= ALPHA_MAX:
        raise ValueError(f"alpha must lie in [{ALPHA_MIN}, {ALPHA_MAX}], got {alpha}")
    return alpha


def _check_scale(gamma: float) -> float:
    gamma = float(gamma)
    if not gamma > 0.0 or not math.isfinite(gamma):
        raise ValueError(f"gamma must be a finite positive scale, got {gamma}")
    return gamma


def _is_gaussian(alpha: float) -> bool:
    return abs(alpha - 2.0) <= _SPECIAL_TOL


def _is_cauchy(alpha: float) -> bool:
    return abs(alpha - 1.0) <= _SPECIAL_TOL


def _cms_standard(
    rng: np.random.Generator, alpha: float, beta: float, size
) -> np.ndarray | np.floating:
    """One standardised S1 (Samorodnitsky-Taqqu) draw per requested element."""
    v = rng.uniform(-math.pi / 2.0, math.pi / 2.0, size=size)
    w = rng.exponential(1.0, size=size)
    cos_v = np.maximum(np.cos(v), _TINY)
    w = np.maximum(w, _TINY)

    if _is_cauchy(alpha):
        half = math.pi / 2.0
        centre = np.maximum(half + beta * v, _TINY)
        return (2.0 / math.pi) * (
            centre * np.tan(v) - beta * np.log(half * w * cos_v / centre)
        )

    tan_half = math.tan(math.pi * alpha / 2.0)
    b = math.atan(beta * tan_half) / alpha
    s = (1.0 + (beta * tan_half) ** 2) ** (1.0 / (2.0 * alpha))
    arg = alpha * (v + b)
    sin_arg = np.sin(arg)
    cos_diff = np.maximum(np.cos(v - arg), _TINY)
    with np.errstate(divide="ignore"):
        log_mag = (
            math.log(s)
            + np.log(np.abs(sin_arg))
            - np.log(cos_v) / alpha
            + (1.0 - alpha) / alpha * (np.log(cos_diff) - np.log(w))
        )
    return np.sign(sin_arg) * np.exp(log_mag)


def _s1_to_s0(z, alpha: float, beta: float, gamma: float):
    """Shift the standardised S1 variable into Nolan's S0 parameterisation."""
    if beta == 0.0:
        return z
    if _is_cauchy(alpha):
        return z - beta * (2.0 / math.pi) * math.log(gamma)
    return z - beta * math.tan(math.pi * alpha / 2.0)


def sample_stable(
    rng: np.random.Generator,
    alpha: float,
    beta: float = 0.0,
    gamma: float = 1.0,
    delta: float = 0.0,
    size=None,
    parameterization: str = "S0",
) -> float | np.ndarray:
    """Draw from Stable(alpha, beta, gamma, delta) by Chambers-Mallows-Stuck."""
    alpha = _check_alpha(alpha)
    beta = float(beta)
    if not -1.0 <= beta <= 1.0:
        raise ValueError(f"beta must lie in [-1, 1], got {beta}")
    gamma = _check_scale(gamma)
    if parameterization not in ("S0", "S1"):
        raise ValueError(f"unknown parameterization {parameterization!r}")

    z = _cms_standard(rng, alpha, beta, size)
    if parameterization == "S0":
        z = _s1_to_s0(z, alpha, beta, gamma)
    x = gamma * z + float(delta)
    return float(x) if size is None else np.asarray(x)


def sample_radicality(
    rng: np.random.Generator, alpha: float, gamma: float, size=None
) -> float | np.ndarray:
    """rho = |Z| for Z ~ Stable_S0(alpha, 0, gamma, 0), the paper's radicality."""
    z = sample_stable(rng, alpha, 0.0, gamma, 0.0, size=size)
    return abs(z) if size is None else np.abs(z)


def _quadrature(alpha: float, u_max: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nodes, weights and exp(-t^alpha) for the inversion integral on [0, T]."""
    t_max = _LOG_CUTOFF ** (1.0 / alpha)
    cycles = u_max * t_max / (2.0 * math.pi)
    n_uniform = max(64, int(math.ceil(_PANELS_PER_CYCLE * cycles)))
    first = t_max / n_uniform
    graded = first * np.geomspace(1e-10, 1.0, 12)[:-1]
    edges = np.concatenate([[0.0], graded, np.linspace(first, t_max, n_uniform)])

    x, wl = np.polynomial.legendre.leggauss(_GL_ORDER)
    half = np.diff(edges) / 2.0
    mid = (edges[:-1] + edges[1:]) / 2.0
    t = (mid[:, None] + half[:, None] * x[None, :]).ravel()
    w = (half[:, None] * wl[None, :]).ravel()
    return t, w, np.exp(-(t**alpha))


def _cf_pdf(u: np.ndarray, alpha: float, grid=None) -> np.ndarray:
    """f(u) = (1/pi) int_0^inf exp(-t^alpha) cos(u t) dt, standard scale."""
    u = np.atleast_1d(np.asarray(u, dtype=float))
    t, w, decay = grid if grid is not None else _quadrature(alpha, float(np.max(np.abs(u))))
    coeff = w * decay
    out = np.empty(u.shape, dtype=float)
    for lo in range(0, u.size, 64):
        block = u[lo : lo + 64]
        out[lo : lo + 64] = np.cos(np.outer(block, t)) @ coeff
    return out / math.pi


def _cf_sf(u: np.ndarray, alpha: float, grid=None) -> np.ndarray:
    """P(X > u) for u >= 0, by inverting the characteristic function."""
    u = np.atleast_1d(np.asarray(u, dtype=float))
    t, w, decay = grid if grid is not None else _quadrature(alpha, float(np.max(np.abs(u))))
    coeff = w * decay / t
    out = np.empty(u.shape, dtype=float)
    for lo in range(0, u.size, 64):
        block = u[lo : lo + 64]
        out[lo : lo + 64] = np.sin(np.outer(block, t)) @ coeff
    return 0.5 - out / math.pi


def _tail_series(u: np.ndarray, alpha: float, sf: bool) -> np.ndarray:
    """Bergstrom expansion of the density (or upper tail) for large u > 0."""
    log_u = np.log(u)
    total = np.zeros_like(u)
    prev = math.inf
    for k in range(1, _MAX_TAIL_TERMS + 1):
        if sf:
            log_c = gammaln(alpha * k) - gammaln(k + 1.0)
            power = alpha * k
        else:
            log_c = gammaln(alpha * k + 1.0) - gammaln(k + 1.0)
            power = alpha * k + 1.0
        envelope = np.exp(log_c - power * log_u)
        total += math.sin(k * math.pi * alpha / 2.0) * (1.0 if k % 2 else -1.0) * envelope
        worst = float(np.max(envelope))
        if worst > prev:
            break
        prev = worst
        if worst <= 1e-15 * float(np.max(np.abs(total))):
            break
    return total / math.pi


@lru_cache(maxsize=256)
def _skew_grid(alpha: float, beta: float, u_max: float) -> tuple:
    """Quadrature nodes and the skewed integrand's phase, cached per (alpha, beta)."""
    t, w, decay = _quadrature(alpha, u_max)
    zeta = beta * math.tan(math.pi * alpha / 2.0) * (t - t**alpha)
    return t, w * decay, zeta


def skew_stable_logpdf(
    x, alpha: float, beta: float = 0.0, gamma: float = 1.0, delta: float = 0.0
) -> np.ndarray:
    """Log density of the S0 stable law with all four parameters free."""
    alpha = _check_alpha(alpha)
    gamma = _check_scale(gamma)
    if not -1.0 <= beta <= 1.0:
        raise ValueError(f"beta must lie in [-1, 1], got {beta}")
    u = (np.atleast_1d(np.asarray(x, dtype=float)) - float(delta)) / gamma
    if abs(beta) < 1e-12:
        return _std_logpdf(u, alpha).reshape(np.shape(u)) - math.log(gamma)
    if _is_cauchy(alpha):
        raise ValueError("alpha = 1 has no S0 skewed form here; the method never uses it")

    split = 25.0 if alpha >= 1.0 else 10.0
    t, coeff, zeta = _skew_grid(alpha, beta, max(float(np.max(np.abs(u))), split))
    out = np.empty(u.shape, dtype=float)
    for lo in range(0, u.size, 64):
        block = u[lo : lo + 64]
        out[lo : lo + 64] = np.cos(np.outer(block, t) + zeta[None, :]) @ coeff
    density = out / math.pi

    spoiled = ~np.isfinite(density) | (density <= 0.0)
    if spoiled.any():
        far = np.maximum(np.abs(u[spoiled]), 1.0)
        lead = (
            alpha
            * math.gamma(alpha)
            * math.sin(math.pi * alpha / 2.0)
            / math.pi
            * far ** (-alpha - 1.0)
            * (1.0 + np.sign(u[spoiled]) * beta)
        )
        density = density.copy()
        density[spoiled] = lead
    floor = np.finfo(float).tiny
    return np.log(np.maximum(density, floor)).reshape(np.shape(u)) - math.log(gamma)


@dataclass(frozen=True, slots=True)
class _Standard:
    """Cached density and tail of the standard symmetric stable law."""

    alpha: float
    u_split: float
    log_pdf: CubicSpline
    log_sf: CubicSpline


@lru_cache(maxsize=128)
def _standard(alpha: float) -> _Standard:
    u_split = 25.0 if alpha >= 1.0 else 10.0
    grid = _quadrature(alpha, u_split)
    v = np.linspace(0.0, math.asinh(u_split), _SPLINE_NODES)
    u = np.sinh(v)
    pdf = _cf_pdf(u, alpha, grid)
    sf = _cf_sf(u, alpha, grid)
    if not (np.all(pdf > 0.0) and np.all(sf > 0.0)):
        raise FloatingPointError(f"stable density quadrature lost precision at alpha={alpha}")
    return _Standard(alpha, u_split, CubicSpline(v, np.log(pdf)), CubicSpline(v, np.log(sf)))


def _std_logpdf(u: np.ndarray, alpha: float) -> np.ndarray:
    a = np.abs(u)
    if _is_gaussian(alpha):
        return -0.25 * a**2 - 0.5 * math.log(4.0 * math.pi)
    if _is_cauchy(alpha):
        return -math.log(math.pi) - np.log1p(a**2)
    std = _standard(alpha)
    out = np.empty(a.shape, dtype=float)
    near = a <= std.u_split
    if near.any():
        out[near] = std.log_pdf(np.arcsinh(a[near]))
    far = ~near
    if far.any():
        with np.errstate(divide="ignore"):
            out[far] = np.log(_tail_series(a[far], alpha, sf=False))
    return out


def _std_sf(u: np.ndarray, alpha: float) -> np.ndarray:
    """P(X > u) for u >= 0 under the standard symmetric stable law."""
    a = np.asarray(u, dtype=float)
    if _is_gaussian(alpha):
        return ndtr(-a / math.sqrt(2.0))
    if _is_cauchy(alpha):
        return 0.5 - np.arctan(a) / math.pi
    std = _standard(alpha)
    out = np.empty(a.shape, dtype=float)
    near = a <= std.u_split
    if near.any():
        out[near] = np.exp(std.log_sf(np.arcsinh(a[near])))
    far = ~near
    if far.any():
        out[far] = _tail_series(a[far], alpha, sf=True)
    return out


def stable_pdf(x, alpha: float, gamma: float = 1.0, delta: float = 0.0) -> np.ndarray:
    """Density of the symmetric stable law with scale gamma and location delta."""
    return np.exp(stable_logpdf(x, alpha, gamma, delta))


def stable_logpdf(x, alpha: float, gamma: float = 1.0, delta: float = 0.0) -> np.ndarray:
    """Log density; the fitting code works with this to keep the far tail finite."""
    alpha = _check_alpha(alpha)
    gamma = _check_scale(gamma)
    u = (np.asarray(x, dtype=float) - float(delta)) / gamma
    return _std_logpdf(np.atleast_1d(u), alpha).reshape(np.shape(u)) - math.log(gamma)


def stable_cdf(x, alpha: float, gamma: float = 1.0, delta: float = 0.0) -> np.ndarray:
    """CDF of the symmetric stable law, evaluated through the upper tail."""
    alpha = _check_alpha(alpha)
    gamma = _check_scale(gamma)
    u = (np.asarray(x, dtype=float) - float(delta)) / gamma
    tail = _std_sf(np.abs(np.atleast_1d(u)), alpha).reshape(np.shape(u))
    return np.where(u >= 0.0, 1.0 - tail, tail)


def folded_stable_cdf(x, alpha: float, gamma: float = 1.0) -> np.ndarray:
    """CDF of rho = |Z| for Z symmetric stable: 2 F(x) - 1 on x >= 0."""
    alpha = _check_alpha(alpha)
    gamma = _check_scale(gamma)
    a = np.asarray(x, dtype=float) / gamma
    out = 1.0 - 2.0 * _std_sf(np.abs(np.atleast_1d(a)), alpha).reshape(np.shape(a))
    return np.where(a <= 0.0, 0.0, np.clip(out, 0.0, 1.0))


def folded_stable_ppf(q, alpha: float, gamma: float = 1.0) -> np.ndarray:
    """Inverse of `folded_stable_cdf`, by bisection in asinh space."""
    alpha = _check_alpha(alpha)
    gamma = _check_scale(gamma)
    levels = np.asarray(q, dtype=float)
    shape = levels.shape
    q = np.atleast_1d(levels)
    if np.any(q < 0.0) or np.any(q > 1.0):
        raise ValueError("quantile levels must lie in [0, 1]")
    target = (1.0 - q) / 2.0

    hi = np.ones_like(q)
    for _ in range(400):
        over = _std_sf(hi, alpha) > target
        if not over.any():
            break
        hi = np.where(over, hi * 2.0, hi)

    lo_v = np.zeros_like(q)
    hi_v = np.arcsinh(hi)
    for _ in range(80):
        mid_v = 0.5 * (lo_v + hi_v)
        past = _std_sf(np.sinh(mid_v), alpha) < target
        hi_v = np.where(past, mid_v, hi_v)
        lo_v = np.where(past, lo_v, mid_v)
    out = gamma * np.sinh(0.5 * (lo_v + hi_v))
    out = np.where(q >= 1.0, np.inf, out)
    return out.reshape(shape)


def stable_ppf(q, alpha: float, gamma: float = 1.0, delta: float = 0.0) -> np.ndarray:
    """Quantile function of the symmetric stable law."""
    levels = np.asarray(q, dtype=float)
    upper = levels >= 0.5
    folded = np.where(upper, 2.0 * levels - 1.0, 1.0 - 2.0 * levels)
    mag = folded_stable_ppf(folded, alpha, gamma)
    return np.where(upper, mag, -mag) + float(delta)
