"""Behavioral descriptors delta: S -> B, one grid per benchmark."""

from __future__ import annotations

import ast
import functools
import hashlib
import json
import math
import re
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from scipy.stats import norm

from trope.backends.base import DecodingParams, Encoder, HashEncoder
from trope.config import ASSET_DIR
from trope.types import Representation

Tagger = Callable[[str, Sequence[str]], str]

_WORD = re.compile(r"[a-z0-9']+")
_CODE_FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)
_LOOP = re.compile(r"^\s*(for|while)\b")
_BRANCH = re.compile(r"^\s*(if|elif|else|match|case)\b")
_DEF = re.compile(r"^\s*def\s+([A-Za-z_]\w*)")


class Descriptor(Protocol):
    name: str
    shape: tuple[int, ...]
    n_cells: int

    def __call__(
        self, candidate_text: str, representation: Representation | None = None
    ) -> tuple[int, ...]: ...

    def cell_index(self, desc: Sequence[int]) -> int: ...


class Axis(Protocol):
    name: str
    size: int

    def __call__(self, text: str, rep: Representation | None) -> int: ...


@functools.lru_cache(maxsize=1)
def vocabularies() -> dict:
    path = ASSET_DIR / "descriptor_vocabularies.json"
    return json.loads(path.read_text(encoding="utf-8"))


def tag_vocabulary(name: str) -> tuple[str, ...]:
    return tuple(vocabularies()["tags"][name])


@functools.lru_cache(maxsize=1)
def _vocabulary_to_axis() -> Mapping[tuple[str, ...], str]:
    return {tuple(tags): name for name, tags in vocabularies()["tags"].items()}


def axis_for_vocabulary(vocabulary: Sequence[str]) -> str:
    """Name the tag axis whose closed vocabulary is exactly `vocabulary`."""
    key = tuple(vocabulary)
    known = _vocabulary_to_axis().get(key)
    if known is not None:
        return known
    digest = hashlib.sha256("\x00".join(key).encode("utf-8")).hexdigest()
    return f"anon:{digest[:16]}"


@dataclass(frozen=True, slots=True)
class BinAxis:
    """A statistic of the candidate, clipped into `size` ordered bins."""

    name: str
    size: int
    fn: Callable[[str, Representation | None], int]

    def __call__(self, text: str, rep: Representation | None) -> int:
        return int(min(max(self.fn(text, rep), 0), self.size - 1))


class KeywordTagger:
    """The offline tagging function: keyword counts, nearest tag as a fallback."""

    __slots__ = ("_bags", "_encoder", "_matrix", "axis", "vocabulary")

    def __init__(
        self,
        axis: str,
        *,
        bags: Mapping[str, Sequence[str]] | None = None,
        encoder: Encoder | None = None,
    ) -> None:
        table = vocabularies()["tags"][axis] if bags is None else bags
        self.axis = axis
        self.vocabulary = tuple(table)
        self._bags = tuple(tuple(k.lower() for k in table[tag]) for tag in self.vocabulary)
        self._encoder = encoder or HashEncoder()
        self._matrix: np.ndarray | None = None

    @classmethod
    def for_vocabulary(
        cls, vocabulary: Sequence[str], *, encoder: Encoder | None = None
    ) -> KeywordTagger:
        """Keyword tagger for whichever axis has this closed vocabulary."""
        axis = axis_for_vocabulary(vocabulary)
        if axis in vocabularies()["tags"]:
            return cls(axis, encoder=encoder)
        return cls(axis, bags={tag: [tag] for tag in vocabulary}, encoder=encoder)

    def index(self, text: str) -> int:
        low = text.lower()
        scores = [sum(low.count(kw) for kw in bag) for bag in self._bags]
        best = max(scores)
        if best > 0:
            return scores.index(best)
        return self._nearest(text)

    def __call__(self, text: str, vocabulary: Sequence[str] | None = None) -> str:
        return self.vocabulary[self.index(text)]

    def _nearest(self, text: str) -> int:
        if self._matrix is None:
            self._matrix = self._encoder.encode([" ".join(bag) for bag in self._bags])
        vec = self._encoder.encode([text])[0]
        sims = self._matrix @ vec
        return int(np.argmax(sims))


TAGGER_TEMPLATE = """Assign exactly one label to the text below.

<axis>
{{AXIS}}
</axis>

<labels>
{{LABELS}}
</labels>

<text>
{{TEXT}}
</text>

Answer with one label, copied exactly from the list above, and nothing else.
"""

