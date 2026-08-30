"""Exact-match verification for benchmarks with a short gold answer."""

from __future__ import annotations

import re
from typing import Any

from trope.data.base import Problem
from trope.verify.base import Verdict, at_least

DEFAULT_TOLERANCE = 1e-6

_NUMBER = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?")
_ANSWER_CUE = re.compile(
    r"(?:the\s+)?(?:final\s+)?answer\s*(?:is|:|=)\s*", re.IGNORECASE
)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d\d\d(?!\d))")
_TEXT_WRAPPER = re.compile(
    r"\\(?:text|textbf|textit|textrm|mbox|mathrm|mathbf|mathit)\s*\{([^{}]*)\}"
)
_FRAC = re.compile(r"\\[dt]?frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
_FRAC_TERSE = re.compile(r"\\[dt]?frac\s*(-?\d)\s*(\d)")
_SUPERSUB = re.compile(r"([_^])\{([^{}]+)\}")
_PLAIN_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_SPACING = (
    "\\left",
    "\\right",
    "\\displaystyle",
    "\\limits",
    "\\quad",
    "\\qquad",
    "\\!",
    "\\,",
    "\\;",
    "\\:",
    "\\ ",
    "\\$",
    "$",
    "\\%",
    "%",
)


def boxed_answers(text: str) -> list[str]:
    """Contents of every ``\\boxed{...}``, outermost braces stripped."""
    out: list[str] = []
    for match in re.finditer(r"\\boxed\s*", text):
        i = match.end()
        if i >= len(text):
            continue
        if text[i] != "{":
            out.append(text[i])
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "{" and (j == 0 or text[j - 1] != "\\"):
                depth += 1
            elif text[j] == "}" and text[j - 1] != "\\":
                depth -= 1
                if depth == 0:
                    out.append(text[i + 1 : j])
                    break
    return out


def _cue_span(text: str) -> str | None:
    matches = list(_ANSWER_CUE.finditer(text))
    if not matches:
        return None
    tail = text[matches[-1].end() :]
    stop = len(tail)
    for pattern in (r"\.\s", r"\n"):
        found = re.search(pattern, tail)
        if found:
            stop = min(stop, found.start())
    span = tail[:stop].strip().rstrip(".").strip()
    return span or None


def extract_answer(text: str) -> str | None:
    """The candidate's final answer, or None when it never states one."""
    if not text:
        return None
    boxed = boxed_answers(text)
    if boxed:
        return boxed[-1].strip() or None
    cue = _cue_span(text)
    if cue:
        return cue
    for match in reversed(list(_NUMBER.finditer(text))):
        if _HEDGED.search(text[max(0, match.start() - 24) : match.start()].lower()):
            return None
        return match.group(0)
    return None


def _unwrap(text: str) -> str:
    """Remove one balanced bracket pair that encloses the entire string."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    if len(text) < 2 or text[0] not in pairs or text[-1] != pairs[text[0]]:
        return text
    depth = 0
    for i, ch in enumerate(text):
        if ch in pairs:
            depth += 1
        elif ch in pairs.values():
            depth -= 1
            if depth == 0 and i != len(text) - 1:
                return text
    return text[1:-1].strip()


def _canonical_numbers(text: str) -> str:
    """Rewrite numeric literals in canonical form: 007 -> 7, 2.50 -> 2.5."""

    def repl(match: re.Match[str]) -> str:
        raw = match.group(0).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            return match.group(0)
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return repr(value)

    return _NUMBER.sub(repl, text)


def normalise_answer(answer: str) -> str:
    """Strip LaTeX packaging and unify fraction / numeral spellings."""
    out = answer.strip()
    for token in _SPACING:
        out = out.replace(token, "")
    for _ in range(4):
        new = _TEXT_WRAPPER.sub(r"\1", out)
        if new == out:
            break
        out = new
    for _ in range(4):
        new = _FRAC.sub(_frac_repl, out)
        new = _FRAC_TERSE.sub(r"\1/\2", new)
        if new == out:
            break
        out = new
    out = _SUPERSUB.sub(r"\1\2", out)
    out = _THOUSANDS.sub("", out)
    out = _canonical_numbers(out)
    out = " ".join(out.split())
    out = out.rstrip(".").strip()
    for _ in range(4):
        stripped = _unwrap(out)
        if stripped == out:
            break
        out = stripped
    return out


def _frac_repl(match: re.Match[str]) -> str:
    num, den = match.group(1).strip(), match.group(2).strip()
    return f"{_maybe_paren(num)}/{_maybe_paren(den)}"


def _maybe_paren(term: str) -> str:
    if _PLAIN_NUMBER.fullmatch(term) or term.isalpha():
        return term
    return f"({term})"


def parse_number(text: str) -> float | None:
    """Numeric value of a normalised answer, or None if it is not a number."""
    body = text.strip().replace(" ", "").lstrip("+")
    if not body:
        return None
    frac = re.fullmatch(r"(-?\d+(?:\.\d+)?)/(-?\d+(?:\.\d+)?)", body)
    if frac:
        den = float(frac.group(2))
        return float(frac.group(1)) / den if den != 0.0 else None
    try:
        value = float(body)
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


_HEDGED = re.compile(
    r"(?<![a-z])(?:not|isn't|is not|never|approximately|approx|about|around|"
    r"near|nearly|roughly|almost|at least|at most|more than|less than|greater "
    r"than|fewer than|cannot|can't|unable|maybe|perhaps|possibly|unsure)"
    r"(?![a-z])"
)


def answers_match(
    predicted: str, gold: str, *, tolerance: float = DEFAULT_TOLERANCE
) -> bool:
    """Whether a raw predicted answer means the same as the gold answer."""
    pred, want = normalise_answer(predicted), normalise_answer(gold)
    if not pred or not want:
        return False
    if pred.casefold() == want.casefold():
        return True
    if pred.replace(" ", "").casefold() == want.replace(" ", "").casefold():
        return True
    pv, gv = parse_number(pred), parse_number(want)
    if pv is not None and gv is not None:
        return _close(pv, gv, tolerance)
    if gv is not None and not _HEDGED.search(pred):
        found = [parse_number(m.group(0)) for m in _NUMBER.finditer(pred)]
        values = [v for v in found if v is not None]
        if len(values) == 1:
            return _close(values[0], gv, tolerance)
    return False


class ExactMatchVerifier:
    """V_P for benchmarks whose gold is a short answer string."""

    name = "exact_match"

    def __init__(self, *, tolerance: float = DEFAULT_TOLERANCE) -> None:
        self.tolerance = float(tolerance)
        self.verified_predicate = at_least(1.0)

    def __call__(self, problem: Problem, candidate_text: str) -> Verdict:
        gold = problem.answer
        if gold is None:
            return Verdict(0.0, False, "problem carries no gold answer")
        predicted = extract_answer(candidate_text)
        if predicted is None:
            return Verdict(0.0, False, "candidate states no answer")
        ok = answers_match(predicted, gold, tolerance=self.tolerance)
        meta: dict[str, Any] = {
            "extracted": predicted,
            "normalised": normalise_answer(predicted),
            "gold": gold,
        }
        return Verdict(
            1.0 if ok else 0.0,
            ok,
            f"extracted {predicted!r} against gold {gold!r}",
            meta,
        )
