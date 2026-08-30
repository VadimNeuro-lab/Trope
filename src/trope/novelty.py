"""Compression novelty, Eq. (5): Nov(s|C) = log P_ref(C|s) - log P_ref(C|empty)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from trope.backends.base import ScoreResult

NORMALISATIONS: tuple[str, ...] = ("compression", "per_token", "total")

DEFAULT_WINDOW_TOKENS = 512

CONTEXT_ATTRIBUTES: tuple[str, ...] = (
    "context_tokens",
    "context_window",
    "max_context_tokens",
    "context_length",
    "n_ctx",
    "window",
)


@dataclass(frozen=True, slots=True)
class NoveltyResult:
    value: float
    total_logprob: float
    baseline_logprob: float
    n_tokens: int
    truncated: bool = False

    @property
    def gain(self) -> float:
        """The unnormalised difference, whatever `normalise` was set to."""
        return self.total_logprob - self.baseline_logprob


def reported_context(scorer: Any) -> int | None:
    """The reference model's context length, if the backend reports one."""
    seen: set[int] = set()
    while scorer is not None and id(scorer) not in seen:
        seen.add(id(scorer))
        for attr in CONTEXT_ATTRIBUTES:
            value = getattr(scorer, attr, None)
            if callable(value):
                value = value()
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return int(value)
        scorer = getattr(scorer, "inner", None)
    return None


class CompressionNovelty:
    """Nov(s|C) against a fixed corpus and a frozen reference LM."""

    __slots__ = (
        "_baseline",
        "_baseline_parts",
        "_passages",
        "_prefix_tokens",
        "_truncated_passages",
        "context_tokens",
        "corpus",
        "normalise",
        "prefix_fraction",
        "scorer",
        "window_tokens",
    )

    def __init__(
        self,
        scorer: Any,
        corpus: Any,
        *,
        normalise: str = "per_token",
        window_tokens: int = DEFAULT_WINDOW_TOKENS,
        prefix_tokens: int | None = None,
        context_tokens: int | None = None,
        prefix_fraction: float = 0.5,
    ) -> None:
        if normalise not in NORMALISATIONS:
            raise ValueError(f"normalise must be one of {NORMALISATIONS}, got {normalise!r}")
        if not 0.0 < prefix_fraction < 1.0:
            raise ValueError("prefix_fraction must be strictly between 0 and 1")
        self.scorer = scorer
        self.corpus = corpus
        self.normalise = normalise
        self.context_tokens = (
            reported_context(scorer) if context_tokens is None else int(context_tokens)
        )
        self.window_tokens = int(self.context_tokens or window_tokens)
        if self.window_tokens < 2:
            raise ValueError("the window must hold at least one candidate and one corpus token")
        self.prefix_fraction = float(prefix_fraction)
        self._prefix_tokens = None if prefix_tokens is None else int(prefix_tokens)
        if self._prefix_tokens is not None and not 0 < self._prefix_tokens < self.window_tokens:
            raise ValueError("prefix_tokens must leave room for corpus tokens")
        self._passages: tuple[str, ...] | None = None
        self._truncated_passages = 0
        self._baseline_parts: tuple[ScoreResult, ...] = ()
        self._baseline: float | None = None

    @property
    def prefix_tokens(self) -> int:
        """The candidate's share of the window."""
        self._size()
        return int(self._prefix_tokens or 0)

    @property
    def passage_tokens(self) -> int:
        return self.window_tokens - self.prefix_tokens

    @property
    def passages_truncated(self) -> int:
        self._size()
        return self._truncated_passages

    def _size(self) -> tuple[str, ...]:
        """Split the window between candidate and corpus, once, at first use."""
        if self._passages is not None:
            return self._passages
        raw = _corpus_passages(self.corpus)
        if self._prefix_tokens is None:
            longest = max(self.scorer.count_tokens(text) for text in raw)
            proportional = max(1, int(self.window_tokens * self.prefix_fraction))
            spare = self.window_tokens - longest
            self._prefix_tokens = min(max(proportional, spare), self.window_tokens - 1)
        budget = self.window_tokens - self._prefix_tokens
        kept: list[str] = []
        truncated = 0
        for text in raw:
            passage, cut = _truncate(self.scorer, text, budget)
            truncated += int(cut)
            kept.append(passage)
        self._passages = tuple(kept)
        self._truncated_passages = truncated
        return self._passages

    def passages(self) -> tuple[str, ...]:
        """The corpus passages, each truncated to the fixed per-passage budget."""
        return self._size()

    def baseline(self) -> float:
        """log P_ref(C | empty). Cached: it does not depend on the candidate."""
        if self._baseline is None:
            parts = tuple(self.scorer.score(p, "") for p in self.passages())
            self._baseline_parts = parts
            self._baseline = float(sum(p.total_logprob for p in parts))
        return self._baseline

    @property
    def n_corpus_tokens(self) -> int:
        self.baseline()
        return int(sum(p.n_tokens for p in self._baseline_parts))

    def score(self, candidate_text: str) -> NoveltyResult:
        baseline = self.baseline()
        prefix, prefix_cut = _truncate(self.scorer, candidate_text, self.prefix_tokens)
        total = 0.0
        n_tokens = 0
        for passage, base in zip(self.passages(), self._baseline_parts, strict=False):
            res = self.scorer.score(passage, prefix)
            if res.n_tokens != base.n_tokens:
                raise ValueError(
                    "reference LM tokenised the same passage into "
                    f"{res.n_tokens} tokens with a candidate prefix and "
                    f"{base.n_tokens} without it; the two terms of Nov would "
                    "not be over the same corpus tokens"
                )
            total += res.total_logprob
            n_tokens += res.n_tokens
        gain = total - baseline
        if self.normalise == "compression":
            cost = -baseline
            value = min(max(gain / cost, 0.0), 1.0) if cost > 0.0 else 0.0
        elif self.normalise == "per_token":
            value = gain / n_tokens if n_tokens else 0.0
        else:
            value = gain
        return NoveltyResult(
            value=float(value),
            total_logprob=float(total),
            baseline_logprob=float(baseline),
            n_tokens=int(n_tokens),
            truncated=bool(prefix_cut or self._truncated_passages),
        )


