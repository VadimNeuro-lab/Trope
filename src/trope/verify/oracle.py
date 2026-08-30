"""Task oracles for the families with no checkable answer."""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from trope.data.base import Problem
from trope.verify.base import TOLERANCE, Verdict, at_least

DEFAULT_THRESHOLD = 0.5

BENCHMARK_THRESHOLD: dict[str, float] = {"llmsrbench": 1.0}


class UnsafeExpression(ValueError):
    """Raised when an expression uses anything outside the whitelist."""


MATH_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "acos": math.acos,
    "asin": math.asin,
    "atan": math.atan,
    "atan2": math.atan2,
    "ceil": math.ceil,
    "cos": math.cos,
    "cosh": math.cosh,
    "exp": math.exp,
    "floor": math.floor,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "max": max,
    "min": min,
    "sin": math.sin,
    "sinh": math.sinh,
    "sqrt": math.sqrt,
    "tan": math.tan,
    "tanh": math.tanh,
}

MATH_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e, "tau": math.tau}

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
)

_BINOPS: dict[type[ast.AST], Callable[[float, float], float]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}

MAX_EXPRESSION_CHARS = 512


def compile_expression(expr: str) -> tuple[ast.Expression, tuple[str, ...]]:
    """Parse and whitelist-check `expr`; returns the tree and its free variables."""
    if len(expr) > MAX_EXPRESSION_CHARS:
        raise UnsafeExpression(f"expression longer than {MAX_EXPRESSION_CHARS} chars")
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise UnsafeExpression(f"not a parsable expression: {exc}") from exc

    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpression(f"{type(node).__name__} is not allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in MATH_FUNCTIONS:
                raise UnsafeExpression("only whitelisted math functions may be called")
            if node.keywords:
                raise UnsafeExpression("keyword arguments are not allowed")
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                raise UnsafeExpression("only numeric literals are allowed")
        elif isinstance(node, ast.Name):
            if node.id not in MATH_FUNCTIONS and node.id not in MATH_CONSTANTS:
                names.add(node.id)
    return tree, tuple(sorted(names))


def eval_tree(tree: ast.Expression, variables: Mapping[str, float]) -> float:
    """Evaluate a tree that `compile_expression` accepted."""
    return _eval(tree.body, variables)


def _eval(node: ast.AST, env: Mapping[str, float]) -> float:
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in MATH_CONSTANTS:
            return MATH_CONSTANTS[node.id]
        try:
            return float(env[node.id])
        except KeyError:
            raise UnsafeExpression(f"unbound variable {node.id!r}") from None
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, env)
        return -value if isinstance(node.op, ast.USub) else +value
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise UnsafeExpression(f"{type(node.op).__name__} is not allowed")
        return float(op(_eval(node.left, env), _eval(node.right, env)))
    if isinstance(node, ast.Call):
        fn = MATH_FUNCTIONS[node.func.id]  # type: ignore[union-attr]
        return float(fn(*(_eval(a, env) for a in node.args)))
    raise UnsafeExpression(f"{type(node).__name__} is not allowed")


def safe_eval(expr: str, variables: Mapping[str, float]) -> float:
    """Evaluate an untrusted arithmetic expression."""
    tree, _ = compile_expression(expr)
    return eval_tree(tree, variables)


_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def _halton(index: int, base: int) -> float:
    out, f = 0.0, 1.0
    while index > 0:
        f /= base
        out += f * (index % base)
        index //= base
    return out


def halton_grid(
    dim: int, n_points: int, low: float, high: float
) -> tuple[tuple[float, ...], ...]:
    """A deterministic low-discrepancy grid. No RNG: the same points every run."""
    if dim > len(_PRIMES):
        raise ValueError(f"at most {len(_PRIMES)} variables are supported")
    return tuple(
        tuple(
            low + (high - low) * _halton(i + 1, _PRIMES[d])
            for d in range(dim)
        )
        for i in range(n_points)
    )


