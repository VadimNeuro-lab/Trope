"""Empirical operator commutativity (the commutativity table, `tab:commute`)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from itertools import permutations
from pathlib import Path
from typing import Any

from trope.isomorphism import compare
from trope.operators.base import CROSSOVER, TOKEN, Operator, Resources, well_formed
from trope.rng import RngTree
from trope.sampling.stable import sample_radicality
from trope.types import Representation

PAIR_KINDS = ("mut-mut", "mut-cross", "cross-cross")


def _pair_kind(a: Operator, b: Operator) -> str:
    kinds = sorted((a.kind, b.kind))
    if kinds == ["mutation", "mutation"]:
        return "mut-mut"
    if kinds == ["crossover", "mutation"]:
        return "mut-cross"
    return "cross-cross"


def _apply(
    op: Operator,
    rep: Representation,
    rho: float,
    tree: RngTree,
    resources: Resources,
    partner: Representation,
) -> Representation | None:
    other = partner if op.kind == CROSSOVER else None
    edit = op.apply(rep, rho, tree.fresh(f"op/{op.name}"), resources, other=other)
    if not edit.changed or edit.representation is None:
        return None
    ok, _ = well_formed(edit.representation)
    return edit.representation if ok else None


def commutativity_rates(
    representations: Sequence[Representation],
    operators: Sequence[Operator],
    resources: Resources,
    *,
    seed: int = 1,
    alpha: float = 1.6,
    gamma: float = 0.3,
) -> dict[str, Any]:
    """Commute rates over every ordered pair of structural operators."""
    structural = [op for op in operators if op.kind != TOKEN]
    tokens = [op for op in operators if op.kind == TOKEN]
    if len(structural) < 2 or not representations:
        raise ValueError("need at least two structural operators and one representation")

    agree = dict.fromkeys(PAIR_KINDS, 0)
    undecided = dict.fromkeys(PAIR_KINDS, 0)
    total = dict.fromkeys(PAIR_KINDS, 0)
    skipped = {"noop_or_malformed": 0}
    root = RngTree(seed)

    for index, rep in enumerate(representations):
        partner = representations[(index + 1) % len(representations)]
        draws = root.stream(f"rho/{index}")
        for first, second in permutations(structural, 2):
            kind = _pair_kind(first, second)
            rho = float(sample_radicality(draws, alpha, gamma))
            tree = root.derive(f"probe/{index}/{first.name}/{second.name}")
            slot = int(root.stream(f"operand/{index}/{first.name}/{second.name}").integers(2))
            a = _apply(first, rep, rho, tree, resources, partner)
            a = None if a is None else _apply(
                second, a, rho, tree, resources, (partner, a)[slot]
            )
            b = _apply(second, rep, rho, tree, resources, partner)
            b = None if b is None else _apply(
                first, b, rho, tree, resources, (partner, b)[slot]
            )
            if a is None or b is None:
                skipped["noop_or_malformed"] += 1
                continue
            total[kind] += 1
            verdict = compare(a, b)
            agree[kind] += int(verdict.isomorphic)
            undecided[kind] += int(verdict.undecided)

    return {
        "seed": seed,
        "alpha": alpha,
        "gamma": gamma,
        "n_representations": len(representations),
        "rates": {
            kind: (100.0 * agree[kind] / total[kind] if total[kind] else None)
            for kind in PAIR_KINDS
        },
        "agreements": dict(agree),
        "undecided": dict(undecided),
        "counts": dict(total),
        "skipped": skipped,
        "token": {
            "operators": [op.name for op in tokens],
            "n_pairs": 2 * len(tokens) * (len(structural) + len(tokens) - 1),
            "commute_rate_pct": 100.0,
            "note": (
                "token operators return a decoding override and never modify R, so "
                "every pair involving one commutes by construction; this line is not "
                "folded into the rates above"
            ),
        },
        "operators": {op.name: op.kind for op in operators},
        "notes": [
            "rate = fraction of (representation, ordered pair) trials whose two "
            "orders are structurally isomorphic",
            "matched radicality and per-operator RNG streams in both orders",
            "the second stage draws its operand from {partner, first stage's "
            "output}, as Algorithm 1's buffer would hold, with the slot shared "
            "between the two orders",
            "trials where either order no-opped or left a malformed representation "
            "are excluded, not scored as agreement",
            "the rates depend on the probe set: the paper's is 200 representations "
            "parsed from the ten benchmarks, and an offline probe over the "
            "synthetic dataset parses far smaller and more homogeneous "
            "representations, on which crossover has much less to bind to",
        ],
    }


def probe_representations(config: str | Path, n: int, seed: int) -> tuple[list, Any, Any]:
    """Parse a probe set with the configured pipeline."""
    from trope.config import Config
    from trope.data.base import load
    from trope.pipeline import Pipeline

    cfg = Config.load(config)
    dataset = load(cfg.run.benchmark).subset(max(n, cfg.run.max_problems or 0) or None)
    pipeline = Pipeline.build(cfg, problems=dataset)
    tree = RngTree(seed)
    reps: list[Representation] = []
    for problem in dataset:
        if len(reps) >= n:
            break
        deps, _ = pipeline.deps_for(problem)
        outcome = deps.parser.parse(problem, tree)
        if outcome.representation is not None:
            reps.append(outcome.representation)
    if not reps:
        raise RuntimeError(
            f"the parser produced no representations from {cfg.run.benchmark}; "
            f"cannot run the commutativity probe"
        )
    return reps, pipeline.operators, pipeline.resources


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m trope.analysis.commutativity",
        description=__doc__.split("\n")[0],
    )
    parser.add_argument("--config", default="configs/smoke.yaml")
    parser.add_argument("--probes", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default="runs/commutativity.json")
    args = parser.parse_args(argv)

    try:
        reps, operators, resources = probe_representations(
            args.config, args.probes, args.seed
        )
    except Exception as exc:
        print(f"commutativity: {exc}", file=sys.stderr)
        return 2

    payload = commutativity_rates(reps, operators, resources, seed=args.seed)
    payload["config"] = str(args.config)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    for kind in PAIR_KINDS:
        rate = payload["rates"][kind]
        print(
            f"{kind:<12} {'n/a' if rate is None else f'{rate:5.1f}%'} "
            f"over {payload['counts'][kind]} trials"
        )
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
