"""Loaders for the ten benchmarks of the benchmark table (`tab:benchmarks`)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from trope.config import REPO_ROOT
from trope.data.base import Dataset, Problem, register

ENV_VAR = "TROPE_DATA_DIR"

SOURCES: dict[str, tuple[str, str]] = {
    "math500": ("test.jsonl", "https://huggingface.co/datasets/HuggingFaceH4/MATH-500"),
    "aime": ("aime.jsonl", "https://matharena.ai (AIME 2025/2026)"),
    "usamo": ("usamo.jsonl", "https://matharena.ai (USAMO 2025)"),
    "livecodebench": (
        "test.jsonl",
        "https://huggingface.co/datasets/livecodebench/code_generation_lite",
    ),
    "humaneval_plus": (
        "HumanEvalPlus.jsonl",
        "https://github.com/evalplus/evalplus (HumanEvalPlus release)",
    ),
    "noveltybench": ("curated.jsonl", "https://github.com/yimingzhang/noveltybench"),
    "creativityprism": ("tasks.jsonl", "CreativityPrism (Hou et al., 2025) release"),
    "uot": ("tasks.jsonl", "Universe of Thoughts (Suzuki et al., 2025) task suite"),
    "llmsrbench": ("problems.jsonl", "https://github.com/deep-symbolic-mathematics/llm-srbench"),
    "researchbench": ("hypotheses.jsonl", "ResearchBench (Liu et al., 2025) release"),
}


class DatasetNotFound(FileNotFoundError):
    """Raised when a benchmark's local copy is absent. Message names the source."""


