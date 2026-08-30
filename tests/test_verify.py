"""V_P: extraction, execution, judging, oracles -- and the soundness invariant."""

from __future__ import annotations

import ast
import inspect
import json
import time
from pathlib import Path

import pytest

from trope.backends.base import (
    CallCounter,
    Generation,
    MeteredBackend,
    ScoreResult,
)
from trope.data.base import Problem
from trope.data.synthetic import synthetic_dataset
from trope.verify import base as verify_base
from trope.verify.base import Verdict, at_least, get_verifier
from trope.verify.code_exec import CodeExecVerifier, extract_code, run_tests
from trope.verify.exact_match import (
    ExactMatchVerifier,
    answers_match,
    boxed_answers,
    extract_answer,
    normalise_answer,
    parse_number,
)
from trope.verify.judge import (
    DEFAULT_TEMPLATE,
    JudgeVerifier,
    build_judge_prompt,
    parse_judge_verdict,
)
from trope.verify.oracle import (
    OracleVerifier,
    UnsafeExpression,
    compile_expression,
    extract_expression,
    get_scorer,
    halton_grid,
    register_scorer,
    safe_eval,
    symbolic_accuracy,
    token_f1,
)

VERIFY_DIR = Path(verify_base.__file__).resolve().parent


def _problem(**kw) -> Problem:
    base = {
        "id": "p/0",
        "text": "Compute the value.",
        "benchmark": "synthetic",
        "family": "math_answer",
    }
    base.update(kw)
    return Problem(**base)


