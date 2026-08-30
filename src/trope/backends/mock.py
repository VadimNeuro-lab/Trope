"""Deterministic offline backend."""

from __future__ import annotations

import itertools
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from trope.backends.base import (
    DecodingParams,
    Generation,
    ScoreResult,
    _stable_hash,
)
from trope.config import ASSET_DIR
from trope.data.base import Problem

_WORD = re.compile(r"[A-Za-z_]+|\d+|[^\sA-Za-z_\d]")
_TAG = re.compile(r"<(?P<tag>[a-z_]+)>(?P<body>.*?)</(?P=tag)>", re.DOTALL)


def tokenise(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(text)]


def extract_tag(prompt: str, tag: str) -> str:
    for match in _TAG.finditer(prompt):
        if match.group("tag") == tag:
            return match.group("body").strip()
    return ""


class CacheBigramLM:
    """Interpolated bigram LM with a unigram cache over the conditioning prefix."""

    def __init__(self, background: str, *, mix: float = 0.35, floor: float = 1e-7) -> None:
        self.mix = float(mix)
        self.floor = float(floor)
        tokens = tokenise(background)
        if len(tokens) < 2:
            raise ValueError("background text is too short for a bigram model")
        self.unigram: Counter[str] = Counter(tokens)
        self.bigram: dict[str, Counter[str]] = defaultdict(Counter)
        for a, b in itertools.pairwise(tokens):
            self.bigram[a][b] += 1
        self.total = float(sum(self.unigram.values()))
        self.vocab = len(self.unigram) + 1

    def _base_logprob(self, prev: str, word: str) -> float:
        uni = (self.unigram.get(word, 0) + 1.0) / (self.total + self.vocab)
        row = self.bigram.get(prev)
        if row:
            row_total = float(sum(row.values()))
            bi = (row.get(word, 0) + 1.0) / (row_total + self.vocab)
            p = 0.6 * bi + 0.4 * uni
        else:
            p = uni
        return max(p, self.floor)

    def _cache(self, prefix_tokens: Sequence[str]) -> tuple[dict[str, float], float]:
        if not prefix_tokens:
            return {}, 0.0
        counts = Counter(prefix_tokens)
        total = float(sum(counts.values())) + self.vocab * 0.01
        table = {w: (c + 0.01) / total for w, c in counts.items()}
        return table, 0.01 / total

    def logprob(self, continuation: Sequence[str], prefix: Sequence[str]) -> np.ndarray:
        table, unseen = self._cache(prefix)
        mix = self.mix if table else 0.0
        out = np.empty(len(continuation), dtype=np.float64)
        prev = "<s>"
        for i, word in enumerate(continuation):
            p = (1.0 - mix) * self._base_logprob(prev, word)
            if mix:
                p += mix * table.get(word, unseen)
            out[i] = math.log(max(p, self.floor))
            prev = word
        return out


@dataclass(frozen=True, slots=True)
class _Unlock:
    frame: str
    entity_index: int
    target_type: str
    needs_negation: bool
    base_rate: float


