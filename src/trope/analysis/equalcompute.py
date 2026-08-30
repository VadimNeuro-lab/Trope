"""Effective K for the equal-compute control (`tab:equalcompute`)."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from trope.analysis.loader import MissingRuns, RunRecord, RunSet, missing

ROLE_MODEL: dict[str, str] = {
    "generator": "backbone",
    "generator_score": "backbone",
    "parser": "backbone",
    "judge": "backbone",
    "reference": "reference",
    "reference_score": "reference",
}
DEFAULT_MODEL = "backbone"

MAIN_SCRIPT = "scripts/run_main.sh"


def _weights(run: RunRecord) -> tuple[dict[str, float], bool]:
    """Parameter weights per model slot, and whether they came from the manifest."""
    params = run.manifest.get("model_params") or {}
    backbone = params.get(DEFAULT_MODEL)
    if not isinstance(backbone, int | float) or backbone <= 0:
        return {}, False
    return (
        {
            slot: float(value) / float(backbone)
            for slot, value in params.items()
            if isinstance(value, int | float) and value > 0
        },
        True,
    )


def total_compute(run: RunRecord) -> tuple[float, list[str]]:
    """Parameter-weighted tokens for one run, with the arithmetic as text."""
    weights, measured = _weights(run)
    tokens = run.ledger.get("tokens") or {}
    if not tokens:
        raise MissingRuns(
            f"{run.path}/ledger.json records no token counts, so total compute is "
            f"undefined. Re-run with a backend that reports token counts."
        )
    lines: list[str] = []
    total = 0.0
    for role in sorted(tokens):
        slot = ROLE_MODEL.get(role, DEFAULT_MODEL)
        weight = weights.get(slot, 1.0)
        contribution = float(tokens[role]) * weight
        total += contribution
        lines.append(
            f"    {role:<18} {int(tokens[role]):>12,} tokens x {weight:.4f} "
            f"({slot}) = {contribution:>14,.0f}"
        )
    lines.append(
        "    weights from manifest['model_params']"
        if measured
        else "    weights all 1.0: no model_params in the manifest, so C is raw tokens"
    )
    return total, lines


def _aggregate(runs: RunSet, label: str) -> tuple[float, int, int, list[str]]:
    """Total compute, problems and generator calls summed over a set of runs."""
    compute = 0.0
    problems = 0
    calls = 0
    lines: list[str] = []
    for run in runs.runs:
        run_compute, detail = total_compute(run)
        compute += run_compute
        problems += run.n_problems
        calls += run.calls("generator") or 0
        lines.append(f"  {label} run {run.path} (seed {run.seed}):")
        lines += detail
        lines.append(
            f"    C = {run_compute:,.0f} over {run.n_problems} problems, "
            f"{run.calls('generator')} generator calls"
        )
    return compute, problems, calls, lines


def effective_k(
    runs_root: str | Path, benchmark: str, baseline: str
) -> tuple[int, list[str]]:
    runs = RunSet(runs_root)
    if not runs:
        raise missing(
            f"the equal-compute budget for {benchmark}/{baseline}", MAIN_SCRIPT, runs_root
        )
    ours = runs.select(arm="trope", benchmark=benchmark)
    theirs = runs.select(arm=baseline, benchmark=benchmark)
    if not ours:
        raise missing(f"TROPE runs on {benchmark}", MAIN_SCRIPT, runs_root)
    if not theirs:
        raise missing(f"{baseline} runs on {benchmark}", MAIN_SCRIPT, runs_root)

    c_trope, n_problems, trope_calls, trope_lines = _aggregate(ours, "trope")
    c_base, _, base_calls, base_lines = _aggregate(theirs, baseline)
    if not n_problems:
        raise MissingRuns(f"TROPE runs on {benchmark} record no problems")
    if not base_calls:
        raise MissingRuns(
            f"{baseline} runs on {benchmark} record no generator calls in ledger.json"
        )
    per_problem = c_trope / n_problems
    per_call = c_base / base_calls
    if per_call <= 0:
        raise MissingRuns(
            f"{baseline} runs on {benchmark} report zero compute per generator call"
        )
    k = int(math.floor(per_problem / per_call))

    explain = [
        f"benchmark: {benchmark}   baseline: {baseline}   root: {Path(runs_root)}",
        "",
        "TROPE total compute:",
        *trope_lines,
        f"  C_trope = {c_trope:,.0f} over {n_problems} problems "
        f"({trope_calls} generator calls)",
        f"  C_trope per problem = {c_trope:,.0f} / {n_problems} = {per_problem:,.2f}",
        "",
        f"{baseline} total compute:",
        *base_lines,
        f"  C_baseline = {c_base:,.0f} over {base_calls} generator calls",
        f"  cost per generator call = {c_base:,.0f} / {base_calls} = {per_call:,.2f}",
        "",
        f"  eff_K = floor({per_problem:,.2f} / {per_call:,.2f}) = {k}",
    ]
    return k, explain


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m trope.analysis.equalcompute", description=__doc__.split("\n")[0]
    )
    parser.add_argument("--runs", required=True, help="root of the matched-budget runs")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument(
        "--explain", action="store_true", help="print the arithmetic to stderr"
    )
    args = parser.parse_args(argv)

    try:
        k, explain = effective_k(args.runs, args.benchmark, args.baseline)
    except MissingRuns as exc:
        print(f"equalcompute: {exc}", file=sys.stderr)
        return 2
    if args.explain:
        print("\n".join(explain), file=sys.stderr)
    print(k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
