"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from trope.config import SEEDS, Config


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trope", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run TROPE on a benchmark")
    _common(run)
    run.add_argument("--out", default=None)

    base = sub.add_parser("baseline", help="run one baseline on a benchmark")
    _common(base)
    base.add_argument("--name", required=True)
    base.add_argument("--out", default=None)

    cal = sub.add_parser("calibrate", help="fit the radicality distribution")
    _common(cal)
    cal.add_argument("--n", type=int, default=1000, help="number of distances to collect")
    cal.add_argument("--out", default="runs/calibration.json")

    null = sub.add_parser(
        "nullcheck", help="probe the novelty bound with random-token prefixes"
    )
    _common(null)
    null.add_argument("--samples", type=int, default=200)
    null.add_argument("--out", default="runs/nullcheck.json")

    tables = sub.add_parser("tables", help="build tables from run artifacts")
    tables.add_argument("--runs", default="runs")
    tables.add_argument("--out", default="tables")
    tables.add_argument("--which", default="all")

    figures = sub.add_parser("figures", help="build figures from run artifacts")
    figures.add_argument("--runs", default="runs")
    figures.add_argument("--out", default="figures")

    sub.add_parser("info", help="print the operator catalog and environment")

    args = parser.parse_args(argv)
    handler = {
        "run": _cmd_run,
        "baseline": _cmd_baseline,
        "calibrate": _cmd_calibrate,
        "nullcheck": _cmd_nullcheck,
        "tables": _cmd_tables,
        "figures": _cmd_figures,
        "info": _cmd_info,
    }[args.command]
    return handler(args)


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default="configs/smoke.yaml")
    p.add_argument("--benchmark", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--seeds", default=None, help="comma-separated, overrides --seed")
    p.add_argument("--limit", type=int, default=None, help="first N problems only")
    p.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="dotted config override, e.g. --set sampling.alpha=1.4",
    )


def _load(args: argparse.Namespace) -> tuple[Config, Any]:
    from trope.data.base import load

    cfg = Config.load(args.config, overrides=_overrides(args))
    dataset = load(cfg.run.benchmark).subset(cfg.run.max_problems)
    return cfg, dataset