RETRY_TEMPLATE = """Your previous answer to this task was {{ANSWER}}, which is
not one of the labels. The labels are the only admissible answers.

<axis>
{{AXIS}}
</axis>

<labels>
{{LABELS}}
</labels>

<text>
{{TEXT}}
</text>

Answer with one label, copied exactly from the list above, and nothing else.
"""


def _normalise_tag(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def parse_tag(answer: str, vocabulary: Sequence[str]) -> str | None:
    """Recover the vocabulary member a tagging answer names, or None."""
    by_norm = {_normalise_tag(tag): tag for tag in vocabulary}
    cleaned = answer.strip().strip("`").strip()
    fragments = [cleaned, *cleaned.splitlines()]
    fragments += [frag.split(":", 1)[1] for frag in list(fragments) if ":" in frag]
    for fragment in fragments:
        hit = by_norm.get(_normalise_tag(fragment))
        if hit is not None:
            return hit
    padded = f"-{_normalise_tag(cleaned)}-"
    named = [tag for norm, tag in by_norm.items() if norm and f"-{norm}-" in padded]
    return named[0] if len(named) == 1 else None


class LLMTagger:
    """The paper's tagging function: one closed-vocabulary model call per tag."""

    __slots__ = (
        "_cache",
        "_encoder",
        "_keyword",
        "backend",
        "calls",
        "fallbacks",
        "max_chars",
        "params",
        "retries",
        "retry_template",
        "role",
        "seed",
        "template",
    )

    def __init__(
        self,
        backend: Any,
        *,
        template: str | None = None,
        retry_template: str | None = None,
        params: DecodingParams | None = None,
        encoder: Encoder | None = None,
        seed: int = 0,
        role: str = "tagger",
        max_chars: int = 4000,
    ) -> None:
        self.backend = backend
        self.template = template or TAGGER_TEMPLATE
        self.retry_template = retry_template or RETRY_TEMPLATE
        self.params = params or DecodingParams(temperature=0.0, max_tokens=16)
        self.seed = int(seed)
        self.role = role
        self.max_chars = int(max_chars)
        self._encoder = encoder
        self._keyword: dict[str, KeywordTagger] = {}
        self._cache: dict[tuple[str, str], str] = {}
        self.calls = 0
        self.retries = 0
        self.fallbacks = 0

    def __call__(self, text: str, vocabulary: Sequence[str]) -> str:
        vocab = tuple(vocabulary)
        axis = axis_for_vocabulary(vocab)
        key = (axis, hashlib.sha256(text.encode("utf-8")).hexdigest())
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        answer = self._ask(self.template, axis, vocab, text)
        tag = parse_tag(answer, vocab)
        if tag is None:
            self.retries += 1
            answer = self._ask(self.retry_template, axis, vocab, text, rejected=answer)
            tag = parse_tag(answer, vocab)
        if tag is None:
            self.fallbacks += 1
            tag = self._keyword_tagger(vocab)(text)
        self._cache[key] = tag
        return tag

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def stats(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "retries": self.retries,
            "fallbacks": self.fallbacks,
            "cached": len(self._cache),
        }

    def _ask(
        self,
        template: str,
        axis: str,
        vocabulary: Sequence[str],
        text: str,
        *,
        rejected: str = "",
    ) -> str:
        prompt = (
            template.replace("{{AXIS}}", axis.replace("_", " "))
            .replace("{{LABELS}}", "\n".join(vocabulary))
            .replace("{{TEXT}}", text.strip()[: self.max_chars])
            .replace("{{ANSWER}}", json.dumps(rejected.strip()[:120]))
        )
        gen = self.backend.generate(prompt, self.params, seed=self.seed, role=self.role)
        self.calls += 1
        return gen.text

    def _keyword_tagger(self, vocabulary: Sequence[str]) -> KeywordTagger:
        axis = axis_for_vocabulary(vocabulary)
        tagger = self._keyword.get(axis)
        if tagger is None:
            tagger = KeywordTagger.for_vocabulary(vocabulary, encoder=self._encoder)
            self._keyword[axis] = tagger
        return tagger


class TagAxis:
    """Closed-vocabulary tag, from the injected tagger or the keyword table."""

    __slots__ = ("_keyword", "name", "tagger", "vocabulary")

    def __init__(
        self,
        name: str,
        *,
        tagger: Tagger | None = None,
        encoder: Encoder | None = None,
    ) -> None:
        self.name = name
        self._keyword = KeywordTagger(name, encoder=encoder)
        self.vocabulary = self._keyword.vocabulary
        self.tagger = tagger

    @property
    def size(self) -> int:
        return len(self.vocabulary)

    def __call__(self, text: str, rep: Representation | None) -> int:
        if self.tagger is not None:
            tag = self.tagger(text, self.vocabulary)
            if tag not in self.vocabulary:
                raise ValueError(
                    f"tagger returned {tag!r}, which is not in the closed "
                    f"vocabulary for axis {self.name!r}"
                )
            return self.vocabulary.index(tag)
        return self._keyword.index(text)


class AnchorAxis:
    """Semantic cluster: nearest of a fixed set of anchor passages under cosine."""

    __slots__ = ("_encoder", "_matrix", "labels", "name")

    def __init__(self, name: str, *, encoder: Encoder | None = None) -> None:
        anchors = vocabularies()["anchors"][name]
        self.name = name
        self.labels = tuple(anchors)
        self._encoder = encoder or HashEncoder()
        self._matrix = self._encoder.encode([anchors[k] for k in self.labels])

    @property
    def size(self) -> int:
        return len(self.labels)

    def __call__(self, text: str, rep: Representation | None) -> int:
        vec = self._encoder.encode([text])[0]
        return int(np.argmax(self._matrix @ vec))


@dataclass(frozen=True, slots=True)
class GridDescriptor:
    name: str
    axes: tuple[Axis, ...]

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(axis.size for axis in self.axes)

    @property
    def n_cells(self) -> int:
        return math.prod(self.shape)

    def __call__(
        self, candidate_text: str, representation: Representation | None = None
    ) -> tuple[int, ...]:
        return tuple(axis(candidate_text, representation) for axis in self.axes)

    def cell_index(self, desc: Sequence[int]) -> int:
        return flat_index(desc, self.shape)


class EmbeddingDescriptor:
    """Encoder + PCA + quantile binning, fitted online on the candidates seen."""

    __slots__ = (
        "_basis",
        "_cuts",
        "_encoder",
        "_fitted_at",
        "_mean",
        "_scale",
        "_seen",
        "bins",
        "components",
        "min_fit",
        "name",
        "refit_every",
    )

    def __init__(
        self,
        name: str,
        *,
        bins: int = 5,
        components: int = 2,
        refit_every: int = 8,
        min_fit: int = 4,
        encoder: Encoder | None = None,
    ) -> None:
        if components > 4:
            raise ValueError("the paper projects to d <= 4")
        self.name = name
        self.bins = int(bins)
        self.components = int(components)
        self.refit_every = int(refit_every)
        self.min_fit = max(int(min_fit), components + 1)
        self._encoder = encoder or HashEncoder()
        self._seen: list[np.ndarray] = []
        self._mean: np.ndarray | None = None
        self._basis: np.ndarray | None = None
        self._scale: np.ndarray | None = None
        self._cuts = norm.ppf(np.arange(1, self.bins) / self.bins)
        self._fitted_at = 0

    @property
    def shape(self) -> tuple[int, ...]:
        return (self.bins,) * self.components

    @property
    def n_cells(self) -> int:
        return self.bins**self.components

    @property
    def n_seen(self) -> int:
        return len(self._seen)

    def __call__(
        self, candidate_text: str, representation: Representation | None = None
    ) -> tuple[int, ...]:
        vec = self._encoder.encode([candidate_text])[0]
        self._seen.append(vec)
        if len(self._seen) >= self.min_fit and (
            self._basis is None or len(self._seen) - self._fitted_at >= self.refit_every
        ):
            self._fit()
        if self._basis is None:
            middle = self.bins // 2
            return (middle,) * self.components
        z = (vec - self._mean) @ self._basis / self._scale
        return tuple(int(np.searchsorted(self._cuts, zi)) for zi in z)

    def cell_index(self, desc: Sequence[int]) -> int:
        return flat_index(desc, self.shape)

    def _fit(self) -> None:
        matrix = np.vstack(self._seen)
        self._mean = matrix.mean(axis=0)
        centred = matrix - self._mean
        _, sv, vt = np.linalg.svd(centred, full_matrices=False)
        k = self.components
        basis = vt[:k].T
        for j in range(basis.shape[1]):
            column = basis[:, j]
            if column[int(np.argmax(np.abs(column)))] < 0:
                basis[:, j] = -column
        self._basis = basis
        scale = sv[:k] / math.sqrt(max(len(self._seen) - 1, 1))
        self._scale = np.where(scale > 1e-12, scale, 1.0)
        self._fitted_at = len(self._seen)


def flat_index(desc: Sequence[int], shape: Sequence[int]) -> int:
    """Row-major index of a descriptor cell."""
    if len(desc) != len(shape):
        raise ValueError(f"descriptor {tuple(desc)} does not fit grid shape {tuple(shape)}")
    index = 0
    for value, size in zip(desc, shape, strict=False):
        if not 0 <= value < size:
            raise ValueError(f"descriptor {tuple(desc)} out of range for shape {tuple(shape)}")
        index = index * size + int(value)
    return index


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def code_block(text: str) -> str:
    match = _CODE_FENCE.search(text)
    return match.group(1) if match else text


def step_count(text: str) -> int:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return len(lines)
    return len(re.findall(r"[.;]\s", text)) + 1


def loop_nesting(code: str) -> int:
    """Maximum nesting of loop headers, by indentation."""
    stack: list[int] = []
    best = 0
    for line in code.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        while stack and indent <= stack[-1]:
            stack.pop()
        if _LOOP.match(line):
            stack.append(indent)
            best = max(best, len(stack))
    return best


def is_recursive(code: str) -> bool:
    """A function that calls itself."""
    try:
        tree = ast.parse(textwrap.dedent(code))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return _textual_self_call(code)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == node.name
            ):
                return True
    return False


