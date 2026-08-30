"""A self-contained benchmark, so the pipeline runs with nothing downloaded."""

from __future__ import annotations

from dataclasses import replace
from math import gcd
from typing import Any, Callable

from trope.data.base import Dataset, Problem, register

FAMILIES: tuple[str, ...] = ("math_answer", "code", "mixed")

_COLLISION_STRIDE = 1005


def _mix(seed: int, index: int, salt: int) -> int:
    """A small deterministic spread of (seed, index) into problem parameters."""
    return (seed * 7919 + index * 104729 + salt * 1299709) % 1_000_003


def _modpow(seed: int, i: int) -> tuple[str, str]:
    base = 2 + _mix(seed, i, 1) % 11
    exponent = 3 + _mix(seed, i, 2) % 17
    modulus = 5 + _mix(seed, i, 3) % 46
    text = (
        f"Let b = {base}, k = {exponent} and m = {modulus}. "
        "Compute the remainder of b raised to the power k when divided by m."
    )
    return text, str(pow(base, exponent, modulus))


def _divisor_count(seed: int, i: int) -> tuple[str, str]:
    limit = 60 + _mix(seed, i, 4) % 400
    divisor = 3 + _mix(seed, i, 5) % 12
    text = (
        f"How many integers strictly between 0 and {limit + 1} "
        f"are divisible by {divisor}?"
    )
    return text, str(limit // divisor)


def _arithmetic_sum(seed: int, i: int) -> tuple[str, str]:
    terms = 5 + _mix(seed, i, 6) % 40
    step = 2 + _mix(seed, i, 7) % 9
    text = (
        f"A sequence begins at {step} and increases by {step} at every step. "
        f"What is the total of its first {terms} terms?"
    )
    return text, str(step * terms * (terms + 1) // 2)


def _digit_sum(seed: int, i: int) -> tuple[str, str]:
    number = 1000 + _mix(seed, i, 8) % 89_000
    text = f"What is the sum of the decimal digits of the integer {number}?"
    return text, str(sum(int(d) for d in str(number)))


def _gcd_problem(seed: int, i: int) -> tuple[str, str]:
    left = 12 + _mix(seed, i, 9) % 800
    right = 12 + _mix(seed, i, 10) % 800
    text = (
        f"Two counters advance in steps of {left} and {right} respectively. "
        "What is the largest common step length that divides both?"
    )
    return text, str(gcd(left, right))


_MATH_TEMPLATES: tuple[Callable[[int, int], tuple[str, str]], ...] = (
    _modpow,
    _divisor_count,
    _arithmetic_sum,
    _digit_sum,
    _gcd_problem,
)


def _degenerate(seed: int, i: int) -> tuple[str, str]:
    """A statement with no alphabetic tokens at all: one entity, no relations."""
    left = 7 + _mix(seed, i, 11) % 90
    right = 3 + _mix(seed, i, 12) % 30
    return f"{left} + {right} = ?", str(left + right)


def _code_multiples(seed: int, i: int) -> dict[str, Any]:
    step = 2 + _mix(seed, i, 13) % 40
    return {
        "entry_point": "sum_multiples",
        "text": (
            "Write a function `sum_multiples(n)` returning the sum of every positive "
            f"multiple of {step} that is at most n. For n below {step} the sum is 0."
        ),
        "answer": (
            "def sum_multiples(n):\n"
            f"    return sum(v for v in range(1, n + 1) if v % {step} == 0)\n"
        ),
        "tests": (
            "assert sum_multiples(0) == 0",
            f"assert sum_multiples({step}) == {step}",
            f"assert sum_multiples({step * 4}) == {sum(v for v in range(1, step * 4 + 1) if v % step == 0)}",
        ),
    }


def _code_digits(seed: int, i: int) -> dict[str, Any]:
    number = 100 + _mix(seed, i, 14) % 80_000
    return {
        "entry_point": "digit_total",
        "text": (
            "Write a function `digit_total(n)` returning the sum of the decimal digits "
            f"of a non-negative integer n. For instance digit_total({number}) is "
            f"{sum(int(d) for d in str(number))}."
        ),
        "answer": (
            "def digit_total(n):\n"
            "    total = 0\n"
            "    while n:\n"
            "        total += n % 10\n"
            "        n //= 10\n"
            "    return total\n"
        ),
        "tests": (
            "assert digit_total(0) == 0",
            "assert digit_total(9) == 9",
            f"assert digit_total({number}) == {sum(int(d) for d in str(number))}",
        ),
    }


def _code_run_length(seed: int, i: int) -> dict[str, Any]:
    width = 2 + _mix(seed, i, 15) % 25
    word = "ab" * width
    return {
        "entry_point": "longest_run",
        "text": (
            "Write a function `longest_run(s)` returning the length of the longest run "
            "of one repeated character in the string s. The empty string has length 0, "
            f"and the string {'c' * width!r} has {width}."
        ),
        "answer": (
            "def longest_run(s):\n"
            "    best = run = 0\n"
            "    previous = None\n"
            "    for ch in s:\n"
            "        run = run + 1 if ch == previous else 1\n"
            "        previous = ch\n"
            "        best = max(best, run)\n"
            "    return best\n"
        ),
        "tests": (
            "assert longest_run('') == 0",
            f"assert longest_run({word!r}) == 1",
            f"assert longest_run({'c' * width!r}) == {width}",
        ),
    }


_CODE_TEMPLATES: tuple[Callable[[int, int], dict[str, Any]], ...] = (
    _code_multiples,
    _code_digits,
    _code_run_length,
)


def _math_problem(name: str, seed: int, i: int, *, degenerate: bool) -> Problem:
    if degenerate:
        text, answer = _degenerate(seed, i)
    else:
        text, answer = _MATH_TEMPLATES[i % len(_MATH_TEMPLATES)](seed, i)
    return Problem(
        id=f"{name}/math/{i:04d}",
        text=text,
        benchmark=name,
        family="math_answer",
        answer=answer,
        rubric="A correct final numeric answer.",
        metadata={"template": "degenerate" if degenerate else i % len(_MATH_TEMPLATES),
                  "degenerate": degenerate},
    )


def _code_problem(name: str, seed: int, i: int) -> Problem:
    spec = _CODE_TEMPLATES[i % len(_CODE_TEMPLATES)](seed, i)
    return Problem(
        id=f"{name}/code/{i:04d}",
        text=spec["text"],
        benchmark=name,
        family="code",
        answer=spec["answer"],
        tests=spec["tests"],
        entry_point=spec["entry_point"],
        metadata={"template": i % len(_CODE_TEMPLATES), "degenerate": False},
    )


@register("synthetic")
def synthetic_dataset(
    name: str = "synthetic", n: int = 32, family: str = "math_answer", seed: int = 0
) -> Dataset:
    """`n` deterministic problems with real gold answers."""
    if family not in FAMILIES:
        raise ValueError(f"family must be one of {FAMILIES}, got {family!r}")
    if n < 0:
        raise ValueError("n must be non-negative")

    degenerate_from = n - 2 if n >= 4 else n

    def build(i: int, k: int) -> Problem:
        if family == "code" or (family == "mixed" and i % 2 == 1):
            return _code_problem(name, seed, k)
        return _math_problem(name, seed, k, degenerate=i >= degenerate_from)

    problems: list[Problem] = []
    seen: set[str] = set()
    for i in range(n):
        item = build(i, i)
        bump = 0
        while item.text in seen and bump < 64:
            bump += 1
            item = replace(build(i, i + bump * _COLLISION_STRIDE), id=item.id)
        seen.add(item.text)
        problems.append(item)
    return Dataset(name, problems)
