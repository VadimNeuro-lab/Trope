"""Calibration of the radicality distribution (paper, Section 2.5)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from trope.config import Config
from trope.data.base import Dataset
from trope.distance import StructuralDistance
from trope.operators.base import CROSSOVER, TOKEN, Operator, Resources, well_formed
from trope.rng import RngTree
from trope.sampling.rejection import RadicalitySampler
from trope.sampling.stable import sample_radicality
from trope.stats.gof import (
    ESTIMATOR_NOTE,
    MLE,
    NO_ESTIMATOR,
    ks_test_stable,
    lr_gaussian_vs_stable,
)
from trope.stats.hill import hill_ci, hill_estimate, hill_plot
from trope.types import Representation

PAPER_ALPHA_FIELD = "alpha_hat"

PAPER_ALPHA_NOTE = (
    "alpha_hat is the number the paper reports: Section 4.4 gives one tail "
    "index for d_struct (2.81 uncalibrated -> 1.62 calibrated, against "
    "alpha* = 1.60) and alpha_hat is that quantity. alpha_hat_radicality is an "
    "addition of this implementation and has no counterpart in the paper; read "
    "it as the diagnostic on what the rejection filter actually controls, not "
    "as the Section 4.4 figure."
)


@dataclass(slots=True)
class CalibrationReport:
    n_distances: int
    alpha_hat: float
    alpha_ci: tuple[float, float]
    alpha_target: float
    k: int
    ks_stat: float
    ks_pvalue: float
    ks_n_boot: int
    alpha_hat_radicality: float
    radicality_ci: tuple[float, float]
    n_radicality: int
    lr_statistic: float
    lr_p_chi2: float
    lr_p_boot: float | None
    ks_point_estimator: str = MLE
    ks_bootstrap_estimator: str = NO_ESTIMATOR
    ks_refit: bool = False
    paper_alpha_field: str = PAPER_ALPHA_FIELD
    rejection_filter: bool = False
    n_proposals: int = 0
    n_vacuous: int = 0
    acceptance_rate: float | None = None
    hill_plot_k: list[int] = field(default_factory=list)
    hill_plot_alpha: list[float | None] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_lines(self) -> list[str]:
        """One line per reported quantity, saying which one the paper prints."""
        lr_boot = (
            "n/a"
            if self.lr_p_boot is None or not np.isfinite(self.lr_p_boot)
            else f"{self.lr_p_boot:.3g}"
        )
        if self.rejection_filter:
            rate = "n/a" if self.acceptance_rate is None else f"{self.acceptance_rate:.3f}"
            filter_line = (
                f"filter      applied  acceptance_rate={rate} "
                f"proposals={self.n_proposals} vacuous={self.n_vacuous}"
            )
        else:
            filter_line = "filter      NOT applied: distances collected without rejection"
        return [
            f"d_struct    alpha_hat={self.alpha_hat:.3f} "
            f"CI=[{self.alpha_ci[0]:.3f},{self.alpha_ci[1]:.3f}] k={self.k} "
            f"n={self.n_distances}  target={self.alpha_target}"
            "   <- the paper's Section 4.4 number",
            f"radicality  alpha_hat={self.alpha_hat_radicality:.3f} "
            f"CI=[{self.radicality_ci[0]:.3f},{self.radicality_ci[1]:.3f}] "
            f"n={self.n_radicality}"
            "   <- this implementation only, not in the paper (entry 3c)",
            f"KS          stat={self.ks_stat:.4f} p={self.ks_pvalue:.3f} "
            f"n_boot={self.ks_n_boot} point={self.ks_point_estimator} "
            f"bootstrap={self.ks_bootstrap_estimator} refit={self.ks_refit}",
            f"LR          Lambda={self.lr_statistic:.3f} p_chi2={self.lr_p_chi2:.3g} "
            f"p_boot={lr_boot} "
            "(chi2(2) is the paper's reference and is conservative at the boundary)",
            filter_line,
        ]

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_finite(self.to_dict()), indent=2, allow_nan=False),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> CalibrationReport:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for key in ("alpha_ci", "radicality_ci"):
            data[key] = tuple(data[key])
        return cls(**data)


def _finite(value: Any) -> Any:
    """Replace NaN and +/-inf with None, recursively."""
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_finite(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


class _Proposal:
    """One operator applied at a radicality, and the displacement it realises."""

    __slots__ = ("distance", "edit", "op", "other", "rep", "resources", "rng", "tag", "tries")

    def __init__(self, op, rep, other, resources, distance, rng, tag) -> None:
        self.op = op
        self.rep = rep
        self.other = other
        self.resources = resources
        self.distance = distance
        self.rng = rng
        self.tag = tag
        self.tries = 0
        self.edit: Any = None

    def __call__(self, rho: float) -> float:
        stream = self.rng.stream(f"calibration/op/{self.tag}/{self.tries}")
        self.tries += 1
        self.edit = self.op.apply(
            self.rep, rho, stream, self.resources, other=self.other
        )
        if not self.edit.changed or self.edit.representation is None:
            return 0.0
        if not well_formed(self.edit.representation)[0]:
            return 0.0
        return float(self.distance(self.rep, self.edit.representation))


def collect_distances(
    representations: Sequence[Representation],
    operators: Sequence[Operator],
    distance: StructuralDistance,
    resources: Resources,
    rng: RngTree,
    *,
    n: int = 1000,
    alpha: float = 1.6,
    gamma: float = 0.3,
    sampler: RadicalitySampler | None = None,
    max_attempts: int | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """Structural distances d_struct(R, o(R)) across operators and problems."""
    structural = [op for op in operators if op.kind != TOKEN]
    if not structural or not representations:
        raise ValueError("need structural operators and at least one representation")

    values: list[float] = []
    draws: list[float] = []
    counts = {"attempts": 0, "noop": 0, "malformed": 0, "zero": 0,
              "rejections": 0, "vacuous": 0, "filtered": int(sampler is not None)}
    max_attempts = max_attempts or 20 * n
    stream = rng.stream("calibration/rho")

    while len(values) < n and counts["attempts"] < max_attempts:
        counts["attempts"] += 1
        t = counts["attempts"]
        pick = rng.stream(f"calibration/pick/{t}")
        rep = representations[int(pick.integers(len(representations)))]
        op = structural[int(pick.integers(len(structural)))]
        other = None
        if op.kind == CROSSOVER:
            other = representations[int(pick.integers(len(representations)))]
        proposal = _Proposal(op, rep, other, resources, distance, rng, str(t))
        if sampler is None:
            rho = float(sample_radicality(stream, alpha, gamma))
            d = proposal(rho)
        else:
            draw = sampler.draw(stream, proposal)
            rho = float(draw.rho)
            d = float(draw.distance)
            counts["rejections"] += draw.rejections
            counts["vacuous"] += int(draw.vacuous)
        draws.append(rho)
        edit = proposal.edit
        if not edit.changed or edit.representation is None:
            counts["noop"] += 1
            continue
        if not well_formed(edit.representation)[0]:
            counts["malformed"] += 1
            continue
        if d <= 0.0:
            counts["zero"] += 1
            continue
        values.append(d)

    return (
        np.asarray(values, dtype=np.float64),
        np.asarray(draws, dtype=np.float64),
        counts,
    )


def _filter_stats(collection: Mapping[str, int] | None) -> tuple[bool, int, int, float | None]:
    """Whether the rejection filter ran during collection, and how often it accepted."""
    if not collection or not collection.get("filtered"):
        return False, 0, 0, None
    accepted = int(collection.get("attempts", 0))
    proposals = accepted + int(collection.get("rejections", 0))
    vacuous = int(collection.get("vacuous", 0))
    rate = accepted / proposals if proposals else None
    return True, proposals, vacuous, rate


def _filter_note(
    filtered: bool, proposals: int, vacuous: int, rate: float | None
) -> str:
    if not filtered:
        return (
            "The rejection filter was NOT applied during collection: the "
            "radicality was drawn straight from Stable(alpha*, 0, gamma, 0) with "
            "no acceptance test, so acceptance_rate is null and these distances "
            "are the uncalibrated ones. Pass a RadicalitySampler to "
            "collect_distances for the calibrated pass."
        )
    return (
        f"The rejection filter was applied during collection: {proposals} "
        f"proposals, acceptance_rate="
        f"{'n/a' if rate is None else format(rate, '.4f')}, {vacuous} draws "
        "taken on a vacuous condition. A window that no value of rho could "
        "have carried past the KS test constrains nothing, so the first draw "
        "is taken and counts as an acceptance: read the rate next to "
        "n_vacuous, since a sampler whose window has drifted out of reach "
        "reports a high rate as well."
    )


def calibrate(
    distances: np.ndarray,
    cfg: Config,
    rng: np.random.Generator,
    *,
    radicality: np.ndarray | None = None,
    n_boot: int | None = None,
    collection: Mapping[str, int] | None = None,
) -> CalibrationReport:
    x = np.asarray(distances, dtype=np.float64)
    if x.size < 32:
        raise ValueError(f"need at least 32 distances to calibrate, got {x.size}")

    hill = hill_estimate(x)
    lo, hi = hill_ci(x, hill.k)
    grid_k, grid_alpha = hill_plot(x)

    rho = np.asarray(radicality if radicality is not None else [], dtype=np.float64)
    if rho.size >= 32:
        rho_hill = hill_estimate(rho)
        rho_lo, rho_hi = hill_ci(rho, rho_hill.k)
        rho_alpha, rho_n = float(rho_hill.alpha), int(rho.size)
    else:
        rho_lo = rho_hi = rho_alpha = float("nan")
        rho_n = int(rho.size)
    ks = ks_test_stable(
        x, n_boot=n_boot if n_boot is not None else cfg.sampling.ks_bootstrap, rng=rng
    )
    lr = lr_gaussian_vs_stable(x, rng=rng)

    filtered, proposals, vacuous, rate = _filter_stats(collection)

    notes = [
        PAPER_ALPHA_NOTE,
        "In-sample on the acceptance criterion: the rejection filter drives the "
        "empirical radicality distribution toward the target, so these statistics "
        "are implementation sanity checks, not evidence of intrinsic alpha-stability.",
        "The Hill estimator is biased upward on stable data -- the stable tail "
        "is only asymptotically Pareto -- and the bias is large at calibration "
        "sample sizes. On draws from the target law itself it reads about 2.1 at "
        "n=1000 and about 1.7 at n=50000 against alpha*=1.6 "
        "(tests/test_stats.py pins this). Read alpha_hat against that scale and "
        "against the k-sensitivity plot, not against alpha* directly.",
        "alpha_hat is the tail index of the realised structural distances; "
        "alpha_hat_radicality is that of the sampled radicality rho = |Z|. The "
        "two are different objects and only the second is alpha-stable by "
        "construction. d_struct is a Wasserstein distance between empirical "
        "measures on a feature space of bounded diameter, so its support is "
        "bounded and no Pareto tail index is identifiable from it: expect a "
        "large alpha_hat here regardless of alpha*. What the rejection filter "
        "controls is the radicality, and that is where the target applies.",
        f"KS p-value from a parametric bootstrap with {ks.n_boot} resamples, "
        f"refit={ks.refit}, point fit by {ks.point_estimator}, bootstrap refits by "
        f"{ks.bootstrap_estimator}. " + ESTIMATOR_NOTE,
        "The likelihood-ratio reference chi2(2) is the paper's; alpha=2 sits on the "
        "boundary of the stable parameter space and beta is unidentified there, so "
        "Wilks' theorem does not apply and chi2(2) under-rejects. That direction is "
        "against the paper's own heavy-tail claim rather than in favour of it. "
        "lr_p_boot is the defensible alternative. lr_statistic is non-negative by "
        "construction: the Gaussian fit is a point of the stable family at alpha=2, "
        "so it bounds the stable supremum and Lambda cannot go below zero even when "
        "the maximum-likelihood simplex stops short of that boundary.",
        _filter_note(filtered, proposals, vacuous, rate),
    ]
    if hill.n_dropped:
        notes.append(f"{hill.n_dropped} non-positive distances dropped before the Hill fit.")
    if hill.n_ties:
        notes.append(f"{hill.n_ties} ties at the Hill threshold order statistic.")

    return CalibrationReport(
        n_distances=int(x.size),
        alpha_hat=float(hill.alpha),
        alpha_ci=(float(lo), float(hi)),
        alpha_target=float(cfg.sampling.alpha),
        k=int(hill.k),
        ks_stat=float(ks.stat),
        ks_pvalue=float(ks.pvalue),
        ks_n_boot=int(ks.n_boot),
        alpha_hat_radicality=rho_alpha,
        radicality_ci=(rho_lo, rho_hi),
        n_radicality=rho_n,
        lr_statistic=float(lr.statistic),
        lr_p_chi2=float(lr.p_chi2),
        lr_p_boot=None if lr.p_boot is None else float(lr.p_boot),
        ks_point_estimator=ks.point_estimator,
        ks_bootstrap_estimator=ks.bootstrap_estimator,
        ks_refit=bool(ks.refit),
        rejection_filter=filtered,
        n_proposals=proposals,
        n_vacuous=vacuous,
        acceptance_rate=rate,
        hill_plot_k=[int(v) for v in grid_k],
        hill_plot_alpha=[float(v) if np.isfinite(v) else None for v in grid_alpha],
        notes=notes,
    )


def calibrate_dataset(
    dataset: Dataset,
    pipeline: Any,
    cfg: Config,
    *,
    n: int = 1000,
    seed: int = 0,
    n_boot: int | None = None,
) -> tuple[CalibrationReport, dict[str, int]]:
    """Parse a development set, collect distances, and calibrate."""
    rng = RngTree(seed)
    reps: list[Representation] = []
    for problem in dataset:
        deps, _ = pipeline.deps_for(problem)
        outcome = deps.parser.parse(problem, rng)
        if outcome.representation is not None:
            reps.append(outcome.representation)
    if not reps:
        raise RuntimeError("the parser failed on every development problem")

    sampler = RadicalitySampler(
        alpha=cfg.sampling.alpha,
        gamma_init=cfg.sampling.gamma_init,
        ks_alpha=cfg.sampling.ks_alpha,
        window=cfg.sampling.ks_window,
        rho_max=cfg.sampling.rho_max,
        gamma_min=cfg.sampling.gamma_min,
        gamma_max=cfg.sampling.gamma_max,
    )
    distances, radicality, counts = collect_distances(
        reps,
        pipeline.operators,
        pipeline.distance,
        pipeline.resources,
        rng,
        n=n,
        alpha=cfg.sampling.alpha,
        gamma=cfg.sampling.gamma_init,
        sampler=sampler,
    )
    report = calibrate(
        distances,
        cfg,
        rng.stream("calibration/bootstrap"),
        radicality=radicality,
        n_boot=n_boot,
        collection=counts,
    )
    return report, counts