def _textual_self_call(code: str) -> bool:
    """`is_recursive` for candidates that do not parse: indentation for scope."""
    lines = code.splitlines()
    for i, line in enumerate(lines):
        match = _DEF.match(line)
        if not match:
            continue
        name = match.group(1)
        header = len(line) - len(line.lstrip())
        for body in lines[i + 1 :]:
            if not body.strip():
                continue
            if len(body) - len(body.lstrip()) <= header:
                break
            if re.search(rf"\b{re.escape(name)}\s*\(", body):
                return True
    return False


def indent_depth(code: str) -> int:
    depths = [
        (len(line) - len(line.lstrip())) // 4
        for line in code.splitlines()
        if line.strip()
    ]
    return max(depths) if depths else 0


def paren_depth(text: str) -> int:
    depth = best = 0
    for ch in text:
        if ch == "(":
            depth += 1
            best = max(best, depth)
        elif ch == ")":
            depth = max(0, depth - 1)
    return best


def type_token_ratio(text: str) -> float:
    toks = words(text)
    return len(set(toks)) / len(toks) if toks else 0.0


def marker_score(text: str, positive: Sequence[str], negative: Sequence[str]) -> int:
    low = text.lower()
    return sum(low.count(p) for p in positive) - sum(low.count(n) for n in negative)