def test_no_verifier_can_see_the_edited_representation():
    """`Representation` must not be reachable from anything in trope.verify."""
    offenders = []
    for path in sorted(VERIFY_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = {a.name for a in node.names}
                if "Representation" in names or node.module.endswith(
                    ("operators", "operators.base", "buffer", "search")
                ):
                    offenders.append(f"{path.name}: {node.module} {sorted(names)}")
    assert offenders == []


@pytest.mark.parametrize(
    "verifier",
    [
        ExactMatchVerifier(),
        CodeExecVerifier(),
        OracleVerifier("uot"),
    ],
    ids=lambda v: v.name,
)
def test_verifier_call_signature_is_problem_and_text(verifier):
    params = list(inspect.signature(verifier.__call__).parameters)
    assert params == ["problem", "candidate_text"]


def test_get_verifier_dispatches_on_family_and_benchmark():
    assert get_verifier("math500").name == "exact_match"
    assert get_verifier("humaneval_plus").name == "code_exec"
    assert get_verifier("llmsrbench").name == "oracle"
    assert get_verifier(_problem(family="code")).name == "code_exec"
    with pytest.raises(KeyError):
        get_verifier("not_a_benchmark")
    with pytest.raises(ValueError):
        get_verifier("usamo")


def test_every_verifier_exposes_the_archive_predicate():
    for verifier in (ExactMatchVerifier(), CodeExecVerifier(), OracleVerifier("uot")):
        predicate = verifier.verified_predicate
        assert predicate(1.0) is True
        assert predicate(-0.1) is False


def test_at_least_absorbs_float_slack():
    predicate = at_least(1.0)
    assert predicate(1.0 - 1e-12)
    assert not predicate(0.999)


EXACT_CASES = [
    ("The answer is \\boxed{42}.", "42", True),
    ("The answer is \\boxed{42}.", "43", False),
    ("Reasoning...\n\\boxed{\\frac{1}{2}}", "1/2", True),
    ("\\boxed{\\frac{1}{2}}", "0.5", True),
    ("\\boxed{\\dfrac{-1}{2}}", "-0.5", True),
    ("\\boxed{1/2}", "\\frac{1}{2}", True),
    ("\\boxed{1,234}", "1234", True),
    ("\\boxed{1,234,567}", "1234567", True),
    ("\\boxed{2.50}", "2.5", True),
    ("\\boxed{007}", "7", True),
    ("\\boxed{-3}", "-3", True),
    ("\\boxed{-3}", "3", False),
    ("\\boxed{50\\%}", "50", True),
    ("\\boxed{50\\%}", "0.5", False),
    ("\\boxed{\\text{Yes}}", "Yes", True),
    ("\\boxed{\\text{yes}}", "Yes", True),
    ("\\boxed{\\left(1,2\\right)}", "(1,2)", True),
    ("\\boxed{x^{2}}", "x^2", True),
    ("$\\boxed{\\!\\, 12 \\;}$", "12", True),
    ("The answer is $-\\frac{2}{3}$.", "-2/3", True),
    ("The answer is 12 apples.", "12", True),
    ("Therefore the answer is 7. This took 3 steps.", "7", True),
    ("Therefore the answer is 7. This took 3 steps.", "3", False),
    ("First \\boxed{3}, on reflection \\boxed{4}.", "4", True),
    ("First \\boxed{3}, on reflection \\boxed{4}.", "3", False),
    ("The answer is 3 more than 12.", "12", False),
    ("The answer is 5, no wait: \\boxed{6}", "6", True),
    ("I could not solve this.", "5", False),
    ("\\boxed{1 + \\frac{1}{2}}", "1+1/2", True),
]


@pytest.mark.parametrize("raw,gold,expected", EXACT_CASES)
def test_exact_match_table(raw, gold, expected):
    verifier = ExactMatchVerifier()
    verdict = verifier(_problem(answer=gold), raw)
    assert verdict.verified is expected
    assert verdict.value == (1.0 if expected else 0.0)


def test_extraction_prefers_boxed_then_cue_then_last_number():
    assert extract_answer("answer is 5 \\boxed{9}") == "9"
    assert extract_answer("the final answer is 5, obviously") == "5, obviously"
    assert answers_match("5, obviously", "5"), "the one-number fallback should recover it"
    assert extract_answer("no cue here, 1 then 2 then 3") == "3"
    assert extract_answer("") is None
    assert extract_answer("nothing numeric at all") is None


def test_boxed_answers_handles_nesting_and_multiplicity():
    assert boxed_answers("\\boxed{\\frac{1}{2}} and \\boxed{3}") == ["\\frac{1}{2}", "3"]
    assert boxed_answers("\\boxed 5") == ["5"]
    assert boxed_answers("no box") == []


def test_normalisation_is_idempotent():
    for raw in ("\\frac{1}{2}", "$1,234$", "\\text{Yes}", "2.50", "x^{2}"):
        once = normalise_answer(raw)
        assert normalise_answer(once) == once


@pytest.mark.parametrize(
    "text,value",
    [
        ("12", 12.0),
        ("-3.5", -3.5),
        ("1/2", 0.5),
        ("-1/2", -0.5),
        ("1e3", 1000.0),
        ("1/0", None),
        ("x", None),
        ("1/2/3", None),
        ("", None),
    ],
)
def test_parse_number(text, value):
    assert parse_number(text) == value


def test_a_missing_gold_answer_is_not_a_pass():
    verdict = ExactMatchVerifier()(_problem(answer=None), "\\boxed{42}")
    assert verdict.verified is False
    assert "gold" in verdict.detail


def test_tolerance_is_relative_not_absolute():
    assert answers_match("1000000.0000001", "1000000")
    assert not answers_match("1.0001", "1.0")


def _code_problem(tests, entry_point="add") -> Problem:
    return Problem(
        id="c/0",
        text="Write add.",
        benchmark="synthetic",
        family="code",
        tests=tuple(tests),
        entry_point=entry_point,
    )


GOOD = "```python\ndef add(a, b):\n    return a + b\n```"


def test_a_correct_snippet_passes_every_test():
    problem = _code_problem(["assert add(1, 2) == 3", "assert add(0, 0) == 0"])
    verdict = CodeExecVerifier(timeout=20)(problem, GOOD)
    assert verdict.value == 1.0
    assert verdict.verified is True


def test_a_partially_correct_snippet_scores_the_fraction():
    problem = _code_problem(["assert add(1, 2) == 3", "assert add(1, 2) == 4"])
    verdict = CodeExecVerifier(timeout=20)(problem, GOOD)
    assert verdict.value == 0.5
    assert verdict.verified is False
    statuses = [o["status"] for o in verdict.meta["outcomes"]]
    assert statuses == ["pass", "fail"]


def test_a_syntax_error_fails_every_test_without_raising():
    problem = _code_problem(["assert add(1, 2) == 3", "assert add(2, 2) == 4"])
    verdict = CodeExecVerifier(timeout=20)(problem, "```python\ndef add(a, b:\n```")
    assert verdict.value == 0.0
    assert verdict.verified is False
    assert all(o["status"] == "error" for o in verdict.meta["outcomes"])


def test_an_exception_is_an_error_not_a_crash():
    problem = _code_problem(["assert add(1, 0) == 1", "assert add(1, 'x') == 1"])
    verdict = CodeExecVerifier(timeout=20)(problem, GOOD)
    assert verdict.value == 0.5
    assert verdict.meta["outcomes"][1]["status"] == "error"


def test_an_infinite_loop_hits_the_timeout_and_keeps_earlier_results():
    problem = _code_problem(["assert add(1, 1) == 2", "while True:\n    pass"])
    started = time.perf_counter()
    verdict = CodeExecVerifier(timeout=2.0)(problem, GOOD)
    elapsed = time.perf_counter() - started
    assert elapsed < 30.0, "the timeout did not fire"
    statuses = [o["status"] for o in verdict.meta["outcomes"]]
    assert statuses == ["pass", "timeout"]
    assert verdict.value == 0.5
    assert verdict.verified is False


def test_candidate_writes_stay_inside_the_temp_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    code = (
        "```python\n"
        "def add(a, b):\n"
        "    with open('escape.txt', 'w', encoding='utf-8') as fh:\n"
        "        fh.write('x')\n"
        "    return a + b\n"
        "```"
    )
    problem = _code_problem(["assert add(1, 2) == 3"])
    verdict = CodeExecVerifier(timeout=20)(problem, code)
    assert isinstance(verdict, Verdict)
    assert verdict.value == 1.0
    assert not (tmp_path / "escape.txt").exists()
    assert list(tmp_path.iterdir()) == [outside]


def test_reading_an_absolute_path_outside_does_not_crash_the_verifier(tmp_path):
    target = tmp_path / "outside.txt"
    target.write_text("secret", encoding="utf-8")
    code = (
        "```python\n"
        "def add(a, b):\n"
        f"    with open({str(target)!r}, encoding='utf-8') as fh:\n"
        "        fh.read()\n"
        "    return a + b\n"
        "```"
    )
    verdict = CodeExecVerifier(timeout=20)(
        _code_problem(["assert add(1, 2) == 3"]), code
    )
    assert verdict.value in (0.0, 1.0)


def test_no_tests_is_not_a_pass():
    verdict = CodeExecVerifier()(_code_problem([]), GOOD)
    assert verdict.verified is False
    assert verdict.value == 0.0


def test_run_tests_on_empty_input_is_empty():
    assert run_tests("x = 1", []) == ()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("```python\nA\n```", "A\n"),
        ("```\nA\n```\n```python\nB\n```", "B\n"),
        ("```text\nA\n```\n```\nB\n```", "B\n"),
        ("```python\nA\n```\ntext\n```python\nB\n```", "B\n"),
        ("def f(): pass", "def f(): pass"),
        ("prose\n```python\nA", "A"),
    ],
)
def test_extract_code_prefers_the_last_python_block(text, expected):
    assert extract_code(text) == expected


