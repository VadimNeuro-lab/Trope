"""lambda_hat_struct, Eq. (8): the divergence rate the PI controller tracks."""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypeVar

import numpy as np

from trope.types import EditRecord, Representation

T = TypeVar("T")

StepFn = Callable[[T, np.random.Generator], T]
DistanceFn = Callable[[T, T], float]
PerturbFn = Callable[[T, np.random.Generator], T]
_ALIAS = ("alt", "bis", "prime", "var")


@dataclass(frozen=True, slots=True)
class DivergenceResult:
    estimate: float
    ratios: tuple[float, ...]
    degenerate: int
    distances: tuple[float, ...]

    @property
    def steps(self) -> int:
        return len(self.distances) - 1


def perturb_single_name(
    rep: Representation, rng: np.random.Generator
) -> Representation:
    """Resample one entity's name, the paper's near-identical starting point."""
    if not rep.entities:
        return rep
    index = int(rng.integers(len(rep.entities)))
    target = rep.entities[index]
    base = target.sort or target.label or target.id
    alias = _ALIAS[int(rng.integers(len(_ALIAS)))]
    renamed = replace(target, sort=f"{base}_{alias}")
    entities = rep.entities[:index] + (renamed,) + rep.entities[index + 1 :]
    return rep.with_edit(
        EditRecord(
            operator="perturb_single_name",
            radicality=0.0,
            detail=f"{target.id}: {target.sort!r} -> {renamed.sort!r}",
        ),
        entities=entities,
    )


def estimate_divergence(
    rep0: T,
    step_fn: StepFn,
    distance_fn: DistanceFn,
    rng: np.random.Generator,
    *,
    steps: int = 16,
    epsilon: float = 1e-6,
    perturb_fn: PerturbFn = perturb_single_name,
) -> DivergenceResult:
    """Average per-step log-divergence rate of two branches from `rep0`."""
    if steps < 1:
        raise ValueError("need at least one probe step")
    if epsilon < 0.0:
        raise ValueError("eps_div must be non-negative")

    left: T = rep0
    right: T = perturb_fn(rep0, rng)
    distances = [float(distance_fn(left, right))]
    for _ in range(steps):
        a, b = rng.spawn(2)
        left = step_fn(left, a)
        right = step_fn(right, b)
        distances.append(float(distance_fn(left, right)))

    ratios: list[float] = []
    degenerate = 0
    for prev, cur in itertools.pairwise(distances):
        lo, hi = prev + epsilon, cur + epsilon
        if lo <= 0.0 or hi <= 0.0 or not math.isfinite(lo) or not math.isfinite(hi):
            degenerate += 1
            continue
        ratios.append(math.log(hi / lo))

    estimate = sum(ratios) / len(ratios) if ratios else 0.0
    return DivergenceResult(
        estimate=float(estimate),
        ratios=tuple(ratios),
        degenerate=degenerate,
        distances=tuple(distances),
    )
