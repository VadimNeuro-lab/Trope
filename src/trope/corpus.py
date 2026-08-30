"""The evidence corpus C and the BM25 retrieval that builds it."""

from __future__ import annotations

import functools
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from trope.config import ASSET_DIR
from trope.data.base import Problem

_WORD = re.compile(r"[a-z0-9]+")
_BOXED = re.compile(r"\\boxed\s*\{(.*)\}", re.DOTALL)
_DIGIT_GROUP = re.compile(r"(?<=\d),(?=\d\d\d)")
_LATEX_NOISE = re.compile(r"\\(?:left|right|,|!|;|\s)")

BENCHMARK_PATH_PATTERNS: tuple[str, ...] = (
    "math500",
    "math 500",
    "aime",
    "usamo",
    "livecodebench",
    "live code bench",
    "humaneval",
    "human eval",
    "noveltybench",
    "creativityprism",
    "uot",
    "llmsrbench",
    "llm srbench",
    "researchbench",
    "gold",
    "solutions",
    "answer key",
    "test cases",
)


def tokenise(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    text: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class Corpus:
    """The passages Nov(s|C) is scored against, plus their retrieval provenance."""

    passages: tuple[str, ...]
    ids: tuple[str, ...]
    scores: tuple[float, ...]
    problem_id: str = ""
    family: str = ""
    sources: tuple[str, ...] = ()
    report: Mapping[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.passages)

    def __iter__(self) -> Iterator[str]:
        return iter(self.passages)

    def records(self) -> list[dict[str, Any]]:
        sources = self.sources or ("",) * len(self.passages)
        return [
            {
                "passage_id": pid,
                "problem_id": self.problem_id,
                "family": self.family,
                "source": src,
                "score": score,
                "text": text,
            }
            for pid, text, score, src in zip(self.ids, self.passages, self.scores, sources, strict=False)
        ]

    def write_jsonl(self, path: str | Path) -> Path:
        """Export in the shape `analysis.audit.sample_retrieval_audit` reads."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for record in self.records():
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path


class BM25Index:
    """Okapi BM25 with the Lucene idf variant."""

    __slots__ = ("_by_id", "_df", "_len", "_tf", "avgdl", "b", "documents", "k1")

    def __init__(
        self,
        documents: Iterable[Document | str],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        docs: list[Document] = []
        for i, doc in enumerate(documents):
            docs.append(Document(f"doc{i}", doc) if isinstance(doc, str) else doc)
        self.documents = tuple(docs)
        self.k1 = float(k1)
        self.b = float(b)
        self._tf = [Counter(tokenise(d.text)) for d in self.documents]
        self._df: Counter[str] = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())
        self._len = np.array([sum(tf.values()) for tf in self._tf], dtype=np.float64)
        self.avgdl = float(self._len.mean()) if len(self._len) else 0.0
        self._by_id = {d.id: d for d in self.documents}
        if len(self._by_id) != len(self.documents):
            raise ValueError("document ids must be unique")

    def __len__(self) -> int:
        return len(self.documents)

    def get(self, doc_id: str) -> Document:
        return self._by_id[doc_id]

    def idf(self, term: str) -> float:
        n = len(self.documents)
        df = self._df.get(term, 0)
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def score(self, query_terms: Sequence[str], doc_index: int) -> float:
        if self.avgdl <= 0.0:
            return 0.0
        tf = self._tf[doc_index]
        norm = self.k1 * (1.0 - self.b + self.b * self._len[doc_index] / self.avgdl)
        total = 0.0
        for term in query_terms:
            f = tf.get(term, 0)
            if f:
                total += self.idf(term) * f * (self.k1 + 1.0) / (f + norm)
        return float(total)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Documents with a positive score, best first, ties broken by doc id."""
        terms = tokenise(query)
        scored = [
            (doc.id, self.score(terms, i))
            for i, doc in enumerate(self.documents)
        ]
        hits = [(doc_id, s) for doc_id, s in scored if s > 0.0]
        hits.sort(key=lambda item: (-item[1], item[0]))
        return hits[: max(0, int(top_k))]


class GoldAnswerFilter:
    """Rejects leaked passages, and counts what it rejected."""

    __slots__ = ("_counts", "needles", "path_patterns")

    def __init__(
        self,
        answers: Iterable[str] = (),
        *,
        path_patterns: Sequence[str] = BENCHMARK_PATH_PATTERNS,
    ) -> None:
        needles: list[str] = []
        for answer in answers:
            for variant in answer_variants(answer):
                if variant and variant not in needles:
                    needles.append(variant)
        self.needles = tuple(needles)
        self.path_patterns = tuple(tuple(tokenise(p)) for p in path_patterns)
        self._counts = {"seen": 0, "kept": 0, "dropped_answer": 0, "dropped_path": 0}

    @classmethod
    def from_problem(cls, problem: Problem, **kwargs: Any) -> GoldAnswerFilter:
        answers = [problem.answer or ""]
        answers.extend(problem.tests)
        return cls([a for a in answers if a.strip()], **kwargs)

    def __call__(self, doc: Document) -> bool:
        self._counts["seen"] += 1
        if self._path_is_benchmark(doc.source):
            self._counts["dropped_path"] += 1
            return False
        if self._contains_answer(doc.text):
            self._counts["dropped_answer"] += 1
            return False
        self._counts["kept"] += 1
        return True

    def screen(self, documents: Iterable[Document]) -> tuple[Document, ...]:
        return tuple(d for d in documents if self(d))

    def filter_report(self) -> dict[str, int]:
        return dict(self._counts)

    def reset(self) -> None:
        for key in self._counts:
            self._counts[key] = 0

    def _contains_answer(self, text: str) -> bool:
        """Does the passage state the gold answer anywhere in it?"""
        if not self.needles:
            return False
        haystack = _flatten(text)
        return any(
            re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", haystack)
            for n in self.needles
        )

    def _path_is_benchmark(self, source: str) -> bool:
        tokens = tokenise(source)
        for pattern in self.path_patterns:
            n = len(pattern)
            if n and any(
                tuple(tokens[i : i + n]) == pattern for i in range(len(tokens) - n + 1)
            ):
                return True
        return False


def _flatten(text: str) -> str:
    """Passage-wide normalisation: case, digit-group commas, whitespace."""
    out = text.lower()
    out = _DIGIT_GROUP.sub("", out)
    return " ".join(out.split())


def normalise_answer(text: str) -> str:
    """Lowercase, strip LaTeX packaging and digit-group commas, collapse space."""
    out = text.strip()
    boxed = _BOXED.search(out)
    if boxed:
        out = boxed.group(1)
    out = out.replace("$", "").replace("\\dfrac", "\\frac")
    out = _LATEX_NOISE.sub(" ", out)
    out = _DIGIT_GROUP.sub("", out)
    return " ".join(out.lower().split())


def answer_variants(answer: str) -> tuple[str, ...]:
    """Forms of a gold answer a passage could plausibly spell it in."""
    base = normalise_answer(answer)
    if not base:
        return ()
    variants = [base]
    squeezed = base.replace(" ", "")
    if squeezed != base:
        variants.append(squeezed)
    try:
        value = float(base)
    except ValueError:
        return tuple(variants)
    if value.is_integer():
        variants.append(str(int(value)))
    else:
        variants.append(repr(value))
    return tuple(dict.fromkeys(variants))


class RetrievalError(RuntimeError):
    """BM25 returned nothing usable, so C would be empty and Nov undefined."""


def build_corpus(
    problem: Problem,
    index: BM25Index,
    *,
    top_k: int = 200,
    gold_filter: GoldAnswerFilter | None = None,
    oversample: int = 3,
) -> Corpus:
    """Retrieve, filter, and package the evidence corpus for one problem."""
    filt = gold_filter if gold_filter is not None else GoldAnswerFilter.from_problem(problem)
    hits = index.search(problem.text, max(top_k * oversample, top_k))
    kept = [(doc_id, score) for doc_id, score in hits if filt(index.get(doc_id))][:top_k]
    if len(kept) < top_k:
        reached = {doc_id for doc_id, _ in hits}
        rest = [d for d in index.documents if d.id not in reached]
        kept += [(d.id, 0.0) for d in rest if filt(d)][: top_k - len(kept)]
    if not kept:
        report = filt.filter_report()
        raise RetrievalError(
            f"no passage survives the gold-answer filter for problem "
            f"{problem.id!r}: an index of {len(index)} documents, "
            f"{report['dropped_answer']} dropped for stating the gold answer "
            f"and {report['dropped_path']} for a benchmark path. Nov(s|C) is "
            "undefined against an empty corpus."
        )
    zero_scored = sum(1 for _, score in kept if score <= 0.0)
    report = dict(filt.filter_report(), zero_scored=zero_scored)
    docs = [index.get(doc_id) for doc_id, _ in kept]
    return Corpus(
        passages=tuple(d.text for d in docs),
        ids=tuple(d.id for d in docs),
        scores=tuple(float(s) for _, s in kept),
        problem_id=problem.id,
        family=problem.family,
        sources=tuple(d.source for d in docs),
        report=report,
    )


def frame_passages() -> tuple[Document, ...]:
    """One passage per frame of `assets/frames.json`: keywords plus axiom text."""
    raw = json.loads((ASSET_DIR / "frames.json").read_text(encoding="utf-8"))["frames"]
    docs = []
    for name, spec in sorted(raw.items()):
        keywords = ", ".join(spec.get("keywords", ()))
        axioms = " ".join(a["text"] + "." for a in spec.get("axioms", ()))
        topic = name.replace("-", " ")
        docs.append(
            Document(
                id=f"frame:{name}",
                text=f"{topic}. Key notions: {keywords}. {axioms}".strip(),
                source="assets/frames.json",
            )
        )
    return tuple(docs)


@functools.lru_cache(maxsize=1)
def fallback_index() -> BM25Index:
    """The bundled stand-in index. Not the paper's corpus; see the module docstring."""
    return BM25Index(frame_passages())
