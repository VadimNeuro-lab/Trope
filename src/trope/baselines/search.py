"""Search-shaped baselines: Tree of Thoughts and Verbalized Sampling."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from trope.baselines.common import (
    BaselineContext,
    BaselineResult,
    build_prompt,
    excerpt,
    generator_params,
    rounds,
    sample_candidates,
)
from trope.data.base import Problem
from trope.verify.exact_match import extract_answer, normalise_answer, parse_number

TOT_BREADTH = 5
TOT_DEPTH = 3

VS_PHRASINGS = 10

_WEIGHTED_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\(?\d{1,2}[.)]\s+)?(?:p\s*[=:]\s*)?"
    r"(\d*\.?\d+)\s*(%?)\s*[|:\u2013-]\s+(.{4,})$"
)


def value_score(text: str, *, scale: float = 10.0) -> float:
    """A backbone's 0-`scale` judgement, mapped to [0, 1]."""
    raw = extract_answer(text)
    value = parse_number(normalise_answer(raw)) if raw else None
    if value is None:
        return 0.5
    if 0.0 <= value <= scale:
        return value / scale
    return (abs(value) % (scale + 1.0)) / scale


def choice_index(text: str, n: int) -> int:
    """The option a backbone picked, as an index into `n` options."""
    if n <= 0:
        raise ValueError("no options to choose from")
    raw = extract_answer(text)
    value = parse_number(normalise_answer(raw)) if raw else None
    if value is None:
        return 0
    return int(abs(value)) % n


def tree_of_thoughts(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
    *,
    breadth: int = TOT_BREADTH,
    depth: int = TOT_DEPTH,
) -> BaselineResult:
    """Tree of Thoughts (Yao et al. 2023) at breadth 5, depth 3."""
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=budget,
        rng=rng,
        params=generator_params(),
    )
    trees = 0
    for tree in rounds(ctx):
        trees += 1
        path: list[str] = []
        for level in range(1, depth + 1):
            terminal = level == depth
            prompt = build_prompt(problem, _tot_guidance(path, level, depth, terminal))
            proposals = sample_candidates(
                ctx,
                [prompt] * breadth,
                iteration=tree,
                meta={"stage": "propose", "level": level, "terminal": terminal},
            )
            if not proposals:
                break
            values = []
            for step, proposal in enumerate(proposals):
                gen = ctx.ask(_value_prompt(problem, path, proposal["text"]))
                score = value_score(gen.text) if gen is not None else 0.5
                proposal["meta"]["value"] = score
                proposal["meta"]["valued"] = gen is not None
                values.append((score, -step, proposal))
            chosen = max(values)[2]
            chosen["meta"]["selected"] = True
            path.append(chosen["text"])
    return ctx.result(
        arm="tot",
        breadth=breadth,
        depth=depth,
        trees=trees,
        calls_per_tree=2 * breadth * depth,
        proposal_calls=sum(1 for c in ctx.candidates if c["meta"]["stage"] == "propose"),
        value_calls=ctx.calls - len(ctx.candidates),
    )


def _tot_guidance(path: Sequence[str], level: int, depth: int, terminal: bool) -> str:
    lines = [f"You are at step {level} of {depth} of a deliberate search."]
    if path:
        lines.append("Steps taken so far:")
        lines += [f"[{i + 1}] {excerpt(step)}" for i, step in enumerate(path)]
    if terminal:
        lines.append("This is the last step: finish the solution and state the answer.")
    else:
        lines.append(
            "Propose one next step only. Do not finish the solution yet, but say "
            "where the step leads."
        )
    return "\n".join(lines)


def _value_prompt(problem: Problem, path: Sequence[str], thought: str) -> str:
    context = "\n".join(f"[{i + 1}] {excerpt(step)}" for i, step in enumerate(path))
    guidance = [
        "Evaluate whether the partial reasoning below can still reach a correct "
        "solution of the problem.",
    ]
    if context:
        guidance += ["Steps already taken:", context]
    guidance += [
        "Step under evaluation:",
        excerpt(thought),
        "Answer with a single integer from 0 (dead end) to 10 (certain to "
        "succeed) in \\boxed{}, and nothing else.",
    ]
    return build_prompt(problem, "\n".join(guidance))


def verbalized_sampling(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
    *,
    phrasings: int = VS_PHRASINGS,
) -> BaselineResult:
    """Verbalized Sampling (Zhang et al. 2025): elicit a distribution, sample it."""
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=budget,
        rng=rng,
        params=generator_params(),
    )
    parsed_rounds = 0
    judged_rounds = 0
    total_rounds = 0
    for index in rounds(ctx):
        total_rounds = index
        gen = ctx.ask(build_prompt(problem, _vs_guidance(phrasings)))
        if gen is None:
            break
        items, parsed = parse_verbalized(gen.text, limit=phrasings)
        parsed_rounds += int(parsed)
        if not items:
            continue
        weights = np.array([w for w, _ in items], dtype=np.float64)
        weights = weights / weights.sum()
        draw = min(len(items), ctx.remaining)
        if draw <= 0:
            break
        picks = rng.choice(len(items), size=draw, replace=False, p=weights)
        produced = sample_candidates(
            ctx,
            [build_prompt(problem, f"Take this approach:\n{items[i][1]}") for i in picks],
            iteration=index,
            meta={"stage": "sample", "parsed": parsed},
        )
        for candidate, pick in zip(produced, picks, strict=False):
            candidate["meta"]["probability"] = float(weights[pick])
            candidate["meta"]["approach"] = items[pick][1]
        if len(produced) > 1 and ctx.remaining > 0:
            verdict = ctx.ask(_judge_prompt(problem, [c["text"] for c in produced]))
            if verdict is not None:
                judged_rounds += 1
                pick = choice_index(verdict.text, len(produced))
                produced[pick]["meta"]["judged"] = True
    return ctx.result(
        arm="verbalized_sampling",
        phrasings=phrasings,
        rounds=total_rounds,
        parsed_rounds=parsed_rounds,
        judged_rounds=judged_rounds,
        judge="backbone",
    )


def _vs_guidance(phrasings: int) -> str:
    return (
        f"Do not answer yet. First list {phrasings} distinct approaches you could "
        f"take to this problem, together with the probability you would use each. "
        f"One per line, in exactly this form:\n"
        f"0.15 | describe the approach in one sentence\n"
        f"The probabilities must sum to 1 and the approaches must be genuinely "
        f"different, not restatements of the most obvious one."
    )


def _judge_prompt(problem: Problem, texts: Sequence[str]) -> str:
    listing = "\n".join(f"[{i}] {excerpt(text)}" for i, text in enumerate(texts))
    return build_prompt(
        problem,
        "Choose the candidate solution that is most likely to be correct.\n"
        f"{listing}\n"
        "Answer with the index alone, in \\boxed{}.",
    )


def parse_verbalized(text: str, *, limit: int) -> tuple[list[tuple[float, str]], bool]:
    """Parse "<probability> | <approach>" lines into weighted options."""
    weighted: list[tuple[float, str]] = []
    for line in text.splitlines():
        match = _WEIGHTED_LINE.match(line)
        if not match:
            continue
        value = float(match.group(1))
        if match.group(2) == "%":
            value /= 100.0
        if 0.0 < value <= 1.0:
            weighted.append((value, match.group(3).strip()))
    if weighted:
        return weighted[:limit], True
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 3]
    return [(1.0, line) for line in lines[:limit]], False