def _overrides(args: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in getattr(args, "set", []) or []:
        key, _, raw = item.partition("=")
        if not raw:
            raise SystemExit(f"--set expects KEY=VALUE, got {item!r}")
        out[key.strip()] = _coerce(raw.strip())
    if getattr(args, "benchmark", None):
        out["run.benchmark"] = args.benchmark
    if getattr(args, "seed", None) is not None:
        out["run.seed"] = args.seed
    if getattr(args, "limit", None) is not None:
        out["run.max_problems"] = args.limit
    return out


def _coerce(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _seed_list(args: argparse.Namespace, cfg: Config) -> list[int]:
    if getattr(args, "seeds", None):
        return [int(s) for s in str(args.seeds).split(",") if s.strip()]
    if getattr(args, "seed", None) is not None:
        return [int(args.seed)]
    return [cfg.run.seed]


def _cmd_run(args: argparse.Namespace) -> int:
    from trope.pipeline import Pipeline, summarise

    cfg, dataset = _load(args)
    for seed in _seed_list(args, cfg):
        pipeline = Pipeline.build(cfg, problems=dataset)
        out = Path(args.out) / f"seed{seed}" if args.out else None
        results = pipeline.run(dataset, seed=seed, out_dir=out)
        summary = summarise(results, len(dataset))
        print(f"seed {seed}: " + json.dumps(summary, sort_keys=True))
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    from trope.backends.base import CallCounter, MeteredBackend
    from trope.backends.registry import make_backend
    from trope.baselines.registry import get_baseline
    from trope.rng import RngTree
    from trope.runlog import RunLog
    from trope.verify.base import get_verifier

    cfg, dataset = _load(args)
    fn = get_baseline(args.name)
    for seed in _seed_list(args, cfg):
        root = (
            Path(args.out) / f"seed{seed}"
            if args.out
            else Path(cfg.run.out_dir) / f"{cfg.run.benchmark}-{args.name}-seed{seed}"
        )
        totals = CallCounter()
        solved = 0
        with RunLog.open(
            root,
            config=cfg.resolved(),
            backend=cfg.run.backend,
            models={"backbone": cfg.run.backend_model},
            extra={"baseline": args.name, "seed": seed},
        ) as log:
            records = []
            for problem in dataset:
                counter = CallCounter()
                raw = make_backend(
                    cfg.run.backend, model=cfg.run.backend_model, problems=dataset
                )
                backend = MeteredBackend(raw, counter, budget=cfg.run.budget)
                verifier = get_verifier(problem, backend=backend.for_role("judge"))
                result = fn(
                    problem,
                    backend,
                    verifier,
                    cfg.run.budget,
                    RngTree(seed).stream(f"baseline/{args.name}/{problem.id}"),
                )
                ok = any(c.get("verified") for c in result.candidates)
                solved += int(ok)
                records.append(
                    {
                        "problem_id": problem.id,
                        "verified": ok,
                        "generator_calls": result.generator_calls,
                    }
                )
                log.step(records[-1])
                for role, n in counter.counts.items():
                    totals.counts[role] = totals.counts.get(role, 0) + n
            log.write_json(
                "summary.json",
                {
                    "baseline": args.name,
                    "n_problems": len(dataset),
                    "solved": solved,
                    "solve_rate": solved / len(dataset) if len(dataset) else 0.0,
                },
            )
            log.ledger(totals)
        print(f"{args.name} seed {seed}: solved {solved}/{len(dataset)}")
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    from trope.calibrate import calibrate_dataset
    from trope.pipeline import Pipeline

    cfg, dataset = _load(args)
    pipeline = Pipeline.build(cfg, problems=dataset)
    report, counts = calibrate_dataset(
        dataset, pipeline, cfg, n=args.n, seed=cfg.run.seed
    )
    path = report.save(args.out)
    for line in report.summary_lines():
        print(line)
    print(f"-> {path}")
    print("collection: " + json.dumps(counts, sort_keys=True))
    return 0


def _cmd_nullcheck(args: argparse.Namespace) -> int:
    from trope.corpus import build_corpus, fallback_index
    from trope.novelty import null_check
    from trope.pipeline import Pipeline
    from trope.rng import RngTree

    cfg, dataset = _load(args)
    pipeline = Pipeline.build(cfg, problems=dataset)
    deps, _ = pipeline.deps_for(dataset[0])
    corpus = build_corpus(
        dataset[0],
        fallback_index(),
        top_k=cfg.novelty.corpus_passages,
    )
    table = null_check(
        deps.novelty.scorer,
        corpus,
        RngTree(cfg.run.seed).stream("nullcheck"),
        n=args.samples,
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(table, indent=2), encoding="utf-8")
    for length, row in sorted(table.items()):
        print(
            f"prefix {length:>4}: mean={row['mean']:+.4f} "
            f"CI=[{row['ci'][0]:+.4f},{row['ci'][1]:+.4f}] "
            f"P[Nov<=0]={row['p_nonpositive']:.3f}"
        )
    return 0


def _cmd_tables(args: argparse.Namespace) -> int:
    from trope.analysis.tables import build_tables

    written = build_tables(args.runs, args.out, which=args.which)
    for path in written:
        print(path)
    return 0 if written else 1


def _cmd_figures(args: argparse.Namespace) -> int:
    from trope.analysis.figures import build_figures

    written = build_figures(args.runs, args.out)
    for path in written:
        print(path)
    return 0 if written else 1


def _cmd_info(args: argparse.Namespace) -> int:
    import numpy as np

    from trope.data.base import available
    from trope.operators.base import catalog

    ops = catalog()
    print(f"trope, {len(ops)} operators")
    for kind in ("token", "mutation", "crossover"):
        names = [op.name for op in ops if op.kind == kind]
        print(f"  {kind:<10} {len(names)}  {', '.join(names)}")
    print(f"benchmarks: {', '.join(available())}")
    print(f"seeds: {', '.join(str(s) for s in SEEDS)}")
    print(f"python {sys.version.split()[0]}, numpy {np.__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
