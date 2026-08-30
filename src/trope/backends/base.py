"""Backend interface shared by the mock, HuggingFace and vLLM implementations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True, slots=True)
class DecodingParams:
    """Decoding knobs. `None` means "leave this truncation off"."""

    temperature: float = 0.7
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    eta: float | None = None
    entropy_budget: float | None = None
    max_tokens: int = 512
    stop: tuple[str, ...] = ()

    def merged(self, **changes: Any) -> DecodingParams:
        return replace(self, **{k: v for k, v in changes.items() if v is not None})


@dataclass(slots=True)
class Generation:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScoreResult:
    """Summed log-probability of the continuation tokens only."""

    total_logprob: float
    n_tokens: int
    token_logprobs: np.ndarray | None = None

    @property
    def mean_logprob(self) -> float:
        return self.total_logprob / self.n_tokens if self.n_tokens else 0.0


@runtime_checkable
class Backend(Protocol):
    name: str

    def generate(
        self,
        prompt: str,
        params: DecodingParams,
        *,
        seed: int | None = None,
        role: str = "generator",
    ) -> Generation: ...

    def score(self, continuation: str, prefix: str = "") -> ScoreResult: ...

    def count_tokens(self, text: str) -> int: ...


class CallCounter:
    """Per-role call accounting."""

    __slots__ = ("counts", "tokens")

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.tokens: dict[str, int] = {}

    def record(self, role: str, tokens: int = 0) -> None:
        self.counts[role] = self.counts.get(role, 0) + 1
        self.tokens[role] = self.tokens.get(role, 0) + tokens

    def get(self, role: str) -> int:
        return self.counts.get(role, 0)

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {"calls": dict(self.counts), "tokens": dict(self.tokens)}

    def reset(self) -> None:
        self.counts.clear()
        self.tokens.clear()


class BudgetExceeded(RuntimeError):
    """Raised when a run asks for more generator calls than the matched budget."""


class MeteredBackend:
    """Wraps a backend, tags every call with a role and enforces the budget."""

    def __init__(
        self,
        inner: Backend,
        counter: CallCounter | None = None,
        *,
        budget: int | None = None,
        role: str = "generator",
    ) -> None:
        self.inner = inner
        self.counter = counter if counter is not None else CallCounter()
        self.budget = budget
        self.role = role
        self.name = getattr(inner, "name", inner.__class__.__name__)

    def for_role(self, role: str) -> MeteredBackend:
        return MeteredBackend(
            self.inner, self.counter, budget=self.budget, role=role
        )

    @property
    def generator_calls(self) -> int:
        return self.counter.get("generator")

    def remaining(self) -> int | None:
        if self.budget is None:
            return None
        return max(0, self.budget - self.counter.get("generator"))

    def generate(
        self,
        prompt: str,
        params: DecodingParams,
        *,
        seed: int | None = None,
        role: str | None = None,
    ) -> Generation:
        role = role or self.role
        if (
            role == "generator"
            and self.budget is not None
            and self.counter.get("generator") >= self.budget
        ):
            raise BudgetExceeded(
                f"generator budget of {self.budget} calls is exhausted"
            )
        gen = self.inner.generate(prompt, params, seed=seed, role=role)
        self.counter.record(role, gen.completion_tokens)
        return gen

    def score(self, continuation: str, prefix: str = "") -> ScoreResult:
        res = self.inner.score(continuation, prefix)
        self.counter.record(f"{self.role}_score", res.n_tokens)
        return res

    def count_tokens(self, text: str) -> int:
        return self.inner.count_tokens(text)


@runtime_checkable
class Encoder(Protocol):
    """Maps short strings to fixed-width vectors (typed-feature embedding)."""

    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


class HashEncoder:
    """Deterministic feature-hashing encoder."""

    def __init__(self, dim: int = 64, ngram: int = 3) -> None:
        self.dim = dim
        self.ngram = ngram

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float64)
        text = text.strip().lower()
        if not text:
            return vec
        tokens = [text[i : i + self.ngram] for i in range(max(1, len(text) - self.ngram + 1))]
        tokens += text.split()
        for tok in tokens:
            h = _stable_hash(tok)
            vec[h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float64)
        return np.vstack([self._one(t) for t in texts])


def _stable_hash(text: str) -> int:
    """FNV-1a. Python's hash() is salted per process, which would break seeds."""
    h = 0xCBF29CE484222325
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h