class _CountingBackend:
    """Records how many times the judge actually asked."""

    name = "counting"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0
        self.roles: list[str] = []

    def generate(self, prompt, params, *, seed=None, role="generator") -> Generation:
        self.calls += 1
        self.roles.append(role)
        return Generation(text=self.reply)

    def score(self, continuation: str, prefix: str = "") -> ScoreResult:
        return ScoreResult(0.0, 0)

    def count_tokens(self, text: str) -> int:
        return len(text.split())


def test_judge_parses_a_well_formed_verdict():
    backend = _CountingBackend(json.dumps({"score": 0.9, "reason": "complete proof"}))
    verdict = JudgeVerifier(backend)(_problem(family="math_proof"), "a proof")
    assert verdict.value == pytest.approx(0.9)
    assert verdict.verified is True
    assert verdict.detail == "complete proof"
    assert backend.roles == ["judge"]


def test_the_cache_prevents_a_second_backend_call():
    backend = _CountingBackend(json.dumps({"score": 1.0}))
    judge = JudgeVerifier(backend)
    problem = _problem(family="math_proof")
    first = judge(problem, "same text")
    second = judge(problem, "same text")
    assert backend.calls == 1
    assert (first.value, first.verified) == (second.value, second.verified)
    assert second.meta["cached"] is True and first.meta["cached"] is False
    judge(problem, "different text")
    assert backend.calls == 2
    judge(Problem(id="other", text="t", benchmark="b", family="math_proof"), "same text")
    assert backend.calls == 3, "the cache key must include the problem id"


@pytest.mark.parametrize(
    "reply",
    [
        "I think it is correct.",
        "{not json at all",
        json.dumps({"comment": "nice"}),
        json.dumps({"score": "high"}),
    ],
)
def test_malformed_judge_output_degrades_instead_of_raising(reply):
    verdict = JudgeVerifier(_CountingBackend(reply))(_problem(family="math_proof"), "x")
    assert verdict.verified is False
    assert verdict.value == 0.0
    assert verdict.meta.get("parse_error") is True