def data_dir(name: str, path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    root = os.environ.get(ENV_VAR)
    if root:
        return Path(root) / name
    return REPO_ROOT / "data" / name


def resolve_file(name: str, path: str | Path | None, filename: str | None = None) -> Path:
    """Locate the benchmark's data file, or raise with the upstream source."""
    default_name, source = SOURCES[name]
    wanted = filename or default_name
    base = data_dir(name, path)
    if base.is_file():
        return base
    candidate = base / wanted
    if candidate.exists():
        return candidate
    alt = candidate.with_suffix(".json")
    if alt.exists():
        return alt
    raise DatasetNotFound(
        f"{name}: expected {candidate}. This repository ships no benchmark data; "
        f"download it from {source} and place it there, or set {ENV_VAR}, or pass "
        f"path=. Nothing here downloads anything."
    )


def read_records(path: Path) -> list[dict[str, Any]]:
    """Records from a .jsonl file, or from a .json file holding a list or a dict of records."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        blob = json.loads(text)
        if isinstance(blob, Mapping):
            return [
                {"id": key, **value} if isinstance(value, Mapping) else {"id": key, "value": value}
                for key, value in blob.items()
            ]
        return [dict(item) for item in blob]
    out: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: {exc.msg}") from exc
    return out


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _require(record: Mapping[str, Any], path: Path, *keys: str) -> Any:
    value = _first(record, *keys)
    if value is None:
        raise ValueError(
            f"{path}: record is missing all of {list(keys)}; got keys {sorted(record)}"
        )
    return value


def _identifier(record: Mapping[str, Any], benchmark: str, index: int) -> str:
    raw = _first(record, "id", "unique_id", "task_id", "question_id", "problem_id", "idx")
    return f"{benchmark}/{raw}" if raw is not None else f"{benchmark}/{index:05d}"


def _meta(**values: Any) -> dict[str, Any]:
    """Metadata without the keys the release did not carry."""
    return {k: v for k, v in values.items() if v is not None}


def _as_tests(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def _dataset(
    name: str, problems: Iterable[Problem], limit: int | None = None
) -> Dataset:
    items = list(problems)
    return Dataset(name, items[:limit] if limit is not None else items)


@register("math500")
def load_math500(path: str | Path | None = None, limit: int | None = None) -> Dataset:
    file = resolve_file("math500", path)
    return _dataset(
        "math500",
        (
            Problem(
                id=_identifier(r, "math500", i),
                text=str(_require(r, file, "problem", "question")),
                benchmark="math500",
                family="math_answer",
                answer=str(_require(r, file, "answer", "gt_answer", "solution")),
                metadata=_meta(
                    level=_first(r, "level"),
                    subject=_first(r, "subject", "type"),
                ),
            )
            for i, r in enumerate(read_records(file))
        ),
        limit,
    )


@register("aime")
def load_aime(path: str | Path | None = None, limit: int | None = None) -> Dataset:
    file = resolve_file("aime", path)
    return _dataset(
        "aime",
        (
            Problem(
                id=_identifier(r, "aime", i),
                text=str(_require(r, file, "problem", "question", "statement")),
                benchmark="aime",
                family="math_answer",
                answer=str(_require(r, file, "answer", "gold_answer")),
                metadata=_meta(
                    year=_first(r, "year", "competition"), part=_first(r, "part")
                ),
            )
            for i, r in enumerate(read_records(file))
        ),
        limit,
    )


@register("usamo")
def load_usamo(path: str | Path | None = None, limit: int | None = None) -> Dataset:
    """Proof writing: no short answer, so the gold solution becomes the rubric the judge grades against."""
    file = resolve_file("usamo", path)
    problems = []
    for i, r in enumerate(read_records(file)):
        reference = _first(r, "solution", "reference_solution", "answer") or ""
        problems.append(
            Problem(
                id=_identifier(r, "usamo", i),
                text=str(_require(r, file, "problem", "question", "statement")),
                benchmark="usamo",
                family="math_proof",
                rubric=str(_first(r, "rubric", "grading_scheme") or reference),
                metadata=_meta(max_points=_first(r, "points", "max_points") or 7),
            )
        )
    return _dataset("usamo", problems, limit)


def _lcb_tests(record: Mapping[str, Any], entry_point: str) -> tuple[str, ...]:
    """LiveCodeBench ships stdin/stdout pairs, often as a JSON string."""
    raw = _first(record, "public_test_cases", "test_cases", "tests")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return (raw,)
    if not isinstance(raw, Sequence):
        return ()
    out: list[str] = []
    for case in raw:
        if isinstance(case, str):
            out.append(case)
            continue
        stdin = str(case.get("input", ""))
        expected = str(case.get("output", ""))
        if entry_point:
            out.append(
                f"assert str({entry_point}({stdin!r})).strip() == {expected!r}.strip()"
            )
    return tuple(out)


@register("livecodebench")
def load_livecodebench(
    path: str | Path | None = None, limit: int | None = None
) -> Dataset:
    file = resolve_file("livecodebench", path)
    problems = []
    for i, r in enumerate(read_records(file)):
        entry_point = str(_first(r, "entry_point", "func_name") or "")
        problems.append(
            Problem(
                id=_identifier(r, "livecodebench", i),
                text=str(_require(r, file, "question_content", "question", "problem")),
                benchmark="livecodebench",
                family="code",
                tests=_lcb_tests(r, entry_point),
                entry_point=entry_point,
                metadata=_meta(
                    difficulty=_first(r, "difficulty"),
                    contest_date=_first(r, "contest_date"),
                    starter_code=_first(r, "starter_code"),
                ),
            )
        )
    return _dataset("livecodebench", problems, limit)


@register("humaneval_plus")
def load_humaneval_plus(
    path: str | Path | None = None, limit: int | None = None
) -> Dataset:
    file = resolve_file("humaneval_plus", path)
    problems = []
    for i, r in enumerate(read_records(file)):
        tests = _as_tests(_first(r, "test", "tests", "assertion"))
        if not tests:
            raise ValueError(
                f"{file}: {_identifier(r, 'humaneval_plus', i)} has no 'test' field; "
                "the EvalPlus release with the expanded test suites is required"
            )
        problems.append(
            Problem(
                id=_identifier(r, "humaneval_plus", i),
                text=str(_require(r, file, "prompt", "question")),
                benchmark="humaneval_plus",
                family="code",
                answer=_first(r, "canonical_solution"),
                tests=tests,
                entry_point=str(_require(r, file, "entry_point")),
            )
        )
    return _dataset("humaneval_plus", problems, limit)


def _open_ended(
    benchmark: str,
    family: str,
    *,
    text_keys: tuple[str, ...],
    rubric_keys: tuple[str, ...],
    answer_keys: tuple[str, ...] = (),
    metadata_keys: tuple[str, ...] = (),
):
    """Loader body shared by the four benchmarks whose record is prompt + rubric."""

    def load(path: str | Path | None = None, limit: int | None = None) -> Dataset:
        file = resolve_file(benchmark, path)
        problems = [
            Problem(
                id=_identifier(r, benchmark, i),
                text=str(_require(r, file, *text_keys)),
                benchmark=benchmark,
                family=family,
                answer=(
                    str(_first(r, *answer_keys)) if answer_keys and _first(r, *answer_keys) else None
                ),
                rubric=str(_first(r, *rubric_keys) or ""),
                metadata=_meta(**{key: _first(r, key) for key in metadata_keys}),
            )
            for i, r in enumerate(read_records(file))
        ]
        return _dataset(benchmark, problems, limit)

    load.__name__ = f"load_{benchmark}"
    return load


load_noveltybench = register("noveltybench")(
    _open_ended(
        "noveltybench",
        "creativity",
        text_keys=("prompt", "instruction", "text"),
        rubric_keys=("rubric", "reference", "guidance"),
        metadata_keys=("source", "category"),
    )
)

load_creativityprism = register("creativityprism")(
    _open_ended(
        "creativityprism",
        "creativity",
        text_keys=("prompt", "instruction", "task", "question"),
        rubric_keys=("rubric", "criteria", "reference"),
        metadata_keys=("dimension", "domain", "task_type"),
    )
)

load_uot = register("uot")(
    _open_ended(
        "uot",
        "creativity",
        text_keys=("problem", "prompt", "question", "task"),
        rubric_keys=("rubric", "criteria", "reference_answer"),
        metadata_keys=("category", "difficulty"),
    )
)

load_researchbench = register("researchbench")(
    _open_ended(
        "researchbench",
        "discovery",
        text_keys=("background", "question", "prompt", "context"),
        rubric_keys=("gold_hypothesis", "hypothesis", "reference"),
        answer_keys=("gold_hypothesis", "hypothesis"),
        metadata_keys=("field", "inspiration_category", "paper_id"),
    )
)


@register("llmsrbench")
def load_llmsrbench(path: str | Path | None = None, limit: int | None = None) -> Dataset:
    """Equation discovery."""
    file = resolve_file("llmsrbench", path)
    problems = []
    for i, r in enumerate(read_records(file)):
        variables = _first(r, "variables", "symbols", "var_names") or []
        problems.append(
            Problem(
                id=_identifier(r, "llmsrbench", i),
                text=str(_require(r, file, "problem", "description", "prompt", "question")),
                benchmark="llmsrbench",
                family="discovery",
                answer=str(
                    _require(r, file, "gold_equation", "symbolic_expression", "equation", "answer")
                ),
                metadata=_meta(
                    variables=[str(v) for v in variables],
                    domain=_first(r, "domain", "sample_range"),
                    dataset=_first(r, "dataset", "subset"),
                ),
            )
        )
    return _dataset("llmsrbench", problems, limit)