class MockBackend:
    name = "mock"

    def __init__(
        self,
        problems: Iterable[Problem] | None = None,
        *,
        seed: int = 0,
        parser_failure_rate: float = 0.03,
        background: str | None = None,
        mix: float = 0.35,
        difficulty: float = 0.30,
    ) -> None:
        self.seed = int(seed)
        self.parser_failure_rate = float(parser_failure_rate)
        self.difficulty = float(difficulty)
        self._by_text: dict[str, Problem] = {}
        for p in problems or ():
            self._by_text[_norm(p.text)] = p
        text = background if background is not None else _default_background()
        self.lm = CacheBigramLM(text, mix=mix)
        self._frames = _load_frames()
        self._frame_names = tuple(sorted(self._frames))

    def generate(
        self,
        prompt: str,
        params: DecodingParams,
        *,
        seed: int | None = None,
        role: str = "generator",
    ) -> Generation:
        rng = self._rng(prompt, seed)
        if role == "parser":
            text = self._parse(prompt, rng)
        elif role == "generator":
            text = self._solve(prompt, params, rng)
        elif role == "judge":
            text = self._judge(prompt, rng)
        else:
            text = self._freeform(prompt, rng)
        return Generation(
            text=text,
            prompt_tokens=self.count_tokens(prompt),
            completion_tokens=self.count_tokens(text),
            meta={"role": role, "backend": "mock"},
        )

    def _rng(self, prompt: str, seed: int | None) -> np.random.Generator:
        key = (_stable_hash(prompt) ^ (self.seed * 0x9E3779B1)) & 0xFFFFFFFF
        if seed is not None:
            key ^= (int(seed) * 0x85EBCA6B) & 0xFFFFFFFF
        return np.random.default_rng(key)

    def _parse(self, prompt: str, rng: np.random.Generator) -> str:
        text = extract_tag(prompt, "problem") or prompt
        attempt = prompt.count("<validator_error>")
        if attempt == 0 and rng.random() < self.parser_failure_rate:
            return '{"entities": [{"id": "x", "type": "quantum"}], "goal":'
        rep = self._representation_for(text)
        return "```json\n" + json.dumps(rep, indent=1) + "\n```"

    def _representation_for(self, text: str) -> dict:
        words = tokenise(text)
        frame = self._detect_frame(words)
        spec = self._frames[frame]
        sorts = spec.get("sorts") or ["quantity"]
        names = _candidate_names(text)
        h = _stable_hash(_norm(text))
        roles = ("variable", "parameter", "constant", "input", "output", "coordinate")
        entities = []
        for i, name in enumerate(names):
            entities.append(
                {
                    "id": name,
                    "type": roles[(h + i * 7) % len(roles)],
                    "sort": sorts[(h + i * 3) % len(sorts)],
                    "label": name,
                }
            )
        relations = []
        for i in range(len(entities) - 1):
            relations.append(
                {
                    "src": entities[i]["id"],
                    "dst": entities[i + 1]["id"],
                    "rtype": ("depends_on", "constrains", "part_of", "relates")[
                        (h + i) % 4
                    ],
                }
            )
        axioms = spec.get("axioms") or []
        assumptions = [
            {"text": a["text"], "load_bearing": bool(a.get("depends_on")), "negated": False}
            for a in axioms[:3]
        ]
        assumptions.append(
            {"text": f"the statement of {names[0]} is exact as given", "load_bearing": False}
        )
        if not any(a["load_bearing"] for a in assumptions):
            assumptions[0]["load_bearing"] = True
        return {
            "entities": entities,
            "relations": relations,
            "assumptions": assumptions,
            "goal": {"objective": _goal_sentence(text), "constraint": ""},
            "frame": frame,
        }

    def _detect_frame(self, words: Sequence[str]) -> str:
        bag = Counter(words)
        best, best_score = "unspecified", 0.0
        for name in self._frame_names:
            keys = self._frames[name].get("keywords") or []
            score = 0.0
            for key in keys:
                parts = tokenise(key)
                score += min(bag[p] for p in parts) if parts else 0
            if score > best_score:
                best, best_score = name, score
        return best

    def _solve(
        self, prompt: str, params: DecodingParams, rng: np.random.Generator
    ) -> str:
        text = extract_tag(prompt, "problem")
        problem = self._by_text.get(_norm(text))
        rep = _safe_json(extract_tag(prompt, "representation"))
        unlock = self._unlock_for(text)
        score = unlock.base_rate
        if rep:
            if rep.get("frame") == unlock.frame:
                score += 0.30
            ents = rep.get("entities") or []
            if ents:
                idx = unlock.entity_index % len(ents)
                if ents[idx].get("type") == unlock.target_type:
                    score += 0.22
            negated = any(
                a.get("negated") and a.get("load_bearing")
                for a in rep.get("assumptions") or []
            )
            if negated == unlock.needs_negation:
                score += 0.16
            if len(rep.get("history") or []) > 3:
                score -= 0.05
        score += 0.05 * (params.temperature - 0.7)
        solved = bool(rng.random() < min(max(score, 0.01), 0.95))
        answer = (problem.answer if problem else None) or "42"
        if problem is not None and problem.family == "code":
            return _code_answer(problem, solved)
        head = _reasoning_sketch(rep, rng)
        if solved:
            return f"{head}\nTherefore the answer is \\boxed{{{answer}}}."
        wrong = _perturb(answer, rng)
        return f"{head}\nTherefore the answer is \\boxed{{{wrong}}}."

    def _unlock_for(self, text: str) -> _Unlock:
        h = _stable_hash(_norm(text))
        roles = ("variable", "parameter", "constant", "input", "output", "coordinate")
        return _Unlock(
            frame=self._frame_names[h % len(self._frame_names)],
            entity_index=(h >> 8) % 8,
            target_type=roles[(h >> 16) % len(roles)],
            needs_negation=bool((h >> 24) & 1),
            base_rate=self.difficulty * (0.5 + ((h >> 32) % 100) / 100.0),
        )

    def _judge(self, prompt: str, rng: np.random.Generator) -> str:
        body = extract_tag(prompt, "candidate") or prompt
        hits = sum(body.lower().count(w) for w in ("therefore", "hence", "since", "because"))
        verdict = hits >= 2 and "boxed" in body.lower()
        if rng.random() < 0.05:
            verdict = not verdict
        return json.dumps({"correct": bool(verdict), "score": 1.0 if verdict else 0.0})

    def _freeform(self, prompt: str, rng: np.random.Generator) -> str:
        words = tokenise(extract_tag(prompt, "problem") or prompt)[:24]
        pick = rng.permutation(len(words))[: min(12, len(words))]
        return " ".join(words[i] for i in sorted(pick)) or "ok"

    def score(self, continuation: str, prefix: str = "") -> ScoreResult:
        cont = tokenise(continuation)
        if not cont:
            return ScoreResult(0.0, 0, np.zeros(0))
        lp = self.lm.logprob(cont, tokenise(prefix))
        return ScoreResult(float(lp.sum()), len(cont), lp)

    def count_tokens(self, text: str) -> int:
        return len(tokenise(text))