def test_threshold_governs_the_accept_decision():
    reply = json.dumps({"score": 0.6})
    problem = _problem(family="math_proof")
    assert JudgeVerifier(_CountingBackend(reply), threshold=0.5)(problem, "x").verified
    assert not JudgeVerifier(_CountingBackend(reply), threshold=0.7)(problem, "x").verified
    strict = JudgeVerifier(_CountingBackend(reply), threshold=0.7)
    assert strict.verified_predicate(0.7) and not strict.verified_predicate(0.69)


def test_boolean_only_and_scaled_verdicts():
    assert parse_judge_verdict(json.dumps({"correct": True})).value == 1.0
    assert parse_judge_verdict(json.dumps({"correct": False})).value == 0.0
    assert parse_judge_verdict(json.dumps({"score": 7}), scale=7.0).value == 1.0
    assert parse_judge_verdict(json.dumps({"score": 3.5}), scale=7.0).value == 0.5
    assert parse_judge_verdict(json.dumps({"score": 12})).value == 1.0
    assert parse_judge_verdict(json.dumps({"score": -4})).value == 0.0


def test_judge_prompt_carries_the_original_problem_only():
    problem = _problem(text="Original statement.", rubric="Be right.")
    prompt = build_judge_prompt(DEFAULT_TEMPLATE, problem, "candidate body")
    assert "Original statement." in prompt
    assert "<candidate>" in prompt and "candidate body" in prompt
    assert "{{PROBLEM}}" not in prompt and "{{RUBRIC}}" not in prompt


def test_judge_calls_do_not_consume_the_generator_budget():
    from trope.backends.mock import MockBackend

    dataset = synthetic_dataset(n=2, seed=0)
    counter = CallCounter()
    metered = MeteredBackend(MockBackend(dataset, seed=0), counter, budget=4)
    judge = JudgeVerifier(metered.for_role("judge"))
    for i in range(6):
        judge(dataset[0], f"Therefore, since it holds, hence \\boxed{{{i}}}")
    assert counter.get("generator") == 0
    assert counter.get("judge") == 6


def test_judge_is_deterministic_on_the_mock_backend():
    from trope.backends.mock import MockBackend

    dataset = synthetic_dataset(n=2, seed=0)
    text = "Since it holds, and because of that, therefore \\boxed{4}"

    def once() -> Verdict:
        return JudgeVerifier(MockBackend(dataset, seed=0))(dataset[0], text)

    a, b = once(), once()
    assert (a.value, a.verified) == (b.value, b.verified)


UNSAFE = [
    "x.real",
    "x.__class__",
    "__import__('os')",
    "open('f')",
    "eval('1')",
    "[i for i in x]",
    "{i for i in x}",
    "{k: v for k, v in x}",
    "(i for i in x)",
    "lambda: 1",
    "x[0]",
    "f'{x}'",
    "'a' + 'b'",
    "x if x else 1",
    "x and 1",
    "import os",
    "x = 1",
    "sqrt(x, base=2)",
]


@pytest.mark.parametrize("expr", UNSAFE, ids=lambda e: e[:16])
def test_the_safe_evaluator_rejects_everything_outside_the_whitelist(expr):
    with pytest.raises(UnsafeExpression):
        safe_eval(expr, {"x": 2.0})


@pytest.mark.parametrize(
    "expr,value",
    [
        ("2 * x + x", 9.0),
        ("x ** 2", 9.0),
        ("-x", -3.0),
        ("sqrt(x * 3)", 3.0),
        ("exp(0) + log(1)", 1.0),
        ("min(x, 1) + max(x, 1)", 4.0),
        ("pi", 3.141592653589793),
        ("7 % x", 1.0),
    ],
)
def test_the_safe_evaluator_computes(expr, value):
    assert safe_eval(expr, {"x": 3.0}) == pytest.approx(value)


def test_unbound_variables_are_reported_not_defaulted():
    with pytest.raises(UnsafeExpression):
        safe_eval("y + 1", {"x": 1.0})


def test_arithmetic_failures_are_not_disguised_as_rejections():
    with pytest.raises(ZeroDivisionError):
        safe_eval("1 / 0", {})
    with pytest.raises(ValueError):
        safe_eval("log(0 - 1)", {})
    with pytest.raises(OverflowError):
        safe_eval("9 ** 9 ** 9", {})