def frame_deviation(text: str, rep: Representation | None) -> float:
    """1 - fraction of the frame's keywords the candidate mentions."""
    if rep is None:
        return 1.0
    keywords = frame_keywords().get(rep.frame, ())
    if not keywords:
        return 1.0
    low = text.lower()
    hits = sum(1 for kw in keywords if kw in low)
    return 1.0 - hits / len(keywords)


@functools.lru_cache(maxsize=1)
def frame_keywords() -> Mapping[str, tuple[str, ...]]:
    raw = json.loads((ASSET_DIR / "frames.json").read_text(encoding="utf-8"))["frames"]
    return {
        name: tuple(k.lower() for k in spec.get("keywords", ()))
        for name, spec in raw.items()
    }


def _bin(value: float, edges: Sequence[float]) -> int:
    return int(np.searchsorted(np.asarray(edges, dtype=np.float64), value, side="right"))


def _length_axis() -> BinAxis:
    return BinAxis("length_bin", 4, lambda t, _r: _bin(len(words(t)), (60, 150, 350)))


def _depth_axis(size: int, edges: Sequence[float]) -> BinAxis:
    return BinAxis("depth_bin", size, lambda t, _r: _bin(step_count(t), edges))


def _complexity_axis() -> BinAxis:
    def fn(text: str, _rep: Representation | None) -> int:
        code = code_block(text)
        return loop_nesting(code) + int(is_recursive(code))

    return BinAxis("complexity_class", 4, fn)


