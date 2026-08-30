"""Build the paper's tables from run artifacts."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from trope.analysis.loader import (
    FAMILIES,
    MissingRuns,
    RunRecord,
    RunSet,
    benchmark_family,
    benchmark_label,
    missing,
    ordered_benchmarks,
)

DASH = "--"
UNMEASURED = ""

SCRIPTS: dict[str, str] = {
    "main": "scripts/run_main.sh",
    "fullse": "scripts/run_main.sh",
    "decomposition": "scripts/run_ablations.sh",
    "ablation": "scripts/run_ablations.sh",
    "component": "scripts/run_ablations.sh",
    "loo": "scripts/run_ablations.sh",
    "pairdiag": "scripts/run_ablations.sh",
    "equalcompute": "scripts/run_equalcompute.sh",
    "trace": "scripts/run_main.sh (any TROPE run writes trace.jsonl)",
    "band": "scripts/run_main.sh (any TROPE run writes trace.jsonl)",
    "cost": "scripts/run_main.sh",
    "usage": "scripts/run_main.sh",
    "alpha": "scripts/run_sensitivity.sh",
    "lmref": "scripts/run_sensitivity.sh",
    "budget": "scripts/run_sensitivity.sh",
    "commute": "scripts/run_commutativity.sh",
    "audit": "scripts/run_main.sh (traces) plus the evidence corpus",
}

GROUPS: dict[str, tuple[str, ...]] = {
    "sensitivity": ("alpha", "lmref", "budget"),
    "ablations": ("decomposition", "ablation", "component", "loo", "pairdiag"),
}

COMPARISON = ("main", "fullse", "decomposition", "ablation", "component", "loo", "pairdiag")

BASELINE_ORDER: tuple[tuple[str, str], ...] = (
    ("greedy", "Greedy"),
    ("temp_0.7", r"Temp.\ $T\!=\!0.7$"),
    ("temp_1.0", r"Temp.\ $T\!=\!1.0$"),
    ("temp_1.2", r"Temp.\ $T\!=\!1.2$"),
    ("top_p", "Top-$p$"),
    ("min_p", "Min-$p$"),
    ("top_h", "Top-$H$"),
    ("eta", r"$\eta$-sampling"),
    ("self_consistency", "Self-Cons."),
    ("tot", "ToT"),
    ("verbalized_sampling", r"Verb.\ Samp."),
    ("funsearch", "FunSearch"),
    ("promptbreeder", "PromptBr."),
    ("evoprompt", "EvoPrompt"),
    ("eureka", "Eureka"),
    ("uot", "UoT"),
)

COMPONENT_ROWS: tuple[tuple[str, str], ...] = (
    ("no_parser", r"$-$ parser $\Phi$"),
    ("no_heavytail", r"$-$ heavy-tail (Gaussian)"),
    ("no_novelty", r"$-$ compression $\Nov$ (cosine)"),
    ("no_divctrl", r"$-$ divergence ctrl."),
    ("no_rejection", r"$-$ rejection filter"),
    ("no_mapelites", r"$-$ MAP-Elites adaptation"),
)

SYSTEM_ROWS: tuple[tuple[str, str], ...] = (
    ("trope_lite", r"\TROPE{}-lite"),
    ("two_level", r"Two-level \TROPE{}"),
    ("full", r"Full \TROPE{}"),
)

DECOMP_ROWS: tuple[tuple[str, tuple[bool, bool, bool]], ...] = (
    ("tok", (True, False, False)),
    ("mut", (False, True, False)),
    ("cross", (False, False, True)),
    ("tok_mut", (True, True, False)),
    ("tok_cross", (True, False, True)),
    ("mut_cross", (False, True, True)),
    ("full", (True, True, True)),
)

ABLATION_BENCHMARKS = ("math500", "aime", "uot")
LOO_BENCHMARKS = ("math500", "aime", "uot", "llmsrbench")
ALPHA_BENCHMARKS = ("math500", "livecodebench", "uot")
CROSSFAMILY_BENCHMARKS = ("math500", "aime", "usamo", "uot")

COST_STAGES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (r"\quad parser ($\Phi$)", ("parser",), "parser"),
    (r"\quad operator $+$ gen.", ("generator",), "generation"),
    (r"\quad compression score", ("reference", "reference_score"), "novelty"),
    (r"\quad distance comp.", (), "distance"),
)

REFERENCE_ROLES = ("reference", "reference_score")

GPU_HOURS_KEYS = ("gpu_hours", "gpu_hours_total")
PEAK_MEMORY_KEYS = ("peak_memory_gb", "peak_gpu_memory_gb", "max_memory_gb")


class BudgetMismatch(RuntimeError):
    """Arms in a comparison table did not receive a matched generator budget."""


@dataclass(slots=True)
class Context:
    runs: RunSet
    out_dir: Path
    notes: list[str]


def _fmt(value: Any, digits: int = 1, blank: str = UNMEASURED) -> str:
    if value is None:
        return blank
    if isinstance(value, float) and math.isnan(value):
        return blank
    return f"{float(value):.{digits}f}"


def _bold(cell: str) -> str:
    return cell if cell in (DASH, UNMEASURED) else rf"\textbf{{{cell}}}"


def _pval(p: float | None) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return UNMEASURED
    if p < 0.001:
        return "$<$.001"
    return f"{p:.3f}".lstrip("0")


RULE = "\\midrule"


def _tabular(colspec: str, header: Sequence[Any], body: Sequence[Any]) -> str:
    lines = [r"\begin{tabular}{" + colspec + "}", r"\toprule"]
    for row in header:
        lines.append(row if isinstance(row, str) else " & ".join(row) + r" \\")
    lines.append(RULE)
    for row in body:
        lines.append(row if isinstance(row, str) else " & ".join(row) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def _comment(name: str, ctx: Context, runs: RunSet, extra: Iterable[str] = ()) -> str:
    seeds = runs.seeds()
    lines = [
        f"% table `{name}`, built by trope.analysis.tables from run artifacts.",
        f"% runs root: {ctx.runs.root}",
        f"% seeds (n={len(seeds)}): {','.join(str(s) for s in seeds)}",
        f"% built from {len(runs)} run director" + ("y:" if len(runs) == 1 else "ies:"),
    ]
    lines += [f"%   {entry}" for entry in runs.provenance()]
    lines += [f"% {line}" for line in extra]
    return "\n".join(lines)


def _write(ctx: Context, name: str, frame: pd.DataFrame, tex: str) -> list[Path]:
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = ctx.out_dir / f"{name}.csv"
    tex_path = ctx.out_dir / f"{name}.tex"
    frame.to_csv(csv_path, index=False, encoding="utf-8", lineterminator="\n")
    tex_path.write_text(tex.rstrip() + "\n", encoding="utf-8")
    return [csv_path, tex_path]


def _seed_means(frame: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """Mean score per (keys, seed), on the paper's 0--100 scale."""
    if frame.empty:
        return pd.DataFrame(columns=[*keys, "seed", "value"])
    grouped = frame.groupby([*keys, "seed"], dropna=False)["score"].mean() * 100.0
    return grouped.reset_index(name="value")