def test_compile_expression_reports_free_variables():
    _, names = compile_expression("a * sin(b) + pi")
    assert names == ("a", "b")


@pytest.mark.parametrize(
    "predicted,gold,expected",
    [
        ("2*x + x", "3*x", 1.0),
        ("x*x", "x**2", 1.0),
        ("(x + 1)*(x - 1)", "x**2 - 1", 1.0),
        ("2*x", "3*x", 0.0),
        ("x + 1", "x + 1.0000000001", 1.0),
        ("x + 1", "x + 2", 0.0),
    ],
)
def test_symbolic_accuracy_is_algebraic_not_textual(predicted, gold, expected):
    value, _ = symbolic_accuracy(predicted, gold)
    assert value == pytest.approx(expected)


def test_symbolic_accuracy_rejects_an_unsafe_candidate_rather_than_running_it():
    value, detail = symbolic_accuracy("__import__('os')", "x")
    assert value == 0.0
    assert "rejected" in detail


def test_halton_grid_is_deterministic_and_inside_the_domain():
    a = halton_grid(2, 16, 0.5, 2.0)
    assert a == halton_grid(2, 16, 0.5, 2.0)
    assert len({p for p in a}) == 16
    assert all(0.5 <= c <= 2.0 for p in a for c in p)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The law is y = 2*x + 1", "2*x + 1"),
        ("```\nc0 * exp(-x)\n```", "c0 * exp(-x)"),
        ("prose only, no maths", None),
        ("y = 3*x\nand that is 42.", "3*x"),
    ],
)
def test_extract_expression(text, expected):
    assert extract_expression(text) == expected


def test_llmsrbench_verdicts_are_real_not_stand_ins():
    problem = Problem(
        id="sr/0",
        text="Find the law.",
        benchmark="llmsrbench",
        family="discovery",
        answer="3*x",
        metadata={"variables": ["x"]},
    )
    verifier = get_verifier(problem)
    good = verifier(problem, "After fitting, y = 2*x + x")
    bad = verifier(problem, "After fitting, y = 2*x")
    assert good.meta["stand_in"] is False
    assert good.value == 1.0 and good.verified is True
    assert bad.value == 0.0 and bad.verified is False


@pytest.mark.parametrize(
    "benchmark", ["noveltybench", "creativityprism", "uot", "researchbench"]
)
def test_every_placeholder_verdict_is_flagged_as_a_stand_in(benchmark):
    problem = Problem(
        id=f"{benchmark}/0",
        text="Invent something.",
        benchmark=benchmark,
        family="creativity" if benchmark != "researchbench" else "discovery",
        rubric="a plausible mechanism involving diffusion and temperature",
    )
    verdict = get_verifier(problem)(problem, "A mechanism where diffusion rises with temperature.")
    assert verdict.meta["stand_in"] is True
    assert 0.0 <= verdict.value <= 1.0


def test_an_unknown_benchmark_falls_back_to_a_flagged_stand_in():
    problem = Problem(
        id="x/0", text="t", benchmark="brand_new", family="creativity", rubric="alpha beta"
    )
    verdict = OracleVerifier("brand_new")(problem, "alpha and beta")
    assert verdict.meta["stand_in"] is True


def test_registering_the_official_scorer_replaces_the_stand_in():
    from trope.verify.oracle import OracleScore, _uot_stand_in

    try:
        register_scorer("uot", lambda p, t: OracleScore(1.0, "official", False))
        verdict = OracleVerifier("uot")(_problem(family="creativity"), "anything")
        assert verdict.meta["stand_in"] is False
        assert verdict.value == 1.0
    finally:
        register_scorer("uot", _uot_stand_in)
    assert get_scorer("uot") is _uot_stand_in


def test_stand_in_scorers_are_deterministic_and_bounded():
    problem = Problem(
        id="nb/0",
        text="Write something.",
        benchmark="noveltybench",
        family="creativity",
        rubric="colour texture rhythm",
    )
    verifier = OracleVerifier("noveltybench")
    texts = ["", "colour", "colour texture rhythm and more besides, varied and long"]
    for text in texts:
        a, b = verifier(problem, text), verifier(problem, text)
        assert a.value == b.value
        assert 0.0 <= a.value <= 1.0


def test_token_f1_is_symmetric_in_its_extremes():
    assert token_f1("alpha beta", "alpha beta") == pytest.approx(1.0)
    assert token_f1("alpha beta", "gamma delta") == 0.0
    assert token_f1("", "anything") == 0.0
