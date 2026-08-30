"""V_P: the verifier bound to the original problem."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from trope.data.base import Problem

Predicate = Callable[[float], bool]

TOLERANCE = 1e-9


def at_least(threshold: float) -> Predicate:
    """Acceptance predicate for the archive: V_P accepts at or above `threshold`."""
    return lambda value: value >= threshold - TOLERANCE


@dataclass(frozen=True, slots=True)
class Verdict:
    """`value` in [0, 1]; `verified` is the verifier's own accept decision."""

    value: float
    verified: bool
    detail: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Verifier(Protocol):
    name: str

    def __call__(self, problem: Problem, candidate_text: str) -> Verdict: ...


FAMILY_VERIFIER: dict[str, str] = {
    "math_answer": "exact_match",
    "math_proof": "judge",
    "code": "code_exec",
    "creativity": "oracle",
    "discovery": "oracle",
}

BENCHMARK_FAMILY: dict[str, str] = {
    "math500": "math_answer",
    "aime": "math_answer",
    "usamo": "math_proof",
    "livecodebench": "code",
    "humaneval_plus": "code",
    "noveltybench": "creativity",
    "creativityprism": "creativity",
    "uot": "creativity",
    "llmsrbench": "discovery",
    "researchbench": "discovery",
}


def get_verifier(
    problem_or_benchmark: Problem | str,
    *,
    backend: Any = None,
    **kw: Any,
) -> Verifier:
    """Build the verifier for a problem, or for a benchmark named as a string."""
    if isinstance(problem_or_benchmark, str):
        benchmark = problem_or_benchmark
        family = BENCHMARK_FAMILY.get(benchmark)
        if family is None:
            raise KeyError(
                f"unknown benchmark {benchmark!r}; "
                f"have {sorted(BENCHMARK_FAMILY)}"
            )
    else:
        benchmark = problem_or_benchmark.benchmark
        family = problem_or_benchmark.family

    kind = FAMILY_VERIFIER.get(family)
    if kind is None:
        raise KeyError(f"no verifier for family {family!r}")

    if kind == "exact_match":
        from trope.verify.exact_match import ExactMatchVerifier

        return ExactMatchVerifier(**kw)
    if kind == "code_exec":
        from trope.verify.code_exec import CodeExecVerifier

        return CodeExecVerifier(**kw)
    if kind == "judge":
        from trope.verify.judge import JudgeVerifier

        if backend is None:
            raise ValueError(
                f"family {family!r} is verified by an LLM judge and needs a backend"
            )
        return JudgeVerifier(backend, **kw)

    from trope.verify.oracle import OracleVerifier

    return OracleVerifier(benchmark, **kw)