def point_estimates(frame: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """Mean over seeds and SE = sd_over_seeds / sqrt(n_seeds)."""
    seed_means = _seed_means(frame, keys)
    if seed_means.empty:
        return pd.DataFrame(columns=[*keys, "value", "se", "n_seeds"])
    agg = seed_means.groupby(list(keys), dropna=False)["value"].agg(
        value="mean", sd=lambda s: s.std(ddof=1), n_seeds="size"
    )
    agg["se"] = agg["sd"] / np.sqrt(agg["n_seeds"])
    return agg.drop(columns="sd").reset_index()


def _lookup(point: pd.DataFrame, keys: Sequence[str]) -> dict[tuple, tuple[float, float]]:
    return {
        tuple(row[k] for k in keys): (row["value"], row["se"])
        for _, row in point.iterrows()
    }


def _run_frame(runs: RunSet) -> pd.DataFrame:
    """One row per run, from summary.json plus the ledger."""
    rows = []
    for run in runs.runs:
        summary = run.summary
        rows.append(
            {
                "arm": run.arm,
                "variant": run.variant,
                "group": run.group,
                "benchmark": run.benchmark,
                "family": benchmark_family(run.benchmark),
                "seed": run.seed,
                "n_problems": run.n_problems,
                "solve_rate": summary.get("solve_rate"),
                "mean_coverage": summary.get("mean_coverage"),
                "mean_novelty": summary.get("mean_novelty"),
                "generator_calls": run.calls("generator"),
                "run_dir": str(run.path),
            }
        )
    return pd.DataFrame(rows)


def _task_compatibility() -> tuple[dict[str, set[str]] | None, str]:
    """The baseline registry's compatibility map, if the registry is importable."""
    try:
        from trope.baselines.registry import TASK_COMPATIBILITY  # type: ignore
    except Exception as exc:
        return None, (
            f"trope.baselines.registry is unavailable ({exc.__class__.__name__}), so a "
            f"cell with no runs is left empty rather than marked task-incompatible"
        )
    table = {k: set(v) for k, v in dict(TASK_COMPATIBILITY).items()}
    return table, 'marked "--" from trope.baselines.registry.TASK_COMPATIBILITY'


def _incompatible(table: dict[str, set[str]] | None, arm: str, benchmark: str) -> bool:
    if table is None:
        return False
    allowed = table.get(arm)
    return allowed is not None and benchmark not in allowed


def _wilcoxon(x: Sequence[float], y: Sequence[float]) -> tuple[float | None, str]:
    """Two-sided paired Wilcoxon signed-rank p-value, and which code produced it."""
    try:
        from trope.stats.tests import paired_wilcoxon  # type: ignore

        result = paired_wilcoxon(np.asarray(x, float), np.asarray(y, float))
        return float(getattr(result, "pvalue", result)), "trope.stats.tests.paired_wilcoxon"
    except ImportError:
        pass
    from scipy.stats import wilcoxon

    diff = np.asarray(x, float) - np.asarray(y, float)
    if diff.size == 0 or np.allclose(diff, 0.0):
        return None, "scipy.stats.wilcoxon (undefined: all paired differences are zero)"
    try:
        stat = wilcoxon(diff, alternative="two-sided", zero_method="wilcox")
    except ValueError:
        return None, "scipy.stats.wilcoxon (undefined for this sample)"
    return float(stat.pvalue), (
        "scipy.stats.wilcoxon, method=auto (exact for small n, normal "
        "approximation with continuity correction otherwise)"
    )


def _paired(frame: pd.DataFrame, benchmark: str, arm_a: str, arm_b: str):
    """Per-problem scores of two arms, each averaged over seeds, on shared problems."""
    sub = frame[frame["benchmark"] == benchmark]
    per_problem = sub.groupby(["arm", "problem_id"], dropna=False)["score"].mean()
    try:
        a = per_problem.loc[arm_a]
        b = per_problem.loc[arm_b]
    except KeyError:
        return np.array([]), np.array([])
    shared = a.index.intersection(b.index)
    return a.loc[shared].to_numpy(), b.loc[shared].to_numpy()


def _benchmark_columns(runs: RunSet, wanted: Sequence[str], name: str) -> list[str]:
    present = set(runs.benchmarks())
    columns = [b for b in wanted if b in present]
    if not columns:
        raise missing(
            f"table `{name}` (needs any of {', '.join(wanted)})",
            SCRIPTS.get(name, "the scripts in README.md"),
            runs.root,
        )
    return columns


def _pretty_variant(variant: str) -> str:
    """Row label from a run-directory name, leaving inner capitals alone."""
    text = variant.replace("_", " ")
    return text[:1].upper() + text[1:]


def build_main(ctx: Context) -> list[Path]:
    runs = ctx.runs
    frame = runs.frame()
    if frame.empty:
        raise missing("table `main`", SCRIPTS["main"], runs.root)
    benchmarks = ordered_benchmarks(sorted(frame["benchmark"].unique()))
    point = point_estimates(frame, ["arm", "benchmark"])
    cells = _lookup(point, ["arm", "benchmark"])

    compat, compat_source = _task_compatibility()
    arms = [a for a, _ in BASELINE_ORDER if a in set(frame["arm"])]
    arms += sorted(set(frame["arm"]) - {a for a, _ in BASELINE_ORDER} - {"trope"})
    labels = dict(BASELINE_ORDER)
    if "trope" not in set(frame["arm"]):
        raise missing("the TROPE arm of table `main`", SCRIPTS["main"], runs.root)

    strongest: dict[str, str] = {}
    for benchmark in benchmarks:
        scored = [(cells[(a, benchmark)][0], a) for a in arms if (a, benchmark) in cells]
        if scored:
            strongest[benchmark] = max(scored)[1]

    records: list[dict[str, Any]] = []
    body: list[Any] = []
    best = {
        b: max(
            (cells[(a, b)][0] for a in [*arms, "trope"] if (a, b) in cells),
            default=None,
        )
        for b in benchmarks
    }

    def emit(arm: str, label: str, with_se: bool) -> list[str]:
        row = [label]
        for benchmark in benchmarks:
            entry = cells.get((arm, benchmark))
            if entry is None:
                cell = DASH if _incompatible(compat, arm, benchmark) else UNMEASURED
                value, se = None, None
            else:
                value, se = entry
                cell = _fmt(value)
                if with_se and se is not None and not math.isnan(se):
                    cell = f"{cell}$_{{{se:.1f}}}$"
                if best[benchmark] is not None and value >= best[benchmark] - 1e-9:
                    cell = _bold(cell)
            records.append(
                {
                    "row_type": "method",
                    "row": arm,
                    "benchmark": benchmark,
                    "value": value,
                    "se": se,
                    "incompatible": entry is None and _incompatible(compat, arm, benchmark),
                }
            )
            row.append(cell)
        return row

    for arm in arms:
        body.append(emit(arm, labels.get(arm, _pretty_variant(arm)), False))
    body.append(RULE)
    body.append(emit("trope", r"\TROPE{} (ours)", True))
    body.append(RULE)

    strong_row = ["Strongest baseline"]
    delta_row = [r"$\Delta$"]
    p_row = ["$p$ (Wilcoxon)"]
    sources: set[str] = set()
    for benchmark in benchmarks:
        arm = strongest.get(benchmark)
        base = cells.get((arm, benchmark), (None, None))[0] if arm else None
        ours = cells.get(("trope", benchmark), (None, None))[0]
        delta = None if (base is None or ours is None) else ours - base
        p, source = (None, "")
        if arm is not None:
            x, y = _paired(frame, benchmark, "trope", arm)
            if x.size:
                p, source = _wilcoxon(x, y)
                sources.add(source)
        strong_row.append(_fmt(base))
        delta_row.append(UNMEASURED if delta is None else f"${delta:+.1f}$")
        p_row.append(_pval(p))
        records.append(
            {
                "row_type": "summary",
                "row": "strongest_baseline",
                "benchmark": benchmark,
                "value": base,
                "se": None,
                "strongest_arm": arm,
                "delta": delta,
                "wilcoxon_p": p,
                "n_paired": int(_paired(frame, benchmark, "trope", arm)[0].size)
                if arm
                else 0,
            }
        )
    body += [strong_row, delta_row, p_row]

    header = [
        _group_header(benchmarks),
        _cmidrules(benchmarks),
        ["Method", *(benchmark_label(b) for b in benchmarks)],
    ]
    tex = _comment(
        "main",
        ctx,
        runs,
        [
            "metric: percentage of problems whose candidate passed V_P, "
            "averaged over seeds; n = benchmark size",
            f"task-incompatible cells: {compat_source}",
            *(f"Wilcoxon: {s}" for s in sorted(sources)),
            "paired over problem instances, each problem's score averaged over seeds",
        ],
    )
    tex += "\n" + _tabular("@{}l" + "c" * len(benchmarks) + "@{}", header, body)
    return _write(ctx, "main", pd.DataFrame(records), tex)


def _spans(benchmarks: Sequence[str]) -> list[tuple[str, int]]:
    """Contiguous family runs across the benchmark columns."""
    spans: list[tuple[str, int]] = []
    for benchmark in benchmarks:
        family = benchmark_family(benchmark)
        if spans and spans[-1][0] == family:
            spans[-1] = (family, spans[-1][1] + 1)
        else:
            spans.append((family, 1))
    return spans


def _group_header(benchmarks: Sequence[str]) -> str:
    cells = [rf"\multicolumn{{{n}}}{{c}}{{{f}}}" for f, n in _spans(benchmarks)]
    return " & ".join(["", *cells]) + r" \\"


def _cmidrules(benchmarks: Sequence[str]) -> str:
    spans = _spans(benchmarks)
    out, start = [], 2
    for _, n in spans:
        out.append(rf"\cmidrule(lr){{{start}-{start + n - 1}}}")
        start += n
    return "".join(out)


def build_fullse(ctx: Context) -> list[Path]:
    runs = ctx.runs
    frame = runs.frame()
    if frame.empty:
        raise missing("table `fullse`", SCRIPTS["fullse"], runs.root)
    benchmarks = ordered_benchmarks(sorted(frame["benchmark"].unique()))
    cells = _lookup(point_estimates(frame, ["arm", "benchmark"]), ["arm", "benchmark"])
    compat, compat_source = _task_compatibility()

    arms = [a for a, _ in BASELINE_ORDER if a in set(frame["arm"])]
    arms += sorted(set(frame["arm"]) - {a for a, _ in BASELINE_ORDER} - {"trope"})
    labels = dict(BASELINE_ORDER)

    records: list[dict[str, Any]] = []
    body: list[Any] = []
    for arm in [*arms, "trope"]:
        if arm == "trope":
            if "trope" not in set(frame["arm"]):
                continue
            body.append(RULE)
        row = [labels.get(arm, r"\TROPE{}" if arm == "trope" else _pretty_variant(arm))]
        for benchmark in benchmarks:
            entry = cells.get((arm, benchmark))
            if entry is None:
                row.append(DASH if _incompatible(compat, arm, benchmark) else UNMEASURED)
            else:
                value, se = entry
                row.append(f"{value:.1f}$\\pm${se:.1f}" if not math.isnan(se) else _fmt(value))
            records.append(
                {
                    "row_type": "method",
                    "row": arm,
                    "benchmark": benchmark,
                    "value": None if entry is None else entry[0],
                    "se": None if entry is None else entry[1],
                    "n_seeds": len(
                        frame[(frame["arm"] == arm) & (frame["benchmark"] == benchmark)][
                            "seed"
                        ].unique()
                    ),
                }
            )
        body.append(row)

    p_row = ["$p$ (Wilcoxon)"]
    sources: set[str] = set()
    for benchmark in benchmarks:
        scored = [(cells[(a, benchmark)][0], a) for a in arms if (a, benchmark) in cells]
        p = None
        if scored and ("trope", benchmark) in cells:
            arm = max(scored)[1]
            x, y = _paired(frame, benchmark, "trope", arm)
            if x.size:
                p, source = _wilcoxon(x, y)
                sources.add(source)
                records.append(
                    {
                        "row_type": "wilcoxon",
                        "row": "trope_vs_strongest",
                        "benchmark": benchmark,
                        "value": p,
                        "strongest_arm": arm,
                        "n_paired": int(x.size),
                    }
                )
        p_row.append(_pval(p))
    body.append(p_row)

    tex = _comment(
        "fullse",
        ctx,
        runs,
        [
            "cells are mean over seeds +/- SE, SE = sd_over_seeds / sqrt(n_seeds)",
            f"task-incompatible cells: {compat_source}",
            *(f"Wilcoxon: {s}" for s in sorted(sources)),
        ],
    )
    tex += "\n" + _tabular(
        "@{}l" + "c" * len(benchmarks) + "@{}",
        [["", *(benchmark_label(b) for b in benchmarks)]],
        body,
    )
    return _write(ctx, "fullse", pd.DataFrame(records), tex)


def build_decomposition(ctx: Context) -> list[Path]:
    runs = ctx.runs
    run_frame = _run_frame(runs)
    have = set(run_frame["variant"]) if not run_frame.empty else set()
    rows = [(v, marks) for v, marks in DECOMP_ROWS if v in have]
    if not rows:
        raise missing(
            "table `decomposition` (operator-subset runs tok/mut/cross/...)",
            SCRIPTS["decomposition"],
            runs.root,
        )
    frame = runs.frame()
    verif = _lookup(point_estimates(frame, ["variant"]), ["variant"])

    agg = run_frame.groupby("variant", dropna=False).agg(
        coverage=("mean_coverage", "mean"),
        novelty=("mean_novelty", "mean"),
        n_runs=("seed", "size"),
    )

    records, body = [], []
    for variant, marks in rows:
        cov = agg.loc[variant, "coverage"] if variant in agg.index else None
        nov = agg.loc[variant, "novelty"] if variant in agg.index else None
        value, se = verif.get((variant,), (None, None))
        cells = [
            r"\checkmark" if marks[0] else "",
            r"\checkmark" if marks[1] else "",
            r"\checkmark" if marks[2] else "",
            _fmt(None if cov is None else 100.0 * cov),
            _fmt(nov, digits=2),
            _fmt(None if value is None else value / 100.0, digits=2),
        ]
        body.append(cells)
        records.append(
            {
                "variant": variant,
                "token": marks[0],
                "mutation": marks[1],
                "crossover": marks[2],
                "coverage": None if cov is None else 100.0 * cov,
                "novelty": nov,
                "verified": None if value is None else value / 100.0,
                "verified_se": None if se is None else se / 100.0,
            }
        )

    tex = _comment(
        "decomposition",
        ctx,
        runs,
        [
            "Cov. = mean archive coverage x100; Nov = summary mean_novelty;",
            "Verif. = verified pass rate, averaged over benchmarks and seeds",
        ],
    )
    tex += "\n" + _tabular(
        "@{}cccccc@{}",
        [[r"$\Otok$", r"$\Omut$", r"$\Ocross$", "Cov.", r"$\Nov$", "Verif."]],
        body,
    )
    return _write(ctx, "decomposition", pd.DataFrame(records), tex)


def build_ablation(ctx: Context) -> list[Path]:
    runs = ctx.runs
    frame = runs.frame()
    if frame.empty:
        raise missing("table `ablation`", SCRIPTS["ablation"], runs.root)
    benchmarks = _benchmark_columns(runs, ABLATION_BENCHMARKS, "ablation")
    cells = _lookup(point_estimates(frame, ["variant", "benchmark"]), ["variant", "benchmark"])
    arm_cells = _lookup(point_estimates(frame, ["arm", "benchmark"]), ["arm", "benchmark"])
    have = set(frame["variant"])
    gpu = _gpu_hours_by_variant(runs)

    records: list[dict[str, Any]] = []
    body: list[Any] = [
        rf"\multicolumn{{{len(benchmarks) + 2}}}{{@{{}}l}}{{\emph{{Component removal, "
        rf"from full \TROPE{{}}}}}} \\"
    ]
    skipped: list[str] = []

    def emit(variant: str, label: str) -> None:
        row = [label]
        for benchmark in benchmarks:
            value = cells.get((variant, benchmark), (None, None))[0]
            row.append(_fmt(value))
            records.append(
                {"block": block, "variant": variant, "benchmark": benchmark, "value": value}
            )
        row.append(_fmt(gpu.get(variant), digits=2))
        body.append(row)

    block = "component_removal"
    for variant, label in COMPONENT_ROWS:
        if variant in have:
            emit(variant, label)
        else:
            skipped.append(f"{label.strip()} (no runs named `{variant}`)")

    strongest_present = [
        a for a in set(frame["arm"]) if a != "trope" and (a, benchmarks[0]) in arm_cells
    ]
    body.append(RULE)
    body.append(
        rf"\multicolumn{{{len(benchmarks) + 2}}}{{@{{}}l}}{{\emph{{System complexity}}}} \\"
    )
    block = "system_complexity"
    if strongest_present:
        row = ["Strongest baseline"]
        for benchmark in benchmarks:
            scored = [
                (arm_cells[(a, benchmark)][0], a)
                for a in set(frame["arm"])
                if a != "trope" and (a, benchmark) in arm_cells
            ]
            value = max(scored)[0] if scored else None
            row.append(_fmt(value))
            records.append(
                {
                    "block": block,
                    "variant": "strongest_baseline",
                    "benchmark": benchmark,
                    "value": value,
                    "strongest_arm": max(scored)[1] if scored else None,
                }
            )
        row.append(UNMEASURED)
        body.append(row)
    else:
        skipped.append("Strongest baseline (no baseline arms under this root)")

    for variant, label in SYSTEM_ROWS:
        if variant in have:
            emit(variant, label)
        else:
            skipped.append(f"{label.strip()} (no runs named `{variant}`)")

    if not records:
        raise missing("table `ablation`", SCRIPTS["ablation"], runs.root)

    extra = [
        "GPU-h/100 is empty unless a run recorded it in manifest.json "
        f"(keys: {', '.join(GPU_HOURS_KEYS)})"
    ]
    if skipped:
        extra.append("rows omitted for want of runs:")
        extra += [f"  {s}" for s in skipped]
    tex = _comment("ablation", ctx, runs, extra)
    tex += "\n" + _tabular(
        "@{}l" + "c" * (len(benchmarks) + 1) + "@{}",
        [["Configuration", *(benchmark_label(b) for b in benchmarks), "GPU-h"]],
        body,
    )
    return _write(ctx, "ablation", pd.DataFrame(records), tex)


def _gpu_hours_by_variant(runs: RunSet) -> dict[str, float]:
    out: dict[str, list[float]] = {}
    for run in runs.runs:
        hours = _manifest_number(run, GPU_HOURS_KEYS)
        if hours is None:
            continue
        n = run.n_problems
        if n:
            out.setdefault(run.variant, []).append(100.0 * hours / n)
    return {k: sum(v) / len(v) for k, v in out.items()}


def _manifest_number(run: RunRecord, keys: Sequence[str]) -> float | None:
    for key in keys:
        value = run.manifest.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def build_component(ctx: Context) -> list[Path]:
    runs = ctx.runs
    frame = runs.frame()
    if frame.empty:
        raise missing("table `component`", SCRIPTS["component"], runs.root)
    benchmarks = ordered_benchmarks(sorted(frame["benchmark"].unique()))
    cells = _lookup(point_estimates(frame, ["variant", "benchmark"]), ["variant", "benchmark"])
    have = set(frame["variant"])
    rows = [
        (variant, label)
        for variant, label in [("full", r"Full \TROPE{} (ours)"), *COMPONENT_ROWS]
        if variant in have
    ]
    if not rows:
        raise missing(
            "table `component` (component-removal runs no_parser/no_heavytail/...)",
            SCRIPTS["component"],
            runs.root,
        )

    records, body = [], []
    for variant, label in rows:
        row = [label]
        for benchmark in benchmarks:
            value = cells.get((variant, benchmark), (None, None))[0]
            row.append(_fmt(value))
            records.append({"variant": variant, "benchmark": benchmark, "value": value})
        body.append(row)

    tex = _comment("component", ctx, runs)
    tex += "\n" + _tabular(
        "@{}l" + "c" * len(benchmarks) + "@{}",
        [
            _group_header(benchmarks),
            _cmidrules(benchmarks),
            ["Config", *(benchmark_label(b) for b in benchmarks)],
        ],
        body,
    )
    return _write(ctx, "component", pd.DataFrame(records), tex)


def build_loo(ctx: Context) -> list[Path]:
    runs = ctx.runs
    frame = runs.frame()
    variants = sorted(v for v in set(frame["variant"]) if v.startswith("loo_"))
    if not variants:
        raise missing(
            "table `loo` (leave-one-operator-out runs named loo_<operator>)",
            SCRIPTS["loo"],
            runs.root,
        )
    benchmarks = _benchmark_columns(runs, LOO_BENCHMARKS, "loo")
    cells = _lookup(point_estimates(frame, ["variant", "benchmark"]), ["variant", "benchmark"])

    kinds = operator_kinds()
    ordered = sorted(
        variants,
        key=lambda v: (
            ["token", "mutation", "crossover"].index(kinds.get(v[4:], "token"))
            if kinds.get(v[4:]) in ("token", "mutation", "crossover")
            else 3,
            v,
        ),
    )

    records, body = [], []
    if "full" in set(frame["variant"]):
        row = [r"None / Full \TROPE{}"]
        for benchmark in benchmarks:
            value = cells.get(("full", benchmark), (None, None))[0]
            row.append(_fmt(value))
            records.append({"removed": None, "benchmark": benchmark, "value": value})
        body += [row, RULE]

    previous: str | None = None
    for variant in ordered:
        operator = variant[4:]
        kind = kinds.get(operator)
        if previous is not None and kind != previous:
            body.append(RULE)
        previous = kind
        row = [_pretty_variant(operator)]
        for benchmark in benchmarks:
            value = cells.get((variant, benchmark), (None, None))[0]
            row.append(_fmt(value))
            records.append(
                {"removed": operator, "kind": kind, "benchmark": benchmark, "value": value}
            )
        body.append(row)

    tex = _comment(
        "loo",
        ctx,
        runs,
        ["row labels are catalog operator names; rules group them by operator level"],
    )
    tex += "\n" + _tabular(
        "@{}l" + "c" * len(benchmarks) + "@{}",
        [["Removed operator", *(benchmark_label(b) for b in benchmarks)]],
        body,
    )
    return _write(ctx, "loo", pd.DataFrame(records), tex)


def operator_kinds() -> dict[str, str]:
    try:
        from trope.operators.base import catalog

        return {op.name: op.kind for op in catalog()}
    except Exception:
        return {}


def build_pairdiag(ctx: Context) -> list[Path]:
    runs = ctx.runs
    frame = runs.frame()
    variants = sorted(
        (
            v
            for v in set(frame["variant"])
            if v.startswith(("only_", "pair_", "minus_"))
        ),
        key=lambda v: (v.startswith("minus_"), v),
    )
    if not variants:
        raise missing(
            "table `pairdiag` (single-operator, pair-only and pair-removal runs, "
            "named only_*/pair_*/minus_*)",
            SCRIPTS["pairdiag"],
            runs.root,
        )
    benchmarks = _benchmark_columns(runs, LOO_BENCHMARKS, "pairdiag")
    cells = _lookup(point_estimates(frame, ["variant", "benchmark"]), ["variant", "benchmark"])

    records, body = [], []
    previous: str | None = None
    for variant in variants:
        block = "removal" if variant.startswith("minus_") else "subset"
        if previous is not None and block != previous:
            body.append(RULE)
        previous = block
        row = [_pretty_variant(variant)]
        for benchmark in benchmarks:
            value = cells.get((variant, benchmark), (None, None))[0]
            row.append(_fmt(value))
            records.append({"variant": variant, "benchmark": benchmark, "value": value})
        body.append(row)

    tex = _comment("pairdiag", ctx, runs)
    tex += "\n" + _tabular(
        "@{}l" + "c" * len(benchmarks) + "@{}",
        [["Configuration", *(benchmark_label(b) for b in benchmarks)]],
        body,
    )
    return _write(ctx, "pairdiag", pd.DataFrame(records), tex)


def build_equalcompute(ctx: Context) -> list[Path]:
    runs = ctx.runs
    frame = runs.frame()
    baselines = frame[frame["arm"] != "trope"]
    if baselines.empty:
        raise missing(
            "table `equalcompute` (baseline runs at the raised budget)",
            SCRIPTS["equalcompute"],
            runs.root,
        )
    trope_runs = runs.select(arm="trope")
    extra_note: list[str] = []
    if not trope_runs:
        sibling = runs.root.parent / "main"
        if sibling.exists():
            trope_runs = RunSet(sibling).select(arm="trope")
            extra_note.append(
                f"the TROPE column is read from {sibling}: the equal-compute root "
                f"holds baseline runs only"
            )
    trope_point = (
        _lookup(point_estimates(trope_runs.frame(), ["benchmark"]), ["benchmark"])
        if trope_runs
        else {}
    )
    if not trope_point:
        extra_note.append(
            "TROPE column empty: no TROPE runs under this root or under a sibling "
            "`main` root; produce them with scripts/run_main.sh"
        )
    base_point = _lookup(point_estimates(baselines, ["arm", "benchmark"]), ["arm", "benchmark"])
    budgets = {
        (run.arm, run.benchmark): run.budget
        for run in runs.runs
        if run.arm != "trope"
    }

    records, body = [], []
    for benchmark in ordered_benchmarks(sorted(baselines["benchmark"].unique())):
        for arm in sorted(baselines[baselines["benchmark"] == benchmark]["arm"].unique()):
            base = base_point.get((arm, benchmark), (None, None))[0]
            ours = trope_point.get((benchmark,), (None, None))[0]
            eff_k = budgets.get((arm, benchmark))
            base_cell, ours_cell = _fmt(base), _fmt(ours)
            if base is not None and ours is not None:
                if base > ours:
                    base_cell = _bold(base_cell)
                elif ours > base:
                    ours_cell = _bold(ours_cell)
            body.append(
                [
                    benchmark_label(benchmark),
                    _pretty_variant(arm),
                    UNMEASURED if eff_k is None else str(eff_k),
                    base_cell,
                    ours_cell,
                ]
            )
            records.append(
                {
                    "benchmark": benchmark,
                    "baseline": arm,
                    "effective_k": eff_k,
                    "baseline_value": base,
                    "trope_value": ours,
                }
            )

    tex = _comment(
        "equalcompute",
        ctx,
        runs,
        [
            "Eff. K is the run's own run.budget from manifest.json, set by "
            "scripts/run_equalcompute.sh from trope.analysis.equalcompute",
            *extra_note,
        ],
    )
    tex += "\n" + _tabular(
        "@{}llccc@{}",
        [["Bench.", "Baseline", r"Eff.\ $K$", "Base.", r"\TROPE{}"]],
        body,
    )
    return _write(ctx, "equalcompute", pd.DataFrame(records), tex)


def build_trace(ctx: Context) -> list[Path]:
    runs = ctx.runs.select(arm="trope")
    chosen: RunRecord | None = None
    steps: list[dict[str, Any]] = []
    for run in runs.runs:
        by_problem: dict[str, list[dict[str, Any]]] = {}
        for record in run.trace():
            if "iteration" not in record or record.get("verdict") is None:
                continue
            by_problem.setdefault(str(record.get("problem_id", "")), []).append(record)
        if by_problem:
            problem = sorted(by_problem, key=lambda p: (-len(by_problem[p]), p))[0]
            chosen, steps = run, by_problem[problem]
            break
    if chosen is None:
        raise missing(
            "table `trace` (a TROPE run whose trace.jsonl records generated candidates)",
            SCRIPTS["trace"],
            ctx.runs.root,
        )

    archive = chosen.archive_entries()
    problem_id = str(steps[0].get("problem_id", ""))
    records, body = [], []
    for step in steps:
        entry = archive.get((problem_id, int(step["iteration"]))) or {}
        candidate = step.get("answer") or entry.get("text") or entry.get("answer") or ""
        edit = step.get("detail") or ("none" if step.get("level") == "token" else "")
        verdict = step.get("verdict")
        verified = bool(step.get("verified"))
        body.append(
            [
                _tex_escape(str(edit)),
                _pretty_variant(str(step.get("operator") or "")),
                _tex_escape(_shorten(str(candidate))),
                r"\textbf{pass}" if verified else "fail",
                _fmt(step.get("novelty"), digits=2),
            ]
        )
        records.append(
            {
                "problem_id": problem_id,
                "iteration": step.get("iteration"),
                "edit": edit,
                "operator": step.get("operator"),
                "level": step.get("level"),
                "radicality": step.get("radicality"),
                "candidate": candidate,
                "verdict": verdict,
                "verified": verified,
                "novelty": step.get("novelty"),
                "accepted": step.get("accepted"),
            }
        )

    note = [f"problem {problem_id} from {chosen.path}"]
    if not any(r["candidate"] for r in records):
        note.append(
            "the Cand. column is empty: neither trace.jsonl's `answer` field nor "
            "this run's results.json archive dump carries candidate text"
        )
    tex = _comment("trace", ctx, RunSet(ctx.runs.root, [chosen]), note)
    tex += "\n" + _tabular(
        "@{}llccr@{}",
        [[r"Edit to $R$", "Operator", "Cand.", r"$\VerP$", r"$\Nov$"]],
        body,
    )
    return _write(ctx, "trace", pd.DataFrame(records), tex)


def _shorten(text: str, limit: int = 28) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _tex_escape(text: str) -> str:
    for char in ("\\", "&", "%", "$", "#", "_", "{", "}"):
        text = text.replace(char, "\\" + char)
    return text


def build_band(ctx: Context) -> list[Path]:
    runs = ctx.runs.select(arm="trope")
    if not runs:
        raise missing("table `band` (TROPE traces)", SCRIPTS["band"], ctx.runs.root)

    stats: dict[str, dict[str, float]] = {}
    total = {"in_band": 0.0, "n": 0.0, "lambda": 0.0, "steady_in": 0.0, "steady_n": 0.0}
    warmups: set[int] = set()
    for run in runs.runs:
        controller = (run.config.get("controller") or {})
        lo = float(controller.get("lambda_min", 0.05))
        hi = float(controller.get("lambda_max", 0.40))
        warm = int(controller.get("window", 8))
        warmups.add(warm)
        family = benchmark_family(run.benchmark)
        cell = stats.setdefault(
            family, {"in_band": 0.0, "n": 0.0, "lambda": 0.0, "steady_in": 0.0, "steady_n": 0.0}
        )
        for record in run.trace():
            value = record.get("lambda_struct")
            if value is None:
                continue
            value = float(value)
            inside = float(lo <= value <= hi)
            for target in (cell, total):
                target["n"] += 1
                target["in_band"] += inside
                target["lambda"] += value
            if int(record.get("iteration", 0)) > warm:
                for target in (cell, total):
                    target["steady_n"] += 1
                    target["steady_in"] += inside

    if not total["n"]:
        raise missing(
            "table `band` (traces recording lambda_struct)", SCRIPTS["band"], ctx.runs.root
        )

    records, body = [], []
    for family in [f for f in FAMILIES if f in stats] + sorted(set(stats) - set(FAMILIES)):
        cell = stats[family]
        steady = 100.0 * cell["steady_in"] / cell["steady_n"] if cell["steady_n"] else None
        mean_lambda = cell["lambda"] / cell["n"] if cell["n"] else None
        body.append([family, _fmt(steady), _fmt(mean_lambda, digits=3)])
        records.append(
            {
                "family": family,
                "steady_occupancy_pct": steady,
                "overall_occupancy_pct": 100.0 * cell["in_band"] / cell["n"]
                if cell["n"]
                else None,
                "mean_lambda_struct": mean_lambda,
                "n_iterations": int(cell["n"]),
            }
        )
    body.append(RULE)
    overall = 100.0 * total["in_band"] / total["n"]
    body.append(
        [r"All ($+$warm-up)", _fmt(overall), _fmt(total["lambda"] / total["n"], digits=3)]
    )
    records.append(
        {
            "family": "all",
            "steady_occupancy_pct": 100.0 * total["steady_in"] / total["steady_n"]
            if total["steady_n"]
            else None,
            "overall_occupancy_pct": overall,
            "mean_lambda_struct": total["lambda"] / total["n"],
            "n_iterations": int(total["n"]),
        }
    )

    tex = _comment(
        "band",
        ctx,
        runs,
        [
            f"band is [controller.lambda_min, lambda_max] from each run's config; "
            f"warm-up W = {sorted(warmups)} iterations, excluded from the steady column",
        ],
    )
    tex += "\n" + _tabular(
        "@{}lcc@{}",
        [["Task family", r"Steady occ.\ (\%)", r"$\bar\lambda_{\mathrm{struct}}$"]],
        body,
    )
    return _write(ctx, "band", pd.DataFrame(records), tex)


def build_cost(ctx: Context) -> list[Path]:
    """Cost (`tab:cost`) and per-benchmark overhead (`tab:overhead`)."""
    written = _cost_table(ctx)
    try:
        written += _overhead_table(ctx)
    except MissingRuns as exc:
        print(f"skipped overhead: {exc}")
    return written


def _cost_rows(runs: RunSet) -> dict[str, dict[str, Any]]:
    """Per-arm cost aggregates, keyed by arm."""
    out: dict[str, dict[str, list[float]]] = {}
    for run in runs.runs:
        n = run.n_problems
        if not n:
            continue
        cell = out.setdefault(run.arm, {"gpu": [], "wall": [], "mem": []})
        hours = _manifest_number(run, GPU_HOURS_KEYS)
        if hours is not None:
            cell["gpu"].append(100.0 * hours / n)
        memory = _manifest_number(run, PEAK_MEMORY_KEYS)
        if memory is not None:
            cell["mem"].append(memory)
        walls = [r["wall_seconds"] for r in run.rows() if r.get("wall_seconds") is not None]
        if walls:
            cell["wall"].append(sum(walls) / len(walls))
    return {
        arm: {k: (sum(v) / len(v) if v else None) for k, v in cell.items()}
        for arm, cell in out.items()
    }


def _cost_table(ctx: Context) -> list[Path]:
    runs = ctx.runs
    aggregates = _cost_rows(runs)
    arms = [a for a, _ in BASELINE_ORDER if a in aggregates]
    arms += sorted(set(aggregates) - {a for a, _ in BASELINE_ORDER} - {"trope"})
    labels = dict(BASELINE_ORDER)

    records, body = [], []
    for arm in arms:
        cell = aggregates[arm]
        body.append(
            [
                labels.get(arm, _pretty_variant(arm)),
                _fmt(cell["gpu"], digits=2),
                _fmt(cell["wall"]),
                _fmt(cell["mem"]),
            ]
        )
        records.append({"row": arm, "stage": None, **_cost_record(cell)})

    if "trope" in aggregates:
        body.append(RULE)
        cell = aggregates["trope"]
        body.append(
            [
                r"\textsc{Trope}",
                _fmt(cell["gpu"], digits=2),
                _fmt(cell["wall"]),
                _fmt(cell["mem"]),
            ]
        )
        records.append({"row": "trope", "stage": None, **_cost_record(cell)})
        ledger = _ledger_totals(runs.select(arm="trope"))
        timings = _stage_timings(runs.select(arm="trope"))
        for label, roles, key in COST_STAGES:
            body.append(
                [
                    label,
                    _fmt(timings.get(key, {}).get("gpu_hours_per_100"), digits=2),
                    _fmt(timings.get(key, {}).get("wall_seconds")),
                    UNMEASURED,
                ]
            )
            records.append(
                {
                    "row": "trope",
                    "stage": key,
                    "gpu_hours_per_100": timings.get(key, {}).get("gpu_hours_per_100"),
                    "wall_seconds_per_problem": timings.get(key, {}).get("wall_seconds"),
                    "peak_memory_gb": None,
                    "calls_per_problem": sum(
                        ledger["calls"].get(r, 0.0) for r in roles
                    )
                    or None,
                    "tokens_per_problem": sum(
                        ledger["tokens"].get(r, 0.0) for r in roles
                    )
                    or None,
                }
            )

    if not records:
        raise missing("table `cost`", SCRIPTS["cost"], runs.root)

    tex = _comment(
        "cost",
        ctx,
        runs,
        [
            "GPU-h/100 and Mem. are empty unless the run recorded them in "
            f"manifest.json (keys: {', '.join(GPU_HOURS_KEYS + PEAK_MEMORY_KEYS)})",
            "wall seconds per problem come from results.json stats['wall_seconds']; "
            "baselines do not record it",
            "per-stage rows are empty unless a run recorded stats['timings']; the CSV "
            "carries the per-stage calls and tokens from ledger.json, which every run "
            "does record",
        ],
    )
    tex += "\n" + _tabular(
        "@{}lccc@{}",
        [["Method", "GPU-h/100", "Wall (s)", r"Mem.\ (GB)"]],
        body,
    )
    return _write(ctx, "cost", pd.DataFrame(records), tex)


def _cost_record(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "gpu_hours_per_100": cell["gpu"],
        "wall_seconds_per_problem": cell["wall"],
        "peak_memory_gb": cell["mem"],
        "calls_per_problem": None,
        "tokens_per_problem": None,
    }


def _ledger_totals(runs: RunSet) -> dict[str, dict[str, float]]:
    """Calls and tokens per problem, averaged over runs, by role."""
    calls: dict[str, list[float]] = {}
    tokens: dict[str, list[float]] = {}
    for run in runs.runs:
        n = run.n_problems
        if not n:
            continue
        for role, value in (run.ledger.get("calls") or {}).items():
            calls.setdefault(role, []).append(value / n)
        for role, value in (run.ledger.get("tokens") or {}).items():
            tokens.setdefault(role, []).append(value / n)
    return {
        "calls": {k: sum(v) / len(v) for k, v in calls.items()},
        "tokens": {k: sum(v) / len(v) for k, v in tokens.items()},
    }


def _stage_timings(runs: RunSet) -> dict[str, dict[str, float]]:
    """Per-stage wall time, if a run recorded stats['timings']."""
    collected: dict[str, list[float]] = {}
    for run in runs.runs:
        for result in run.results:
            timings = (result.get("stats") or {}).get("timings") or {}
            for stage, seconds in timings.items():
                if isinstance(seconds, int | float):
                    collected.setdefault(str(stage), []).append(float(seconds))
    return {
        stage: {"wall_seconds": sum(v) / len(v), "gpu_hours_per_100": None}
        for stage, v in collected.items()
    }


def _overhead_table(ctx: Context) -> list[Path]:
    runs = ctx.runs.select(arm="trope")
    if not runs:
        raise missing("table `overhead` (TROPE runs)", SCRIPTS["cost"], ctx.runs.root)

    records, body = [], []
    for benchmark in runs.benchmarks():
        subset = runs.select(benchmark=benchmark)
        ledger = _ledger_totals(subset)
        memory = [
            m
            for m in (_manifest_number(r, PEAK_MEMORY_KEYS) for r in subset.runs)
            if m is not None
        ]
        parser = ledger["calls"].get("parser")
        lmref = sum(ledger["calls"].get(role, 0.0) for role in REFERENCE_ROLES) or None
        scored = sum(ledger["tokens"].get(role, 0.0) for role in REFERENCE_ROLES) or None
        body.append(
            [
                benchmark_label(benchmark),
                _fmt(parser, digits=0),
                _fmt(lmref, digits=0),
                _fmt(None if scored is None else scored / 1e6, digits=1),
                UNMEASURED,
                _fmt(sum(memory) / len(memory) if memory else None),
            ]
        )
        records.append(
            {
                "benchmark": benchmark,
                "parser_calls_per_problem": parser,
                "lmref_passes_per_problem": lmref,
                "scored_tokens_millions_per_problem": None
                if scored is None
                else scored / 1e6,
                "parse_plus_distance_gpu_hours_per_100": None,
                "peak_memory_gb": sum(memory) / len(memory) if memory else None,
            }
        )

    tex = _comment(
        "overhead",
        ctx,
        runs,
        [
            "parser calls and LMref passes are ledger.json call counts divided by the "
            "number of problems in the run",
            "Parse+dist. is empty: it is a GPU-hour figure, and no run recorded "
            "per-stage GPU time",
        ],
    )
    tex += "\n" + _tabular(
        "@{}lccccc@{}",
        [
            ["Benchmark", "Parser", r"$\LMref$", "Tok.", "Parse$+$", "Peak"],
            [" ", "calls", "passes", "(M)", "dist.", "GB"],
        ],
        body,
    )
    return _write(ctx, "overhead", pd.DataFrame(records), tex)


def build_usage(ctx: Context) -> list[Path]:
    runs = ctx.runs.select(arm="trope")
    if not runs:
        raise missing("table `usage` (TROPE runs)", SCRIPTS["usage"], ctx.runs.root)

    kinds = operator_kinds()
    per_family: dict[str, dict[str, float]] = {}
    for run in runs.runs:
        family = benchmark_family(run.benchmark)
        cell = per_family.setdefault(
            family,
            {"token": 0.0, "mutation": 0.0, "crossover": 0.0, "rejections": 0.0, "draws": 0.0},
        )
        usage = usage_counts(run, kinds)
        for level in ("token", "mutation", "crossover"):
            cell[level] += usage[level]
        for record in run.trace():
            if "iteration" not in record:
                continue
            if record.get("rejections") is not None:
                cell["rejections"] += float(record["rejections"])
                cell["draws"] += 1.0

    if not any(sum(c[k] for k in ("token", "mutation", "crossover")) for c in per_family.values()):
        raise missing(
            "table `usage` (runs recording operator selections)",
            SCRIPTS["usage"],
            ctx.runs.root,
        )

    records, body = [], []
    for family in [f for f in FAMILIES if f in per_family] + sorted(
        set(per_family) - set(FAMILIES)
    ):
        cell = per_family[family]
        total = sum(cell[k] for k in ("token", "mutation", "crossover"))
        shares = {
            k: (100.0 * cell[k] / total if total else None)
            for k in ("token", "mutation", "crossover")
        }
        attempts = cell["rejections"] + cell["draws"]
        rejected = 100.0 * cell["rejections"] / attempts if attempts else None
        body.append(
            [
                family,
                _fmt(shares["token"]),
                _fmt(shares["mutation"]),
                _fmt(shares["crossover"]),
                _fmt(rejected),
            ]
        )
        records.append(
            {
                "family": family,
                "token_pct": shares["token"],
                "mutation_pct": shares["mutation"],
                "crossover_pct": shares["crossover"],
                "rejection_pct": rejected,
                "n_selections": int(total),
                "n_draws": int(cell["draws"]),
            }
        )

    tex = _comment(
        "usage",
        ctx,
        runs,
        [
            "level shares from trope.search.level_usage over results.json stats['usage'], "
            "falling back to the trace `level` field",
            "rejection % = rejected draws / (rejected + accepted draws), from the trace "
            "`rejections` field",
        ],
    )
    tex += "\n" + _tabular(
        "@{}lcccc@{}",
        [["Family", r"$\Otok$ \%", r"$\Omut$ \%", r"$\Ocross$ \%", r"rej.\ \%"]],
        body,
    )
    return _write(ctx, "usage", pd.DataFrame(records), tex)


def usage_counts(run: RunRecord, kinds: dict[str, str]) -> dict[str, float]:
    """Selections per operator level for one run."""
    merged: dict[str, int] = {}
    for result in run.results:
        for name, count in ((result.get("stats") or {}).get("usage") or {}).items():
            merged[name] = merged.get(name, 0) + int(count)
    if merged:
        try:
            from trope.operators.base import catalog
            from trope.search import level_usage

            shares = level_usage({"usage": merged}, catalog())
            total = sum(merged.values())
            return {k: total * v / 100.0 for k, v in shares.items()}
        except Exception:
            out = {"token": 0.0, "mutation": 0.0, "crossover": 0.0}
            for name, count in merged.items():
                out[kinds.get(name, "token")] += count
            return out
    out = {"token": 0.0, "mutation": 0.0, "crossover": 0.0}
    for record in run.trace():
        level = record.get("level")
        if "iteration" in record and level in out and record.get("changed"):
            out[level] += 1.0
    return out


def build_alpha(ctx: Context) -> list[Path]:
    runs = ctx.runs.select(group="alpha")
    if not runs:
        raise missing(
            "table `alpha` (tail-index sweep under <root>/alpha/<value>)",
            SCRIPTS["alpha"],
            ctx.runs.root,
        )
    frame = runs.frame()
    benchmarks = _benchmark_columns(runs, ALPHA_BENCHMARKS, "alpha")
    cells = _lookup(point_estimates(frame, ["variant", "benchmark"]), ["variant", "benchmark"])
    variants = sorted(set(frame["variant"]), key=_as_float)

    records, body = [], []
    best = {
        b: max((cells[(v, b)][0] for v in variants if (v, b) in cells), default=None)
        for b in benchmarks
    }
    for variant in variants:
        row = [variant]
        for benchmark in benchmarks:
            value = cells.get((variant, benchmark), (None, None))[0]
            cell = _fmt(value)
            if value is not None and best[benchmark] is not None and value >= best[benchmark]:
                cell = _bold(cell)
            row.append(cell)
            records.append({"alpha": variant, "benchmark": benchmark, "value": value})
        body.append(row)

    tex = _comment("alpha", ctx, runs)
    tex += "\n" + _tabular(
        "@{}l" + "c" * len(benchmarks) + "@{}",
        [[r"$\alpha^{*}$", *(benchmark_label(b) for b in benchmarks)]],
        body,
    )
    return _write(ctx, "alpha", pd.DataFrame(records), tex)


def _as_float(value: str) -> tuple[int, float, str]:
    try:
        return (0, float(value), "")
    except ValueError:
        return (1, 0.0, value)


def build_lmref(ctx: Context) -> list[Path]:
    runs = ctx.runs.select(group="lmref")
    if not runs:
        raise missing(
            "table `lmref` (reference-LM sweep under <root>/lmref/<checkpoint>)",
            SCRIPTS["lmref"],
            ctx.runs.root,
        )
    frame = runs.frame()
    cells = _lookup(point_estimates(frame, ["variant", "benchmark"]), ["variant", "benchmark"])
    variants = sorted(set(frame["variant"]))
    default = _default_reference(runs, variants)
    benchmarks = _benchmark_columns(runs, CROSSFAMILY_BENCHMARKS, "lmref")
    rho = _spearman_vs_default(frame, variants, benchmarks, default)

    records, body = [], []
    for variant in variants:
        label = _pretty_variant(variant) + (" (default)" if variant == default else "")
        row = [label]
        for benchmark in benchmarks:
            value = cells.get((variant, benchmark), (None, None))[0]
            row.append(_fmt(value))
            records.append(
                {
                    "table": "crossfamily",
                    "reference_lm": variant,
                    "benchmark": benchmark,
                    "value": value,
                    "spearman_rho": rho.get((variant, benchmark)),
                }
            )
        body.append(row)
    body.append(RULE)
    worst = {
        b: min(
            (
                rho[(v, b)]
                for v in variants
                if v != default and rho.get((v, b)) is not None
            ),
            default=None,
        )
        for b in benchmarks
    }
    body.append([r"Spearman $\rho$", *(_fmt(worst[b], digits=2) for b in benchmarks)])
    for benchmark in benchmarks:
        records.append(
            {
                "table": "crossfamily",
                "reference_lm": "min over non-default",
                "benchmark": benchmark,
                "value": None,
                "spearman_rho": worst[benchmark],
            }
        )

    note = [
        f"default reference LM: {default}",
        "Spearman rho is the rank correlation of per-problem seed-averaged scores "
        "against the default reference LM, computed with scipy.stats.spearmanr; the "
        "paper's per-solution rankings are not recoverable from run artifacts",
        "the Spearman row reports the minimum over the non-default reference LMs, "
        "which is the quantity the paper's `rho >= 0.93` claim bounds",
    ]
    tex = _comment("crossfamily", ctx, runs, note)
    tex += "\n" + _tabular(
        "@{}l" + "c" * len(benchmarks) + "@{}",
        [[r"$\LMref$", *(benchmark_label(b) for b in benchmarks)]],
        body,
    )
    written = _write(ctx, "crossfamily", pd.DataFrame(records), tex)

    headline = benchmarks[0]
    size_records, size_body = [], []
    for variant in variants:
        value = cells.get((variant, headline), (None, None))[0]
        size_body.append(
            [
                _pretty_variant(variant) + (" (default)" if variant == default else ""),
                _fmt(rho.get((variant, headline)), digits=2),
                _fmt(value),
            ]
        )
        size_records.append(
            {
                "table": "lmrefsize",
                "reference_lm": variant,
                "spearman_rho": rho.get((variant, headline)),
                "benchmark": headline,
                "value": value,
            }
        )
    size_tex = _comment(
        "lmrefsize",
        ctx,
        runs,
        [
            *note,
            "the row label is the checkpoint the run used; parameter counts are not "
            "recorded in run artifacts, so the paper's size column is not reproduced",
        ],
    )
    size_tex += "\n" + _tabular(
        "@{}lcc@{}",
        [[r"$\LMref$", r"Spearman $\rho$", benchmark_label(headline)]],
        size_body,
    )
    return written + _write(ctx, "lmrefsize", pd.DataFrame(size_records), size_tex)


def _default_reference(runs: RunSet, variants: Sequence[str]) -> str:
    """The repository default reference LM, if it is one of the swept variants."""
    from trope.config import RunConfig

    slug = str(RunConfig().reference_model).replace("/", "_")
    if slug in variants:
        return slug
    for run in runs.runs:
        configured = (run.config.get("run") or {}).get("reference_model")
        if configured and str(configured).replace("/", "_") in variants:
            return str(configured).replace("/", "_")
    return variants[0]


def _spearman_vs_default(
    frame: pd.DataFrame,
    variants: Sequence[str],
    benchmarks: Sequence[str],
    default: str,
) -> dict[tuple[str, str], float | None]:
    """Rank correlation of per-problem scores against the default reference LM."""
    from scipy.stats import spearmanr

    scores = frame.groupby(["variant", "benchmark", "problem_id"], dropna=False)[
        "score"
    ].mean()
    out: dict[tuple[str, str], float | None] = {}
    for benchmark in benchmarks:
        try:
            reference = scores.loc[default, benchmark]
        except KeyError:
            out.update({(v, benchmark): None for v in variants})
            continue
        for variant in variants:
            try:
                other = scores.loc[variant, benchmark]
            except KeyError:
                out[(variant, benchmark)] = None
                continue
            shared = reference.index.intersection(other.index)
            a = reference.loc[shared].to_numpy()
            b = other.loc[shared].to_numpy()
            if a.size < 2 or np.allclose(a, a[0]) or np.allclose(b, b[0]):
                out[(variant, benchmark)] = 1.0 if np.array_equal(a, b) else None
            else:
                out[(variant, benchmark)] = float(spearmanr(a, b).statistic)
    return out


def build_budget(ctx: Context) -> list[Path]:
    runs = ctx.runs.select(group="budget")
    if not runs:
        raise missing(
            "table `budget` (sample-budget sweep under <root>/budget/<K>)",
            SCRIPTS["budget"],
            ctx.runs.root,
        )
    frame = runs.frame()
    trope = _lookup(point_estimates(frame[frame["arm"] == "trope"], ["variant"]), ["variant"])
    baselines = frame[frame["arm"] != "trope"]
    base_point = (
        _lookup(point_estimates(baselines, ["variant", "arm"]), ["variant", "arm"])
        if not baselines.empty
        else {}
    )
    default_budget = {run.variant: run.budget for run in runs.runs}

    records, body = [], []
    for variant in sorted(set(frame["variant"]), key=_as_float):
        best, best_arm = None, None
        for (v, arm), (value, _) in base_point.items():
            if v == variant and (best is None or value > best):
                best, best_arm = value, arm
        ours = trope.get((variant,), (None, None))[0]
        label = variant + (" (default)" if default_budget.get(variant) == 64 else "")
        body.append([label, _fmt(ours), _fmt(best)])
        records.append(
            {
                "K": variant,
                "trope": ours,
                "best_baseline": best,
                "best_baseline_arm": best_arm,
            }
        )

    note = []
    if not base_point:
        note.append(
            "the `Best baseline` column is empty: scripts/run_sensitivity.sh sweeps K "
            "for TROPE only. Produce the baseline arms at each K with "
            "`trope baseline --set run.budget=<K>` under the same root."
        )
    tex = _comment("budget", ctx, runs, note)
    tex += "\n" + _tabular(
        "@{}lcc@{}", [["$K$", r"\TROPE{}", "Best baseline"]], body
    )
    return _write(ctx, "budget", pd.DataFrame(records), tex)


def build_commute(ctx: Context) -> list[Path]:
    root = ctx.runs.root
    candidates = [root / "commutativity.json", *sorted(root.rglob("commutativity.json"))]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise missing("table `commute`", SCRIPTS["commute"], root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    rates = payload.get("rates") or {}
    counts = payload.get("counts") or {}
    columns = ("mut-mut", "mut-cross", "cross-cross")
    if not any(c in rates for c in columns):
        raise missing("table `commute`", SCRIPTS["commute"], root)

    body = [
        [
            r"Commute rate (\%)",
            *(_fmt(rates.get(c), digits=0) for c in columns),
        ]
    ]
    token = payload.get("token") or {}
    if token:
        body.append(
            [
                "Token pairs (never edit $R$)",
                *([_fmt(100.0, digits=0)] * len(columns)),
            ]
        )
    records = [
        {
            "pair_kind": column,
            "commute_rate_pct": rates.get(column),
            "n_pairs": counts.get(column),
        }
        for column in columns
    ]
    if token:
        records.append(
            {
                "pair_kind": "token-any",
                "commute_rate_pct": 100.0,
                "n_pairs": token.get("n_pairs"),
            }
        )

    tex = _comment(
        "commute",
        ctx,
        RunSet(root, []),
        [
            f"source: {path}",
            f"probe representations: {payload.get('n_representations')}, "
            f"seed {payload.get('seed')}",
            "token operators are reported as a separate row: they never modify R, so "
            "they commute by construction and are not folded into the rates",
        ],
    )
    tex += "\n" + _tabular(
        "@{}lccc@{}",
        [
            [
                "Operator pair",
                r"mut$\circ$mut",
                r"mut$\circ$cross",
                r"cross$\circ$cross",
            ]
        ],
        body,
    )
    return _write(ctx, "commute", pd.DataFrame(records), tex)


def build_audit(ctx: Context) -> list[Path]:
    from trope.analysis.audit import sample_semantic_audit

    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    written = [sample_semantic_audit(ctx.runs.root, ctx.out_dir / "semantic_audit.csv")]
    ctx.notes.append(
        "retrieval audit: run trope.analysis.audit.sample_retrieval_audit against the "
        "evidence corpus; it is not a run artifact, so `tables --which audit` cannot "
        "reach it."
    )
    return written


BUILDERS: dict[str, Callable[[Context], list[Path]]] = {
    "main": build_main,
    "fullse": build_fullse,
    "decomposition": build_decomposition,
    "ablation": build_ablation,
    "component": build_component,
    "loo": build_loo,
    "pairdiag": build_pairdiag,
    "equalcompute": build_equalcompute,
    "trace": build_trace,
    "band": build_band,
    "cost": build_cost,
    "usage": build_usage,
    "alpha": build_alpha,
    "lmref": build_lmref,
    "budget": build_budget,
    "commute": build_commute,
    "audit": build_audit,
}


def expand(which: str) -> list[str]:
    names: list[str] = []
    for token in str(which).split(","):
        token = token.strip()
        if not token:
            continue
        if token == "all":
            names += list(BUILDERS)
        elif token in GROUPS:
            names += list(GROUPS[token])
        elif token in BUILDERS:
            names.append(token)
        else:
            raise KeyError(
                f"unknown table {token!r}; choose from "
                f"{', '.join([*BUILDERS, *GROUPS, 'all'])}"
            )
    out: list[str] = []
    for name in names:
        if name not in out:
            out.append(name)
    return out


def build_tables(
    runs_root: str | Path,
    out_dir: str | Path,
    which: str = "all",
    *,
    budget_tolerance: float = 0.02,
) -> list[Path]:
    """Build the requested tables, or raise naming the script that is missing."""
    names = expand(which)
    runs = RunSet(runs_root)
    if not runs:
        raise missing(
            "any table (no run directories with a manifest.json)",
            "the launch scripts in README.md",
            runs_root,
        )

    if any(name in COMPARISON for name in names):
        complaints = runs.budget_check(budget_tolerance)
        if complaints:
            message = "\n".join(
                [
                    "matched-budget check FAILED; refusing to build a comparison table:",
                    *(f"  - {c}" for c in complaints),
                    "Re-run the offending arms at the same run.budget, or build only "
                    "the non-comparison tables.",
                ]
            )
            print(message)
            raise BudgetMismatch(message)

    ctx = Context(runs=runs, out_dir=Path(out_dir), notes=[])
    written: list[Path] = []
    failures: list[str] = []
    explicit = which.strip() != "all"
    for name in names:
        try:
            written += BUILDERS[name](ctx)
        except MissingRuns as exc:
            if explicit:
                raise
            failures.append(f"{name}: {exc}")
    for line in failures:
        print(f"skipped {line}")
    for note in ctx.notes:
        print(f"note: {note}")
    if not written:
        raise missing(
            f"any of the requested tables ({', '.join(names)})",
            "the launch scripts in README.md",
            runs_root,
        )
    return written