def symbolic_accuracy(
    predicted: str,
    gold: str,
    *,
    variables: Sequence[str] | None = None,
    n_points: int = 64,
    domain: tuple[float, float] = (0.5, 2.0),
    rtol: float = 1e-6,
) -> tuple[float, str]:
    """Fraction of grid points where the two expressions agree, plus a reason."""
    try:
        gold_tree, gold_names = compile_expression(gold)
    except UnsafeExpression as exc:
        return 0.0, f"gold expression rejected: {exc}"
    try:
        pred_tree, pred_names = compile_expression(predicted)
    except UnsafeExpression as exc:
        return 0.0, f"candidate expression rejected: {exc}"

    names = (
        tuple(variables)
        if variables is not None
        else tuple(sorted(set(gold_names) | set(pred_names)))
    )
    unknown = set(pred_names) - set(names)
    if unknown:
        return 0.0, f"candidate uses unknown symbols {sorted(unknown)}"
    missing = set(gold_names) - set(names)
    if missing:
        return 0.0, f"gold expression uses symbols outside the variable list {sorted(missing)}"

    grid = halton_grid(len(names), n_points, *domain) if names else ((),)
    agree = usable = 0
    for point in grid:
        env = dict(zip(names, point, strict=False))
        try:
            want = eval_tree(gold_tree, env)
            got = eval_tree(pred_tree, env)
        except (ArithmeticError, ValueError, UnsafeExpression):
            continue
        if not (math.isfinite(want) and math.isfinite(got)):
            continue
        usable += 1
        agree += abs(got - want) <= rtol * max(1.0, abs(want), abs(got))
    if usable == 0:
        return 0.0, "no sample point where both expressions evaluate finitely"
    return agree / usable, f"{agree}/{usable} sample points agree"


_FENCE = re.compile(r"```[A-Za-z0-9_+-]*\r?\n(.*?)```", re.DOTALL)


def extract_expression(text: str) -> str | None:
    """The last line of `text` that parses as a whitelisted expression."""
    lines = text.splitlines()
    for block in _FENCE.findall(text):
        lines.extend(block.splitlines())
    constant: str | None = None
    for line in reversed(lines):
        body = line.strip().strip("$").rstrip(".;,").strip()
        if "=" in body:
            body = body.rsplit("=", 1)[1].strip()
        if not body:
            continue
        try:
            _, names = compile_expression(body)
        except UnsafeExpression:
            continue
        if names:
            return body
        constant = constant or body
    return constant


_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_SENTENCE = re.compile(r"[.!?\n]+")

_STOP = frozenset(
    """a an the and or but if then than that this these those of in on at to for
    with from by as is are was were be been being it its it's he she they them we
    you your i not no do does did have has had can could would should will may
    might must about into over under more most some any each such which who whom
    """.split()
)

_FEASIBLE = frozenset(
    "step measure estimate compute build test procedure method observe sample "
    "calibrate protocol experiment implement verify".split()
)
_INFEASIBLE = frozenset(
    "impossible cannot never infeasible unknowable magic paradox violates "
    "unbounded intractable".split()
)


def content_words(text: str) -> list[str]:
    return [w for w in (m.group(0).lower() for m in _WORD.finditer(text)) if w not in _STOP]


def distinct_ratio(text: str) -> float:
    """Type-token ratio over content words; a lexical-diversity proxy."""
    words = content_words(text)
    return len(set(words)) / len(words) if words else 0.0


def rubric_coverage(rubric: str, text: str) -> float:
    """Fraction of the rubric's content words the candidate mentions."""
    wanted = set(content_words(rubric))
    if not wanted:
        return 0.0
    seen = set(content_words(text))
    return len(wanted & seen) / len(wanted)


def sentence_diversity(text: str) -> float:
    """1 - (repeated sentence openings), a crude within-response redundancy check."""
    sentences = [s.strip() for s in _SENTENCE.split(text) if s.strip()]
    if len(sentences) < 2:
        return 0.0
    openings = Counter(s.split()[0].lower() for s in sentences if s.split())
    return 1.0 - (max(openings.values()) - 1) / len(sentences)


def marker_balance(text: str) -> float:
    """Feasible markers against infeasible ones, squashed into [0, 1]."""
    words = Counter(content_words(text))
    good = sum(words[w] for w in _FEASIBLE)
    bad = sum(words[w] for w in _INFEASIBLE)
    return 0.5 + 0.5 * math.tanh((good - bad) / 4.0)


