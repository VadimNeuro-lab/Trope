"""Shared machinery for the baseline arms: the budget gate, prompts, records."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import yaml

from trope.backends.base import BudgetExceeded, DecodingParams, Generation
from trope.config import CONFIG_DIR
from trope.data.base import Problem

PROMPT_TEMPLATE = """Solve the problem below.

<problem>
{problem}
</problem>
{guidance}
Write your reasoning, then the final answer:

  - for a problem with a definite answer, end with the answer in \\boxed{{}};
  - for a coding problem, end with the complete solution in a single fenced
    python block, with no text after it;
  - otherwise, end with a line beginning "Final answer:".
"""

_CONFIG_CACHE: dict[str, Any] | None = None


def decoding_config() -> Mapping[str, Any]:
    """configs/decoding.yaml, read once per process."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        path = CONFIG_DIR / "decoding.yaml"
        _CONFIG_CACHE = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _CONFIG_CACHE


def generator_params() -> DecodingParams:
    """The run's standard generator decoding."""
    block = dict(decoding_config().get("generator") or {})
    return DecodingParams(
        temperature=float(block.get("temperature", 0.7)),
        top_p=block.get("top_p"),
        max_tokens=int(block.get("max_tokens", 512)),
        stop=tuple(block.get("stop") or ()),
    )


def baseline_params(key: str) -> DecodingParams:
    """One entry of the `baselines:` block of configs/decoding.yaml."""
    table = dict(decoding_config().get("baselines") or {})
    if key not in table:
        raise KeyError(
            f"no decoding entry {key!r} in configs/decoding.yaml `baselines`; "
            f"have {sorted(table)}"
        )
    return DecodingParams(max_tokens=generator_params().max_tokens, **table[key])


def excerpt(text: str, limit: int = 600) -> str:
    """A whitespace-collapsed prefix, for quoting a candidate inside a prompt."""
    body = " ".join(text.split())
    return body if len(body) <= limit else body[: limit - 3] + "..."


def build_prompt(problem: Problem, guidance: str = "") -> str:
    """The arm's prompt for one problem; `guidance` is the method's own steer."""
    body = f"\n{guidance.strip()}\n" if guidance.strip() else ""
    return PROMPT_TEMPLATE.format(problem=problem.text.strip(), guidance=body)


@dataclass(slots=True)
class BaselineResult:
    """What an arm hands back. `cli._cmd_baseline` reads the first and third."""

    candidates: list[dict[str, Any]]
    best: dict[str, Any] | None
    generator_calls: int
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def solved(self) -> bool:
        return any(c["verified"] for c in self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "best": self.best,
            "generator_calls": self.generator_calls,
            "meta": self.meta,
            "solved": self.solved,
        }


@dataclass(slots=True)
class BaselineContext:
    """Per-problem state for one arm: the budget, the RNG, the candidate list."""

    problem: Problem
    backend: Any
    verifier: Callable[[Problem, str], Any]
    budget: int
    rng: np.random.Generator
    params: DecodingParams = field(default_factory=generator_params)
    deterministic: bool = False
    calls: int = 0
    stopped: bool = False
    candidates: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.budget = max(0, int(self.budget))
        room = getattr(self.backend, "remaining", None)
        if callable(room):
            left = room()
            if left is not None:
                self.budget = min(self.budget, int(left))

    @property
    def remaining(self) -> int:
        if self.stopped:
            return 0
        return max(0, self.budget - self.calls)

    def ask(self, prompt: str, params: DecodingParams | None = None) -> Generation | None:
        """One backbone call, or None once K is spent."""
        if self.remaining <= 0:
            return None
        seed = None if self.deterministic else int(self.rng.integers(0, 2**31 - 1))
        try:
            gen = self.backend.generate(
                prompt, params or self.params, seed=seed, role="generator"
            )
        except BudgetExceeded:
            self.meta["budget_exceeded"] = True
            self.stopped = True
            return None
        self.calls += 1
        return gen

    def result(self, **meta: Any) -> BaselineResult:
        self.meta.update(meta)
        return BaselineResult(
            candidates=self.candidates,
            best=best_candidate(self.candidates),
            generator_calls=self.calls,
            meta=dict(self.meta),
        )


def sample_candidates(
    ctx: BaselineContext,
    prompts: str | Sequence[str],
    *,
    iteration: int,
    params: DecodingParams | None = None,
    meta: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate one candidate per prompt, verify it, record it."""
    if isinstance(prompts, str):
        prompts = (prompts,)
    produced: list[dict[str, Any]] = []
    for prompt in prompts:
        gen = ctx.ask(prompt, params)
        if gen is None:
            break
        verdict = ctx.verifier(ctx.problem, gen.text)
        record = {
            "text": gen.text,
            "verified": bool(verdict.verified),
            "verdict": float(verdict.value),
            "iteration": int(iteration),
            "meta": {
                "detail": verdict.detail,
                "completion_tokens": gen.completion_tokens,
                **(dict(meta) if meta else {}),
            },
        }
        ctx.candidates.append(record)
        produced.append(record)
    return produced


def rounds(ctx: BaselineContext) -> Iterator[int]:
    """Yield 1-based round indices while budget remains."""
    index = 0
    while ctx.remaining > 0:
        before = ctx.calls
        index += 1
        yield index
        if ctx.calls == before:
            return


def best_candidate(candidates: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Highest verdict; ties go to the candidate that was produced first."""
    best: dict[str, Any] | None = None
    for candidate in candidates:
        if best is None or candidate["verdict"] > best["verdict"]:
            best = candidate
    return best


def run_baseline(
    name: str,
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
    **kw: Any,
) -> BaselineResult:
    """Run one arm by registry name. The CLI's call, in a single function."""
    from trope.baselines.registry import get_baseline

    return get_baseline(name)(problem, backend, verifier, budget, rng, **kw)