def _control_flow_axis() -> BinAxis:
    def fn(text: str, _rep: Representation | None) -> int:
        code = code_block(text)
        lines = code.splitlines()
        has_loop = any(_LOOP.match(line) for line in lines)
        has_branch = any(_BRANCH.match(line) for line in lines)
        return int(has_loop) + 2 * int(has_branch) + 4 * int(is_recursive(code))

    return BinAxis("ctrl_flow", 8, fn)


def _rubric_axes() -> tuple[BinAxis, ...]:
    markers = vocabularies()["markers"]["flexibility"]

    def originality(text: str, _rep: Representation | None) -> int:
        return _bin(type_token_ratio(text), (0.35, 0.50, 0.65, 0.80))

    def elaboration(text: str, _rep: Representation | None) -> int:
        return _bin(len(words(text)), (40, 120, 300))

    def flexibility(text: str, _rep: Representation | None) -> int:
        low = text.lower()
        return _bin(sum(1 for m in markers if m in low), (1, 3))

    return (
        BinAxis("originality", 5, originality),
        BinAxis("elaboration", 4, elaboration),
        BinAxis("flexibility", 3, flexibility),
    )


def _feasibility_axis() -> BinAxis:
    markers = vocabularies()["markers"]

    def fn(text: str, _rep: Representation | None) -> int:
        score = marker_score(
            text, markers["feasibility_positive"], markers["feasibility_negative"]
        )
        return _bin(score, (-2, -1, 0, 1))

    return BinAxis("feasibility", 5, fn)


def _builders() -> dict[str, Callable[[Tagger | None, Encoder | None], Descriptor]]:
    def synthetic(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        """Grid for the offline synthetic dataset."""
        return GridDescriptor(
            "synthetic",
            (TagAxis("math_method", tagger=tagger, encoder=encoder), _length_axis()),
        )

    def math500(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor(
            "math500",
            (TagAxis("math_method", tagger=tagger, encoder=encoder), _length_axis()),
        )

    def aime(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor(
            "aime",
            (
                TagAxis("math_method", tagger=tagger, encoder=encoder),
                _depth_axis(3, (4, 10)),
            ),
        )

    def usamo(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return EmbeddingDescriptor("usamo", bins=5, components=2, encoder=encoder)

    def livecodebench(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor(
            "livecodebench",
            (TagAxis("alg_class", tagger=tagger, encoder=encoder), _complexity_axis()),
        )

    def humaneval_plus(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor(
            "humaneval_plus",
            (
                _control_flow_axis(),
                BinAxis(
                    "indent_depth", 5, lambda t, _r: indent_depth(code_block(t))
                ),
            ),
        )

    def noveltybench(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor(
            "noveltybench",
            (
                TagAxis("response_tag", tagger=tagger, encoder=encoder),
                AnchorAxis("semantic_cluster", encoder=encoder),
            ),
        )

    def creativityprism(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor("creativityprism", _rubric_axes())

    def uot(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor(
            "uot",
            (
                BinAxis(
                    "frame_deviation",
                    6,
                    lambda t, r: _bin(frame_deviation(t, r), (0.2, 0.4, 0.6, 0.8, 0.999)),
                ),
                _feasibility_axis(),
            ),
        )

    def llmsrbench(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor(
            "llmsrbench",
            (
                TagAxis("operator_skeleton", tagger=tagger, encoder=encoder),
                BinAxis("expression_depth", 4, lambda t, _r: paren_depth(t)),
            ),
        )

    def researchbench(tagger: Tagger | None, encoder: Encoder | None) -> Descriptor:
        return GridDescriptor(
            "researchbench",
            (
                TagAxis("inspiration_category", tagger=tagger, encoder=encoder),
                TagAxis("field", tagger=tagger, encoder=encoder),
            ),
        )

    return {
        "synthetic": synthetic,
        "math500": math500,
        "aime": aime,
        "usamo": usamo,
        "livecodebench": livecodebench,
        "humaneval_plus": humaneval_plus,
        "noveltybench": noveltybench,
        "creativityprism": creativityprism,
        "uot": uot,
        "llmsrbench": llmsrbench,
        "researchbench": researchbench,
    }


def available() -> tuple[str, ...]:
    return tuple(sorted(_builders()))


def get_descriptor(
    benchmark: str,
    *,
    tagger: Tagger | None = None,
    encoder: Encoder | None = None,
) -> Descriptor:
    """A fresh descriptor for `benchmark`; embedding descriptors carry state."""
    builders = _builders()
    if benchmark not in builders:
        raise KeyError(f"no descriptor for benchmark {benchmark!r}; have {available()}")
    return builders[benchmark](tagger, encoder)