def null_check(
    scorer: Any,
    corpus: Any,
    rng: np.random.Generator,
    *,
    lengths: Sequence[int] = (16, 32, 64, 128, 256),
    n: int = 1000,
    vocabulary: Sequence[str] | None = None,
    resamples: int = 1000,
    normalise: str = "total",
    window_tokens: int = DEFAULT_WINDOW_TOKENS,
) -> dict[int, dict[str, Any]]:
    """Probe Assumption 3.3 by scoring uniform random-token prefixes."""
    nov = CompressionNovelty(
        scorer, corpus, normalise=normalise, window_tokens=window_tokens
    )
    vocab = tuple(vocabulary or ())
    source = "given"
    if not vocab:
        vocab, source = model_vocabulary(scorer), "model"
    if not vocab:
        vocab, source = _corpus_vocabulary(corpus), "corpus"
    if not vocab:
        raise ValueError("cannot draw random prefixes from an empty vocabulary")
    table: dict[int, dict[str, Any]] = {}
    for length in lengths:
        idx = rng.integers(0, len(vocab), size=(int(n), int(length)))
        values = np.array(
            [nov.score(" ".join(vocab[j] for j in row)).value for row in idx],
            dtype=np.float64,
        )
        lo, hi = _bootstrap_ci(values, rng, resamples=resamples)
        table[int(length)] = {
            "n": int(n),
            "mean": float(values.mean()),
            "sd": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
            "ci": [lo, hi],
            "p_nonpositive": float(np.mean(values <= 0.0)),
            "vocabulary": source,
            "vocabulary_size": len(vocab),
        }
    return table


def _bootstrap_ci(
    values: np.ndarray, rng: np.random.Generator, *, resamples: int = 1000, level: float = 0.95
) -> tuple[float, float]:
    if values.size == 0:
        return (float("nan"), float("nan"))
    draws = rng.integers(0, values.size, size=(int(resamples), values.size))
    means = values[draws].mean(axis=1)
    tail = 100.0 * (1.0 - level) / 2.0
    lo, hi = np.percentile(means, [tail, 100.0 - tail])
    return (float(lo), float(hi))


def _corpus_passages(corpus: Any) -> tuple[str, ...]:
    """Accept a `corpus.Corpus`, a sequence of strings, or a single string."""
    if isinstance(corpus, str):
        return (corpus,)
    passages = getattr(corpus, "passages", None)
    if passages is None:
        passages = tuple(corpus)
    out = tuple(str(p) for p in passages if str(p).strip())
    if not out:
        raise ValueError("evidence corpus is empty; Nov(s|C) is undefined")
    return out


def model_vocabulary(scorer: Any) -> tuple[str, ...]:
    """The reference model's own vocabulary, if the backend exposes one."""
    seen: set[int] = set()
    while scorer is not None and id(scorer) not in seen:
        seen.add(id(scorer))
        tokens = _vocabulary_of(scorer)
        if tokens:
            return tokens
        scorer = getattr(scorer, "inner", None)
    return ()


def _vocabulary_of(obj: Any) -> tuple[str, ...]:
    raw = getattr(obj, "vocabulary", None)
    if callable(raw):
        raw = raw()
    special: tuple[str, ...] = ()
    if raw is None:
        tokenizer = getattr(obj, "tokenizer", None)
        if tokenizer is None:
            return ()
        getter = getattr(tokenizer, "get_vocab", None)
        raw = getter() if callable(getter) else getattr(tokenizer, "vocab", None)
        special = tuple(str(t) for t in getattr(tokenizer, "all_special_tokens", ()) or ())
    if raw is None:
        return ()
    return tuple(sorted({str(t) for t in raw} - set(special) - {""}))


def _corpus_vocabulary(corpus: Any) -> tuple[str, ...]:
    """Word types of the corpus, sorted."""
    seen: set[str] = set()
    for passage in _corpus_passages(corpus):
        seen.update(w for w in passage.lower().split() if w.isalpha())
    return tuple(sorted(seen))


def _truncate(scorer: Any, text: str, budget: int) -> tuple[str, bool]:
    """Longest whitespace-delimited prefix of `text` within `budget` tokens."""
    if not text.strip():
        return "", False
    if budget <= 0:
        return "", True
    if scorer.count_tokens(text) <= budget:
        return text, False
    words = text.split()
    lo, hi = 0, len(words)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if scorer.count_tokens(" ".join(words[:mid])) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return " ".join(words[:lo]), True
