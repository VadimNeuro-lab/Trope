"""Loaders and the synthetic benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trope.backends.mock import _candidate_names
from trope.data import loaders
from trope.data.base import FAMILIES, Dataset, Problem, available, load
from trope.data.loaders import DatasetNotFound, read_records, resolve_file
from trope.data.synthetic import synthetic_dataset
from trope.verify.base import get_verifier
from trope.verify.code_exec import CodeExecVerifier
from trope.verify.exact_match import ExactMatchVerifier

BENCHMARKS = (
    "math500",
    "aime",
    "usamo",
    "livecodebench",
    "humaneval_plus",
    "noveltybench",
    "creativityprism",
    "uot",
    "llmsrbench",
    "researchbench",
)

EXPECTED_FAMILY = {
    "math500": "math_answer",
    "aime": "math_answer",
    "usamo": "math_proof",
    "livecodebench": "code",
    "humaneval_plus": "code",
    "noveltybench": "creativity",
    "creativityprism": "creativity",
    "uot": "creativity",
    "llmsrbench": "discovery",
    "researchbench": "discovery",
}

FIXTURES: dict[str, list[dict]] = {
    "math500": [
        {"unique_id": "t/1", "problem": "Find x.", "answer": "7", "level": 3, "subject": "Algebra"}
    ],
    "aime": [{"problem": "Find n.", "answer": "042", "year": 2025}],
    "usamo": [{"problem": "Prove it.", "solution": "By induction.", "points": 7}],
    "livecodebench": [
        {
            "question_id": "q1",
            "question_content": "Return the double.",
            "entry_point": "solve",
            "public_test_cases": json.dumps([{"input": "2", "output": "4"}]),
            "difficulty": "easy",
        }
    ],
    "humaneval_plus": [
        {
            "task_id": "HumanEval/0",
            "prompt": "def add(a, b):\n",
            "entry_point": "add",
            "canonical_solution": "    return a + b\n",
            "test": "assert add(1, 2) == 3",
        }
    ],
    "noveltybench": [{"id": "nb1", "prompt": "Write a poem.", "source": "curated"}],
    "creativityprism": [
        {"id": "cp1", "prompt": "Invent a game.", "rubric": "novel and playable", "dimension": "novelty"}
    ],
    "uot": [{"id": "u1", "problem": "Imagine a world.", "rubric": "feasible and useful"}],
    "llmsrbench": [
        {
            "id": "sr1",
            "problem": "Fit the data.",
            "gold_equation": "3*x",
            "variables": ["x"],
            "domain": [0.5, 2.0],
        }
    ],
    "researchbench": [
        {"id": "rb1", "background": "Cells diffuse.", "gold_hypothesis": "Diffusion scales with temperature."}
    ],
}


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """A TROPE_DATA_DIR laid out exactly as the loaders document."""
    for name, records in FIXTURES.items():
        directory = tmp_path / name
        directory.mkdir()
        filename = loaders.SOURCES[name][0]
        with (directory / filename).open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record) + "\n")
    return tmp_path


def test_every_benchmark_of_the_paper_is_registered():
    assert set(BENCHMARKS) <= set(available())
    assert "synthetic" in available()


@pytest.mark.parametrize("name", BENCHMARKS)
def test_loader_sets_the_family_from_the_benchmark_table(name, data_root, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(data_root))
    dataset = load(name)
    assert len(dataset) == 1
    problem = dataset[0]
    assert problem.family == EXPECTED_FAMILY[name]
    assert problem.family in FAMILIES
    assert problem.benchmark == name
    assert problem.text
    assert problem.id.startswith(f"{name}/")


@pytest.mark.parametrize("name", BENCHMARKS)
def test_a_missing_dataset_names_its_upstream_source(name, tmp_path, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(tmp_path))
    with pytest.raises(DatasetNotFound) as excinfo:
        load(name)
    message = str(excinfo.value)
    filename, source = loaders.SOURCES[name]
    assert filename in message
    assert source.split()[0] in message
    assert "download" in message.lower()


def test_the_path_argument_overrides_the_environment(data_root, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(data_root / "nowhere"))
    dataset = loaders.load_math500(path=data_root / "math500")
    assert dataset[0].answer == "7"


def test_the_repo_default_is_used_when_no_environment_is_set(monkeypatch):
    monkeypatch.delenv(loaders.ENV_VAR, raising=False)
    assert loaders.data_dir("math500").parts[-2:] == ("data", "math500")


def test_math_loaders_carry_the_gold_answer(data_root, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(data_root))
    assert load("math500")[0].answer == "7"
    assert load("aime")[0].answer == "042"


def test_code_loaders_carry_runnable_tests(data_root, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(data_root))
    humaneval = load("humaneval_plus")[0]
    assert humaneval.tests == ("assert add(1, 2) == 3",)
    assert humaneval.entry_point == "add"
    lcb = load("livecodebench")[0]
    assert lcb.entry_point == "solve"
    assert len(lcb.tests) == 1 and "solve(" in lcb.tests[0]


def test_usamo_has_no_short_answer_but_keeps_a_rubric(data_root, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(data_root))
    problem = load("usamo")[0]
    assert problem.answer is None
    assert problem.rubric == "By induction."
    assert problem.metadata["max_points"] == 7


def test_llmsrbench_metadata_feeds_the_symbolic_oracle(data_root, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(data_root))
    problem = load("llmsrbench")[0]
    assert problem.answer == "3*x"
    assert problem.metadata["variables"] == ["x"]
    verdict = get_verifier(problem)(problem, "y = x + 2*x")
    assert verdict.verified is True
    assert verdict.meta["stand_in"] is False


def test_humaneval_without_tests_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(tmp_path))
    directory = tmp_path / "humaneval_plus"
    directory.mkdir()
    (directory / "HumanEvalPlus.jsonl").write_text(
        json.dumps({"task_id": "HumanEval/0", "prompt": "p", "entry_point": "add"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="test"):
        load("humaneval_plus")


def test_a_record_missing_its_statement_names_the_keys_it_looked_for(tmp_path, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(tmp_path))
    directory = tmp_path / "math500"
    directory.mkdir()
    (directory / "test.jsonl").write_text(
        json.dumps({"id": "1", "answer": "7"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="problem"):
        load("math500")


def test_a_json_list_is_accepted_in_place_of_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(tmp_path))
    directory = tmp_path / "math500"
    directory.mkdir()
    (directory / "test.json").write_text(
        json.dumps(FIXTURES["math500"]), encoding="utf-8"
    )
    assert load("math500")[0].answer == "7"


def test_read_records_reports_the_offending_line(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"a": 1}\n\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=":3:"):
        read_records(path)


def test_limit_truncates(tmp_path, monkeypatch):
    monkeypatch.setenv(loaders.ENV_VAR, str(tmp_path))
    directory = tmp_path / "math500"
    directory.mkdir()
    with (directory / "test.jsonl").open("w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({"id": i, "problem": f"p{i}", "answer": str(i)}) + "\n")
    assert len(load("math500", limit=2)) == 2
    assert len(load("math500")) == 5


def test_resolve_file_accepts_a_direct_file_path(data_root):
    path = data_root / "math500" / "test.jsonl"
    assert resolve_file("math500", path) == path


def test_synthetic_is_deterministic():
    a = synthetic_dataset(n=12, seed=3)
    b = synthetic_dataset(n=12, seed=3)
    assert [p.to_dict() for p in a] == [p.to_dict() for p in b]
    c = synthetic_dataset(n=12, seed=4)
    assert [p.text for p in a] != [p.text for p in c]


def test_synthetic_respects_size_and_is_a_prefix_in_n():
    for n in (0, 1, 5, 32):
        assert len(synthetic_dataset(n=n)) == n
    assert isinstance(synthetic_dataset(n=4), Dataset)


def test_synthetic_problem_statements_are_pairwise_distinct():
    for family in ("math_answer", "code", "mixed"):
        dataset = synthetic_dataset(n=48, family=family, seed=2)
        texts = [p.text for p in dataset]
        assert len(set(texts)) == len(texts), family
        assert len({p.id for p in dataset}) == len(texts)


@pytest.mark.parametrize("family", ["math_answer", "code", "mixed"])
def test_synthetic_families_are_valid(family):
    dataset = synthetic_dataset(n=10, family=family, seed=1)
    families = {p.family for p in dataset}
    assert families <= set(FAMILIES)
    if family == "mixed":
        assert families == {"math_answer", "code"}
    else:
        assert families == {family}


def test_an_unknown_family_is_refused():
    with pytest.raises(ValueError):
        synthetic_dataset(family="math_proof")
    with pytest.raises(ValueError):
        synthetic_dataset(n=-1)


def test_synthetic_math_gold_answers_verify():
    verifier = ExactMatchVerifier()
    for problem in synthetic_dataset(n=24, seed=5):
        candidate = f"Working it through.\nTherefore the answer is \\boxed{{{problem.answer}}}."
        assert verifier(problem, candidate).verified, problem.text
        wrong = f"Therefore the answer is \\boxed{{{int(problem.answer) + 1}}}."
        assert not verifier(problem, wrong).verified, problem.text


def test_synthetic_code_gold_answers_verify_and_are_not_vacuous():
    verifier = CodeExecVerifier(timeout=20)
    dataset = synthetic_dataset(n=6, family="code", seed=7)
    for problem in dataset:
        good = f"```python\n{problem.answer}```"
        assert verifier(problem, good).verified, problem.id
        broken = f"```python\ndef {problem.entry_point}(*a, **k):\n    return None\n```"
        assert not verifier(problem, broken).verified, problem.id


def test_synthetic_dispatches_to_the_right_verifier():
    for problem in synthetic_dataset(n=6, family="mixed", seed=0):
        expected = "exact_match" if problem.family == "math_answer" else "code_exec"
        assert get_verifier(problem).name == expected


def test_synthetic_includes_degenerate_items():
    dataset = synthetic_dataset(n=16, seed=0)
    degenerate = [p for p in dataset if p.metadata.get("degenerate")]
    assert len(degenerate) == 2
    for problem in degenerate:
        assert len(_candidate_names(problem.text)) == 1
        assert problem.answer is not None
    ordinary = [p for p in dataset if not p.metadata.get("degenerate")]
    assert all(len(_candidate_names(p.text)) > 1 for p in ordinary)


def test_synthetic_is_registered_under_its_own_name():
    dataset = load("synthetic", n=4, seed=1)
    assert isinstance(dataset[0], Problem)
    assert [p.id for p in dataset] == [p.id for p in synthetic_dataset(n=4, seed=1)]