def _norm(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _safe_json(blob: str) -> dict:
    blob = blob.strip()
    if blob.startswith("```"):
        blob = blob.strip("`")
        blob = blob.split("\n", 1)[-1] if "\n" in blob else blob
    try:
        out = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


_STOPWORDS = frozenset(
    """that this with from have been they them then than there where which
    such each also into your will been being does done more most some many
    when what while these those over under about
    """.split()
)


def _candidate_names(text: str) -> list[str]:
    """Pick plausible entity names: short identifiers, then salient nouns."""
    ids = re.findall(r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])", text)
    words = [w for w in re.findall(r"[A-Za-z]{4,}", text) if w.lower() not in _STOPWORDS]
    seen: list[str] = []
    for name in ids + [w.lower() for w in words]:
        if name not in seen:
            seen.append(name)
        if len(seen) >= 6:
            break
    return seen or ["x"]


def _goal_sentence(text: str) -> str:
    for sentence in re.split(r"(?<=[.?])\s+", text.strip()):
        low = sentence.lower()
        if any(k in low for k in ("find", "prove", "compute", "return", "determine")):
            return sentence.strip()[:200]
    return text.strip()[:200] or "solve the problem"


def _reasoning_sketch(rep: Mapping, rng: np.random.Generator) -> str:
    frame = rep.get("frame", "unspecified") if rep else "unspecified"
    steps = int(rng.integers(2, 5))
    lines = [f"Working in the {frame} frame."]
    for i in range(steps):
        lines.append(f"Step {i + 1}: since the constraints hold, the quantity reduces.")
    return "\n".join(lines)


def _perturb(answer: str, rng: np.random.Generator) -> str:
    if answer.lstrip("-").isdigit():
        return str(int(answer) + int(rng.integers(1, 9)))
    return answer + "'"


def _code_answer(problem: Problem, solved: bool) -> str:
    name = problem.entry_point or "solve"
    body = problem.answer or "    return None"
    if not solved:
        body = "    raise ValueError('unsolved')"
    if not body.lstrip().startswith(("def ", "class ", "import ", "from ")):
        code = f"def {name}(*args, **kwargs):\n{body}"
    else:
        code = body
    return f"```python\n{code}\n```"


_FRAMES_CACHE: dict | None = None


def _load_frames() -> dict:
    global _FRAMES_CACHE
    if _FRAMES_CACHE is None:
        blob = json.loads((ASSET_DIR / "frames.json").read_text(encoding="utf-8"))
        _FRAMES_CACHE = blob["frames"]
    return _FRAMES_CACHE


def _default_background() -> str:
    path = ASSET_DIR / "mock_background.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return " ".join(
        " ".join(spec.get("keywords", []) + [a["text"] for a in spec.get("axioms", [])])
        for spec in _load_frames().values()
    )
