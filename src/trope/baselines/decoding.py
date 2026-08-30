"""The eight decoding baselines and self-consistency, as one sampling loop."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from trope.baselines.common import (
    BaselineContext,
    BaselineResult,
    baseline_params,
    build_prompt,
    generator_params,
    rounds,
    sample_candidates,
)
from trope.data.base import Problem
from trope.verify.exact_match import extract_answer, normalise_answer

DECODING_KEYS: dict[str, str] = {
    "greedy": "greedy",
    "temp_0.7": "temperature_07",
    "temp_1.0": "temperature_10",
    "temp_1.2": "temperature_12",
    "top_p": "top_p",
    "min_p": "min_p",
    "top_h": "top_h",
    "eta": "eta_sampling",
}

DETERMINISTIC: frozenset[str] = frozenset({"greedy"})

SELF_CONSISTENCY_GUIDANCE = (
    "Reason step by step, then commit to one final answer."
)


def run_decoding(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
    *,
    arm: str,
) -> BaselineResult:
    """Draw K independent samples from one fixed decoding configuration."""
    key = DECODING_KEYS[arm]
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=budget,
        rng=rng,
        params=baseline_params(key),
        deterministic=arm in DETERMINISTIC,
    )
    prompt = build_prompt(problem)
    for index in rounds(ctx):
        sample_candidates(ctx, prompt, iteration=index, meta={"arm": arm})
    return ctx.result(
        arm=arm,
        decoding=key,
        deterministic=ctx.deterministic,
        temperature=ctx.params.temperature,
    )


def _decoding_arm(arm: str) -> Callable[..., BaselineResult]:
    params = baseline_params(DECODING_KEYS[arm])

    def run(
        problem: Problem,
        backend: Any,
        verifier: Callable[[Problem, str], Any],
        budget: int,
        rng: np.random.Generator,
    ) -> BaselineResult:
        return run_decoding(problem, backend, verifier, budget, rng, arm=arm)

    run.__name__ = arm.replace(".", "_")
    run.__qualname__ = run.__name__
    run.__doc__ = f"Baseline {arm!r}: K independent samples at {params}."
    return run


DECODING_BASELINES: dict[str, Callable[..., BaselineResult]] = {
    arm: _decoding_arm(arm) for arm in DECODING_KEYS
}


@dataclass(slots=True)
class VoteResult:
    """Outcome of a majority vote over extracted answers."""

    answer: str | None
    counts: dict[str, int] = field(default_factory=dict)
    winner_index: int | None = None
    tied: tuple[str, ...] = ()

    @property
    def votes(self) -> int:
        return self.counts.get(_fold(self.answer or ""), 0)


def majority_vote(texts: Sequence[str]) -> VoteResult:
    """Majority vote over the answers extracted from candidate texts."""
    buckets: dict[str, list[int]] = {}
    labels: dict[str, str] = {}
    for index, text in enumerate(texts):
        raw = extract_answer(text)
        if raw is None:
            continue
        answer = normalise_answer(raw)
        if not answer:
            continue
        key = _fold(answer)
        buckets.setdefault(key, []).append(index)
        labels.setdefault(key, answer)
    if not buckets:
        return VoteResult(None)
    top = max(len(hits) for hits in buckets.values())
    tied = [key for key, hits in buckets.items() if len(hits) == top]
    winner = min(tied, key=lambda key: buckets[key][0])
    return VoteResult(
        answer=labels[winner],
        counts={key: len(hits) for key, hits in buckets.items()},
        winner_index=buckets[winner][0],
        tied=tuple(labels[key] for key in sorted(tied, key=lambda k: buckets[k][0])),
    )


def _fold(answer: str) -> str:
    return answer.replace(" ", "").casefold()


def self_consistency(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
) -> BaselineResult:
    """Self-consistency (Wang et al. 2022): sample K chains, vote on the answer."""
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=budget,
        rng=rng,
        params=generator_params(),
    )
    prompt = build_prompt(problem, SELF_CONSISTENCY_GUIDANCE)
    for index in rounds(ctx):
        sample_candidates(ctx, prompt, iteration=index, meta={"arm": "self_consistency"})

    vote = majority_vote([c["text"] for c in ctx.candidates])
    result = ctx.result(
        arm="self_consistency",
        majority_answer=vote.answer,
        votes=vote.votes,
        counts=vote.counts,
        tied=list(vote.tied),
        abstentions=len(ctx.candidates) - sum(vote.counts.values()),
        tie_break="earliest sample among the tied answers",
    )
    if vote.winner_index is not None:
        winner = ctx.candidates[vote.winner_index]
        winner["meta"]["majority"] = True
        result.best = winner
        result.meta["majority_verified"] = winner["verified"]
    return result