def token_f1(reference: str, text: str) -> float:
    """Multiset token F1, the shape ResearchBench's official metric reports."""
    want, got = Counter(content_words(reference)), Counter(content_words(text))
    if not want or not got:
        return 0.0
    overlap = sum((want & got).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(got.values())
    recall = overlap / sum(want.values())
    return 2 * precision * recall / (precision + recall)


@dataclass(frozen=True, slots=True)
class OracleScore:
    value: float
    detail: str
    stand_in: bool
    meta: dict[str, Any] = field(default_factory=dict)


Scorer = Callable[[Problem, str], OracleScore]

_SCORERS: dict[str, Scorer] = {}


def register_scorer(benchmark: str, fn: Scorer) -> None:
    """Install the official scorer for a benchmark, replacing any stand-in."""
    _SCORERS[benchmark] = fn


def get_scorer(benchmark: str) -> Scorer:
    return _SCORERS.get(benchmark, _generic_stand_in)


def registered_scorers() -> tuple[str, ...]:
    return tuple(sorted(_SCORERS))


def _reference_text(problem: Problem) -> str:
    return problem.rubric or problem.answer or problem.text


def _generic_stand_in(problem: Problem, candidate_text: str) -> OracleScore:
    quality = rubric_coverage(_reference_text(problem), candidate_text)
    value = 0.5 * quality + 0.5 * distinct_ratio(candidate_text)
    return OracleScore(
        value,
        f"stand-in composite (coverage {quality:.2f})",
        True,
        {"components": {"coverage": quality, "distinct": distinct_ratio(candidate_text)}},
    )


def _noveltybench_stand_in(problem: Problem, candidate_text: str) -> OracleScore:
    """Stand-in for cumulative utility: distinctness weighted by on-topic-ness."""
    distinct = distinct_ratio(candidate_text)
    onto = rubric_coverage(_reference_text(problem), candidate_text)
    value = distinct * (0.5 + 0.5 * onto)
    return OracleScore(
        value,
        f"stand-in for cumulative utility (distinct {distinct:.2f})",
        True,
        {"components": {"distinct": distinct, "on_topic": onto}},
    )


def _creativityprism_stand_in(problem: Problem, candidate_text: str) -> OracleScore:
    """Stand-in for the Q-N-D composite: one surface proxy per axis."""
    quality = rubric_coverage(_reference_text(problem), candidate_text)
    novelty = distinct_ratio(candidate_text)
    diversity = sentence_diversity(candidate_text)
    value = (quality + novelty + diversity) / 3.0
    return OracleScore(
        value,
        f"stand-in Q-N-D ({quality:.2f}/{novelty:.2f}/{diversity:.2f})",
        True,
        {"components": {"quality": quality, "novelty": novelty, "diversity": diversity}},
    )


def _uot_stand_in(problem: Problem, candidate_text: str) -> OracleScore:
    """Stand-in for the F-U-N composite: feasibility, utility, novelty proxies."""
    feasibility = marker_balance(candidate_text)
    utility = rubric_coverage(_reference_text(problem), candidate_text)
    novelty = distinct_ratio(candidate_text)
    value = (feasibility + utility + novelty) / 3.0
    return OracleScore(
        value,
        f"stand-in F-U-N ({feasibility:.2f}/{utility:.2f}/{novelty:.2f})",
        True,
        {
            "components": {
                "feasibility": feasibility,
                "utility": utility,
                "novelty": novelty,
            }
        },
    )


def _researchbench_stand_in(problem: Problem, candidate_text: str) -> OracleScore:
    """Token F1 against the gold hypothesis."""
    value = token_f1(_reference_text(problem), candidate_text)
    return OracleScore(value, f"stand-in token F1 {value:.3f}", True, {})


def _llmsrbench_scorer(problem: Problem, candidate_text: str) -> OracleScore:
    """Real symbolic accuracy: pointwise agreement with the gold expression."""
    gold = problem.answer
    if not gold:
        return OracleScore(0.0, "problem carries no gold expression", False, {})
    predicted = extract_expression(candidate_text)
    if predicted is None:
        return OracleScore(0.0, "candidate states no usable expression", False, {})
    meta = problem.metadata or {}
    domain = tuple(meta.get("domain") or (0.5, 2.0))
    variables = meta.get("variables")
    value, detail = symbolic_accuracy(
        predicted,
        gold,
        variables=tuple(variables) if variables else None,
        domain=(float(domain[0]), float(domain[1])),
    )
    return OracleScore(
        value, detail, False, {"expression": predicted, "gold_expression": gold}
    )


for _name, _fn in (
    ("noveltybench", _noveltybench_stand_in),
    ("creativityprism", _creativityprism_stand_in),
    ("uot", _uot_stand_in),
    ("researchbench", _researchbench_stand_in),
    ("llmsrbench", _llmsrbench_scorer),
):
    register_scorer(_name, _fn)


class OracleVerifier:
    """V_P for the non-verifiable families, dispatching on the benchmark name."""

    name = "oracle"

    def __init__(
        self,
        benchmark: str,
        *,
        threshold: float | None = None,
        scorer: Scorer | None = None,
    ) -> None:
        self.benchmark = benchmark
        self.threshold = float(
            threshold
            if threshold is not None
            else BENCHMARK_THRESHOLD.get(benchmark, DEFAULT_THRESHOLD)
        )
        self.scorer = scorer or get_scorer(benchmark)
        self.verified_predicate = at_least(self.threshold)

    def __call__(self, problem: Problem, candidate_text: str) -> Verdict:
        score = self.scorer(problem, candidate_text)
        value = min(max(score.value, 0.0), 1.0)
        return Verdict(
            value,
            value >= self.threshold - TOLERANCE,
            score.detail,
            {"stand_in": score.stand_in, "benchmark": self.benchmark, **score.meta},
        )
