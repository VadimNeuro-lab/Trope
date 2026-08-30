"""Figures, built from the same run artifacts as the tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import ScalarFormatter

from trope.analysis.loader import (
    FAMILIES,
    MissingRuns,
    RunSet,
    benchmark_family,
    missing,
)
from trope.analysis.tables import (
    SCRIPTS,
    operator_kinds,
    point_estimates,
    usage_counts,
)

WIDTH = 3.2
OKABE_ITO = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442")

RC = {
    "figure.figsize": (WIDTH, WIDTH * 0.72),
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "lines.linewidth": 1.2,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
}


def _save(fig: plt.Figure, out_dir: Path, stem: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in (".pdf", ".png"):
        path = out_dir / f"{stem}{suffix}"
        fig.savefig(path, dpi=300)
        paths.append(path)
    plt.close(fig)
    return paths


def _find(root: Path, name: str) -> Path | None:
    direct = root / name
    if direct.exists():
        return direct
    return next(iter(sorted(root.rglob(name))), None)


def hill_plot(runs: RunSet, out_dir: Path) -> list[Path]:
    """alpha_hat against k, with the chosen k = floor(N^(2/3)) marked."""
    path = _find(runs.root, "calibration.json")
    if path is None:
        raise missing(
            "the Hill plot (runs/calibration.json)", "scripts/run_calibration.sh", runs.root
        )
    report = json.loads(path.read_text(encoding="utf-8"))
    ks = np.asarray(report.get("hill_plot_k") or [], dtype=float)
    alphas = np.asarray(report.get("hill_plot_alpha") or [], dtype=float)
    if ks.size == 0 or ks.size != alphas.size:
        raise missing(
            "the Hill plot (calibration.json has no hill_plot_k/hill_plot_alpha)",
            "scripts/run_calibration.sh",
            runs.root,
        )

    with plt.rc_context(RC):
        fig, ax = plt.subplots()
        ax.plot(ks, alphas, color=OKABE_ITO[0])
        chosen = report.get("k")
        if chosen is not None:
            ax.axvline(
                chosen,
                color=OKABE_ITO[1],
                linestyle="--",
                label=rf"$k=\lfloor N^{{2/3}}\rfloor={int(chosen)}$",
            )
        target = report.get("alpha_target")
        if target is not None:
            ax.axhline(
                target, color="0.4", linestyle=":", label=rf"$\alpha^*={target:g}$"
            )
        ci = report.get("alpha_ci")
        if ci and chosen is not None:
            ax.fill_between(
                [ks.min(), ks.max()], ci[0], ci[1], color=OKABE_ITO[0], alpha=0.12
            )
        ax.set_xlabel("$k$ (order statistics used)")
        ax.set_ylabel(r"$\hat\alpha_{\mathrm{Hill}}(k)$")
        ax.legend(frameon=False, loc="best")
        return _save(fig, out_dir, "hill_plot")


def budget_curve(runs: RunSet, out_dir: Path) -> list[Path]:
    """Figure 4(a): the metric against K for TROPE and the strongest baseline."""
    sweep = runs.select(group="budget")
    if not sweep:
        raise missing(
            "the budget curve (<root>/budget/<K> runs)", SCRIPTS["budget"], runs.root
        )
    frame = sweep.frame()
    ours = point_estimates(frame[frame["arm"] == "trope"], ["variant"])
    baselines = frame[frame["arm"] != "trope"]

    def as_int(value: str) -> float:
        try:
            return float(value)
        except ValueError:
            return float("nan")

    ours = ours.assign(k=[as_int(v) for v in ours["variant"]]).sort_values("k")
    if ours.empty:
        raise missing("the budget curve (no TROPE runs)", SCRIPTS["budget"], runs.root)

    with plt.rc_context(RC):
        fig, ax = plt.subplots()
        ax.errorbar(
            ours["k"],
            ours["value"],
            yerr=ours["se"],
            color=OKABE_ITO[0],
            marker="o",
            markersize=3,
            capsize=2,
            label="TROPE",
        )
        if not baselines.empty:
            best = point_estimates(baselines, ["variant", "arm"])
            best = best.loc[best.groupby("variant")["value"].idxmax()]
            best = best.assign(k=[as_int(v) for v in best["variant"]]).sort_values("k")
            ax.errorbar(
                best["k"],
                best["value"],
                yerr=best["se"],
                color=OKABE_ITO[1],
                marker="s",
                markersize=3,
                capsize=2,
                linestyle="--",
                label="strongest baseline",
            )
        ax.set_xscale("log", base=2)
        ax.set_xticks(sorted(ours["k"].dropna().unique()))
        ax.get_xaxis().set_major_formatter(ScalarFormatter())
        ax.set_xlabel("$K$ (generator calls per problem)")
        ax.set_ylabel("verified pass rate (%)")
        ax.legend(frameon=False, loc="best")
        return _save(fig, out_dir, "budget_curve")


def operator_usage(runs: RunSet, out_dir: Path) -> list[Path]:
    """Figure 4(b): stacked horizontal bars of level share by task family."""
    trope = runs.select(arm="trope")
    if not trope:
        raise missing("the usage bars (TROPE runs)", SCRIPTS["usage"], runs.root)
    kinds = operator_kinds()
    per_family: dict[str, dict[str, float]] = {}
    for run in trope.runs:
        cell = per_family.setdefault(
            benchmark_family(run.benchmark),
            {"token": 0.0, "mutation": 0.0, "crossover": 0.0},
        )
        counts = usage_counts(run, kinds)
        for level in cell:
            cell[level] += counts[level]

    families = [f for f in FAMILIES if per_family.get(f) and sum(per_family[f].values())]
    families += sorted(
        f for f in per_family if f not in FAMILIES and sum(per_family[f].values())
    )
    if not families:
        raise missing(
            "the usage bars (no operator selections recorded)", SCRIPTS["usage"], runs.root
        )

    with plt.rc_context(RC):
        fig, ax = plt.subplots(figsize=(WIDTH, WIDTH * 0.55))
        y = np.arange(len(families))
        left = np.zeros(len(families))
        for colour, level, label in zip(
            OKABE_ITO, ("token", "mutation", "crossover"), ("token", "mutation", "crossover"), strict=False
        ):
            widths = np.array(
                [
                    100.0 * per_family[f][level] / sum(per_family[f].values())
                    for f in families
                ]
            )
            ax.barh(y, widths, left=left, color=colour, label=label, height=0.62)
            left += widths
        ax.set_yticks(y, families)
        ax.set_xlim(0, 100)
        ax.set_xlabel("selections (%)")
        ax.invert_yaxis()
        ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.18))
        return _save(fig, out_dir, "operator_usage")


def radicality_hist(runs: RunSet, out_dir: Path) -> list[Path]:
    """Survival function of accepted rho on log-log axes, with the Hill slope."""
    values = [
        float(record["radicality"])
        for record in runs.traces(arm="trope")
        if record.get("accepted") and record.get("radicality")
    ]
    rho = np.asarray([v for v in values if v > 0.0], dtype=float)
    if rho.size < 8:
        raise missing(
            "the radicality distribution (traces with accepted candidates)",
            SCRIPTS["usage"],
            runs.root,
        )

    order = np.sort(rho)[::-1]
    survival = np.arange(1, order.size + 1) / order.size
    alpha, k = _hill(order, runs)

    with plt.rc_context(RC):
        fig, ax = plt.subplots()
        ax.loglog(
            order,
            survival,
            marker=".",
            linestyle="none",
            markersize=2.5,
            color=OKABE_ITO[0],
            label=r"accepted $\rho$",
        )
        if alpha is not None and k and k < order.size:
            anchor = order[k]
            grid = np.linspace(np.log(anchor), np.log(order[0]), 32)
            ax.loglog(
                np.exp(grid),
                (k / order.size) * np.exp(-alpha * (grid - np.log(anchor))),
                color=OKABE_ITO[1],
                linestyle="--",
                label=rf"Hill fit, $\hat\alpha={alpha:.2f}$",
            )
        ax.set_xlabel(r"$\rho$")
        ax.set_ylabel(r"$\Pr[\,\rho > x\,]$")
        ax.legend(frameon=False, loc="best")
        return _save(fig, out_dir, "radicality_hist")


def _hill(descending: np.ndarray, runs: RunSet) -> tuple[float | None, int]:
    """Hill tail index at k = floor(N^hill_exponent), from the run config."""
    exponent = 2.0 / 3.0
    for run in runs.runs:
        configured = (run.config.get("sampling") or {}).get("hill_exponent")
        if configured:
            exponent = float(configured)
            break
    n = descending.size
    k = max(2, min(n - 1, int(n**exponent)))
    try:
        from trope.stats.hill import hill_estimate  # type: ignore

        estimate = hill_estimate(descending)
        return float(estimate.alpha), int(getattr(estimate, "k", k))
    except ImportError:
        logs = np.log(descending[:k]) - np.log(descending[k])
        mean = float(logs.mean())
        return (1.0 / mean if mean > 0 else None), k


def controller_trace(runs: RunSet, out_dir: Path) -> list[Path]:
    """gamma and lambda_struct over iterations, with the controller band shaded."""
    chosen = None
    steps: list[dict[str, Any]] = []
    for run in runs.select(arm="trope").runs:
        by_problem: dict[str, list[dict[str, Any]]] = {}
        for record in run.trace():
            if record.get("lambda_struct") is None or record.get("gamma") is None:
                continue
            by_problem.setdefault(str(record.get("problem_id", "")), []).append(record)
        if by_problem:
            key = max(by_problem, key=lambda p: len(by_problem[p]))
            chosen, steps = run, sorted(by_problem[key], key=lambda r: r["iteration"])
            break
    if chosen is None or len(steps) < 2:
        raise missing(
            "the controller trace (traces recording gamma and lambda_struct)",
            SCRIPTS["band"],
            runs.root,
        )

    controller = chosen.config.get("controller") or {}
    lo = float(controller.get("lambda_min", 0.05))
    hi = float(controller.get("lambda_max", 0.40))
    setpoint = controller.get("setpoint")
    iterations = np.array([r["iteration"] for r in steps], dtype=float)
    gamma = np.array([r["gamma"] for r in steps], dtype=float)
    lam = np.array([r["lambda_struct"] for r in steps], dtype=float)

    with plt.rc_context(RC):
        fig, ax = plt.subplots()
        twin = ax.twinx()
        twin.spines["right"].set_visible(True)
        twin.axhspan(lo, hi, color=OKABE_ITO[2], alpha=0.15, lw=0)
        if setpoint is not None:
            twin.axhline(float(setpoint), color=OKABE_ITO[2], linestyle=":")
        line_l, = twin.plot(iterations, lam, color=OKABE_ITO[2],
                            label=r"$\hat\lambda_{\mathrm{struct}}$")
        line_g, = ax.plot(iterations, gamma, color=OKABE_ITO[0], label=r"$\gamma$")
        ax.set_xlabel("iteration $t$")
        ax.set_ylabel(r"$\gamma$")
        twin.set_ylabel(r"$\hat\lambda_{\mathrm{struct}}$")
        ax.legend(handles=[line_g, line_l], frameon=False, loc="best")
        return _save(fig, out_dir, "controller_trace")


FIGURES = (
    ("hill_plot", hill_plot),
    ("budget_curve", budget_curve),
    ("operator_usage", operator_usage),
    ("radicality_hist", radicality_hist),
    ("controller_trace", controller_trace),
)


def build_figures(runs_root: str | Path, out_dir: str | Path) -> list[Path]:
    runs = RunSet(runs_root)
    out_dir = Path(out_dir)
    written: list[Path] = []
    skipped: list[str] = []
    for name, builder in FIGURES:
        try:
            written += builder(runs, out_dir)
        except MissingRuns as exc:
            skipped.append(f"{name}: {exc}")
    for line in skipped:
        print(f"skipped {line}")
    if not written:
        raise missing(
            "any figure", "the launch scripts in README.md", runs_root
        )
    return written
