"""Entropic optimal transport in the log domain."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial.distance import cdist

MARGINAL_TOL = 1e-6


@dataclass(frozen=True, slots=True)
class SinkhornResult:
    """Transport cost, plus how far the plan is from meeting its marginals."""

    cost: float
    marginal_error: float
    converged: bool


def sinkhorn_cost(
    a: np.ndarray,
    b: np.ndarray,
    C: np.ndarray,
    eps: float,
    n_iter: int,
    *,
    tol: float = MARGINAL_TOL,
    stages: int = 1,
    early_exit: bool = False,
) -> SinkhornResult:
    """Entropic OT between weights `a` and `b` under cost matrix `C`."""
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    C = np.asarray(C, dtype=np.float64)
    if C.shape != (a.size, b.size):
        raise ValueError(
            f"cost matrix {C.shape} does not match weights {a.size}x{b.size}"
        )
    if eps <= 0.0:
        raise ValueError("sinkhorn regularisation must be positive")
    if a.min() <= 0.0 or b.min() <= 0.0:
        raise ValueError("marginals must be strictly positive")
    if n_iter < 1:
        raise ValueError("need at least one Sinkhorn iteration")

    log_a, log_b = np.log(a), np.log(b)
    f = np.zeros(a.size)
    g = np.zeros(b.size)
    for stage in _eps_schedule(C, eps, stages):
        for _ in range(n_iter):
            f = stage * (log_a - _logsumexp((g[None, :] - C) / stage, axis=1))
            g = stage * (log_b - _logsumexp((f[:, None] - C) / stage, axis=0))
            if not early_exit:
                continue
            row = np.exp(_logsumexp((f[:, None] + g[None, :] - C) / stage, axis=1))
            if np.abs(row - a).max() <= tol:
                break

    plan = np.exp((f[:, None] + g[None, :] - C) / eps)
    error = float(np.abs(plan.sum(axis=1) - a).max())
    return SinkhornResult(
        cost=float((plan * C).sum()), marginal_error=error, converged=error <= tol
    )


def sinkhorn_divergence(
    X: np.ndarray,
    Y: np.ndarray,
    eps: float,
    n_iter: int,
    a: np.ndarray | None = None,
    b: np.ndarray | None = None,
    *,
    tol: float = MARGINAL_TOL,
    stages: int = 1,
    early_exit: bool = False,
) -> float:
    """``OT_eps(X,Y) - 0.5 OT_eps(X,X) - 0.5 OT_eps(Y,Y)``, clamped at zero."""
    X = _atleast_cloud(X)
    Y = _atleast_cloud(Y)
    a = _weights(a, X.shape[0])
    b = _weights(b, Y.shape[0])
    kw = {"tol": tol, "stages": stages, "early_exit": early_exit}
    xy = sinkhorn_cost(a, b, _sqcost(X, Y), eps, n_iter, **kw).cost
    xx = sinkhorn_cost(a, a, _sqcost(X, X), eps, n_iter, **kw).cost
    yy = sinkhorn_cost(b, b, _sqcost(Y, Y), eps, n_iter, **kw).cost
    return max(xy - 0.5 * xx - 0.5 * yy, 0.0)


def wasserstein2(
    X: np.ndarray,
    Y: np.ndarray,
    eps: float = 0.01,
    n_iter: int = 50,
    *,
    a: np.ndarray | None = None,
    b: np.ndarray | None = None,
    tol: float = MARGINAL_TOL,
    stages: int = 1,
    early_exit: bool = False,
) -> float:
    """Eq. (4): ``W_2`` between two point clouds, by Sinkhorn."""
    X = _atleast_cloud(X)
    Y = _atleast_cloud(Y)
    result = sinkhorn_cost(
        _weights(a, X.shape[0]),
        _weights(b, Y.shape[0]),
        _sqcost(X, Y),
        eps,
        n_iter,
        tol=tol,
        stages=stages,
        early_exit=early_exit,
    )
    return float(np.sqrt(max(result.cost, 0.0)))


def wasserstein2_exact_1d(x: np.ndarray, y: np.ndarray) -> float:
    """Closed-form W2 between two uniformly weighted samples on the line."""
    sx = np.sort(np.asarray(x, dtype=np.float64).ravel())
    sy = np.sort(np.asarray(y, dtype=np.float64).ravel())
    n, m = sx.size, sy.size
    if n == 0 or m == 0:
        raise ValueError("both samples must be non-empty")
    cx = np.arange(1, n + 1, dtype=np.float64) / n
    cy = np.arange(1, m + 1, dtype=np.float64) / m
    knots = np.union1d(cx, cy)
    widths = np.diff(np.concatenate(([0.0], knots)))
    ix = np.clip(np.searchsorted(cx, knots, side="left"), 0, n - 1)
    iy = np.clip(np.searchsorted(cy, knots, side="left"), 0, m - 1)
    return float(np.sqrt(np.sum(widths * (sx[ix] - sy[iy]) ** 2)))


def _logsumexp(M: np.ndarray, axis: int) -> np.ndarray:
    """logsumexp along one axis of a finite matrix."""
    peak = M.max(axis=axis, keepdims=True)
    return (peak + np.log(np.exp(M - peak).sum(axis=axis, keepdims=True))).squeeze(axis)


def _eps_schedule(C: np.ndarray, eps: float, stages: int) -> np.ndarray:
    """Geometric annealing from the cost scale down to the target epsilon."""
    if stages <= 1:
        return np.array([eps])
    hi = max(float(C.max()), eps)
    if hi <= eps:
        return np.array([eps])
    return np.geomspace(hi, eps, stages)


def _sqcost(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    return np.maximum(cdist(X, Y, metric="sqeuclidean"), 0.0)


def _atleast_cloud(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float64)
    if X.ndim == 1:
        X = X[:, None]
    if X.ndim != 2 or X.shape[0] == 0:
        raise ValueError(f"expected a non-empty (n, d) point cloud, got shape {X.shape}")
    return X


def _weights(w: np.ndarray | None, n: int) -> np.ndarray:
    if w is None:
        return np.full(n, 1.0 / n, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64).ravel()
    if w.size != n:
        raise ValueError(f"expected {n} weights, got {w.size}")
    total = w.sum()
    if total <= 0.0:
        raise ValueError("weights must sum to a positive number")
    return w / total
