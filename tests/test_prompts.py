"""Anti-drift tests for the shipped prompts and configs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from trope.backends.mock import extract_tag
from trope.config import CONFIG_DIR, PROMPT_DIR, SCHEMA_DIR, Config, SamplingConfig
from trope.data.base import FAMILIES
from trope.descriptors import get_descriptor
from trope.operators.base import TOKEN, catalog

OPERATOR_PROMPTS = PROMPT_DIR / "operators"
BENCHMARK_DIR = CONFIG_DIR / "benchmarks"

_PLACEHOLDER = re.compile(r"\{\{([A-Za-z_]+)\}\}")

TOP_LEVEL_PLACEHOLDERS = {
    "parser.txt": {"PROBLEM"},
    "generator.txt": {"PROBLEM", "REPRESENTATION", "OPERATOR", "DETAIL"},
    "judge.txt": {"PROBLEM", "CANDIDATE"},
}
OPERATOR_PLACEHOLDERS = {"REPRESENTATION", "RADICALITY", "DETAIL"}

PARSER_EXCERPT = (
    "Extract E, Rel, T, A, G, and F from P. Preserve explicit constraints, "
    "list inferred assumptions separately, and do not solve the problem."
)
EDIT_EXCERPT_TAIL = (
    "Return R' and a short change log. Treat R' as a search hypothesis and "
    "keep the original acceptance rule."
)
GENERATOR_EXCERPT = (
    "Use R' to explore a route, then solve the original P and check every "
    "original constraint. The candidate is evaluated by V_P."
)

VERIFIER_KINDS = {
    "exact_match",
    "unit_tests",
    "llm_judge",
    "symbolic_match",
    "reference_f1",
}

DESCRIPTOR_M = {
    "math500": 48,
    "aime": 36,
    "usamo": 25,
    "livecodebench": 64,
    "humaneval_plus": 40,
    "noveltybench": 80,
    "creativityprism": 60,
    "uot": 30,
    "llmsrbench": 56,
    "researchbench": 72,
}


def prompt_files() -> list[Path]:
    return sorted(PROMPT_DIR.glob("*.txt")) + sorted(OPERATOR_PROMPTS.glob("*.txt"))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def flowed(path: Path) -> str:
    """File text with the hard wrapping collapsed."""
    return " ".join(read(path).split())


def placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER.findall(text))


def schema() -> dict:
    return json.loads(read(SCHEMA_DIR / "representation.json"))


def test_every_operator_has_a_prompt_file():
    missing = [
        op.name
        for op in catalog()
        if not (OPERATOR_PROMPTS / f"{op.name}.txt").exists()
    ]
    assert missing == []


def test_every_operator_prompt_is_a_registered_operator():
    on_disk = {p.stem for p in OPERATOR_PROMPTS.glob("*.txt")}
    assert on_disk == {op.name for op in catalog()}


def test_the_catalog_is_the_eleven_the_paper_counts():
    assert len(catalog()) == 11


@pytest.mark.parametrize("path", prompt_files(), ids=lambda p: p.name)
def test_placeholders_are_ones_the_code_substitutes(path: Path):
    expected = TOP_LEVEL_PLACEHOLDERS.get(path.name, OPERATOR_PLACEHOLDERS)
    assert placeholders(read(path)) == expected


def test_substitution_leaves_no_placeholder_behind():
    """The parser and generator templates fill completely, tags intact."""
    from trope.data.base import Problem
    from trope.search import build_generator_prompt
    from trope.types import Assumption, Entity, Goal, Representation

    problem = Problem(
        id="p1",
        text="How many primes are below 30?",
        benchmark="synthetic",
        family="math_answer",
        answer="10",
    )
    rep = Representation(
        entities=(Entity("n", "parameter", "cardinality"),),
        assumptions=(Assumption("n is an integer", True),),
        goal=Goal("count the primes below n"),
        frame="number-theory",
    )

    parser_prompt = read(PROMPT_DIR / "parser.txt").replace("{{PROBLEM}}", problem.text)
    assert placeholders(parser_prompt) == set()
    assert extract_tag(parser_prompt, "problem").strip() == problem.text

    gen_prompt = build_generator_prompt(
        read(PROMPT_DIR / "generator.txt"),
        problem,
        rep,
        "type_shifting",
        "n: parameter -> variable",
    )
    assert placeholders(gen_prompt) == set()
    assert extract_tag(gen_prompt, "problem").strip() == problem.text
    body = json.loads(extract_tag(gen_prompt, "representation"))
    assert body["frame"] == "number-theory"


def test_parser_prompt_lists_every_entity_type():
    text = read(PROMPT_DIR / "parser.txt")
    enum = schema()["properties"]["entities"]["items"]["properties"]["type"]["enum"]
    assert [t for t in enum if t not in text] == []


def test_parser_prompt_lists_every_relation_type():
    text = read(PROMPT_DIR / "parser.txt")
    enum = schema()["properties"]["relations"]["items"]["properties"]["rtype"]["enum"]
    assert [t for t in enum if t not in text] == []


def test_parser_prompt_lists_every_frame():
    text = read(PROMPT_DIR / "parser.txt")
    assert [f for f in schema()["properties"]["frame"]["enum"] if f not in text] == []


def test_parser_prompt_offers_no_vocabulary_the_schema_rejects():
    """The reverse direction: everything offered as a relation type is one."""
    text = read(PROMPT_DIR / "parser.txt")
    enum = schema()["properties"]["relations"]["items"]["properties"]["rtype"]["enum"]
    block = text.split("<relation type> is exactly one of, and nothing else:")[1]
    assert set(block.split("\n\n")[1].split()) == set(enum)


def test_parser_prompt_carries_the_paper_excerpt():
    assert PARSER_EXCERPT in flowed(PROMPT_DIR / "parser.txt")


def test_parser_prompt_states_the_three_semantic_rules():
    text = flowed(PROMPT_DIR / "parser.txt")
    assert "At least one assumption must be marked true" in text
    assert 'must each be the "id" of an entity you listed above' in text
    assert "the collection of these values is the type map T" in text
    assert "Do not solve the problem." in text


def test_generator_prompt_carries_the_paper_excerpt():
    assert GENERATOR_EXCERPT in flowed(PROMPT_DIR / "generator.txt")


def test_generator_prompt_binds_the_answer_to_the_original_problem():
    text = flowed(PROMPT_DIR / "generator.txt")
    assert "search hypothesis, not a replacement task" in text
    assert "V_P is bound to the original problem P" in text
    assert "never applied to the edited formulation" in text
    assert "every constraint in the original statement" in text
    assert "<problem>" in text and "<representation>" in text


def test_judge_prompt_asks_for_a_verdict_object():
    text = flowed(PROMPT_DIR / "judge.txt")
    assert "<candidate>" in text and "</candidate>" in text
    verdict = json.loads(re.search(r'\{"correct".*?\}', text).group(0))
    assert set(verdict) == {"correct", "score"}
    assert isinstance(verdict["correct"], bool)
    assert isinstance(verdict["score"], float)
    assert "against the original problem only" in text


@pytest.mark.parametrize("op", catalog(), ids=lambda op: op.name)
def test_operator_prompt_carries_the_paper_excerpt(op):
    text = flowed(OPERATOR_PROMPTS / f"{op.name}.txt")
    assert text.startswith(f"Apply operator {op.name} at radicality rho to R.")
    assert EDIT_EXCERPT_TAIL in text


@pytest.mark.parametrize(
    "op", [o for o in catalog() if o.kind == TOKEN], ids=lambda op: op.name
)
def test_token_prompts_say_they_leave_the_representation_alone(op):
    text = flowed(OPERATOR_PROMPTS / f"{op.name}.txt")
    assert "It does not modify R" in text
    assert "R' = R" in text
    assert "do not report a structural change" in text


@pytest.mark.parametrize(
    "op", [o for o in catalog() if o.kind == TOKEN], ids=lambda op: op.name
)
def test_token_prompts_quote_the_decoding_constants(op):
    """The radicality-to-decoding mapping in the prompt is the shipped one."""
    decoding = yaml.safe_load(read(CONFIG_DIR / "decoding.yaml"))
    params = decoding["token_operators"][op.name]
    text = flowed(OPERATOR_PROMPTS / f"{op.name}.txt")
    assert [k for k, v in params.items() if f"{k} = {v}" not in text] == []
    assert f"sampling.rho_max, default {SamplingConfig().rho_max}" in text


@pytest.mark.parametrize(
    "op", [o for o in catalog() if o.kind != TOKEN], ids=lambda op: op.name
)
def test_structural_prompts_ask_for_the_parser_schema_back(op):
    text = flowed(OPERATOR_PROMPTS / f"{op.name}.txt")
    assert "in the same schema the parser emits" in text
    assert "change log:" in text
    assert "Worked example." in text


def test_foundational_negation_example_matches_the_shipped_ranking():
    from trope.operators.base import load_resources, rank_index

    res = load_resources()
    spec = res.frame("euclidean-geometry")
    ranked = spec.ranked_axioms()
    text = flowed(OPERATOR_PROMPTS / "foundational_negation.txt")

    seen = [text.index(f"{a.name} (depth {spec.depth(a.name)})") for a in ranked]
    assert seen == sorted(seen), "prompt lists the axioms out of ranked order"
    for rho, i in ((2.0, 1), (8.0, 4)):
        assert rank_index(rho, len(ranked), res) == i
        assert f'"{ranked[i].text}"' in text


def test_reification_example_names_every_edge_the_operator_adds():
    import numpy as np

    from trope.operators.base import load_resources
    from trope.types import Assumption, Entity, Goal, Relation, Representation

    rep = Representation(
        entities=(Entity("t", "coordinate", "instant"), Entity("state", "variable")),
        relations=(Relation("t", "state", "indexes"),),
        assumptions=(Assumption("time is continuous", True),),
        goal=Goal("describe the trajectory"),
        frame="physics",
    )
    op = next(o for o in catalog() if o.name == "reification")
    result = op.apply(rep, 1.0, np.random.default_rng(0), load_resources())
    text = flowed(OPERATOR_PROMPTS / "reification.txt")

    assert "p_indexes_t_state" in {e.id for e in result.representation.entities}
    for r in result.representation.relations:
        assert f"{r.rtype}({r.src}, {r.dst})" in text


@pytest.mark.parametrize(
    "op", [o for o in catalog() if o.arity == 2], ids=lambda op: op.name
)
def test_crossover_prompts_say_where_the_second_representation_is(op):
    text = flowed(OPERATOR_PROMPTS / f"{op.name}.txt")
    assert "two representations in order: R1" in text
    assert "drawn from the buffer" in text


@pytest.mark.parametrize("path", prompt_files(), ids=lambda p: p.name)
def test_prompt_files_have_no_tabs_and_no_crlf(path: Path):
    raw = path.read_bytes()
    assert b"\t" not in raw
    assert b"\r" not in raw
    assert raw.endswith(b"\n")


@pytest.mark.parametrize("path", prompt_files(), ids=lambda p: p.name)
def test_prompt_files_are_ascii(path: Path):
    """Smart quotes and dashes survive a copy-paste and confuse tokenisers."""
    path.read_bytes().decode("ascii")


def config_files() -> list[Path]:
    return sorted(CONFIG_DIR.rglob("*.yaml"))


@pytest.mark.parametrize("path", config_files(), ids=lambda p: p.name)
def test_config_files_have_no_tabs_and_no_crlf(path: Path):
    raw = path.read_bytes()
    assert b"\t" not in raw
    assert b"\r" not in raw
    assert raw.endswith(b"\n")


DEFAULT_YAML_EXTRAS = {"seeds": [1, 2, 3, 4, 5]}


def test_default_config_is_the_dataclass_defaults():
    loaded = Config.load(CONFIG_DIR / "default.yaml").resolved()
    expected = Config().resolved()
    expected["decoding"] = yaml.safe_load(read(CONFIG_DIR / "decoding.yaml"))
    expected.update(DEFAULT_YAML_EXTRAS)
    assert loaded == expected


def test_default_config_names_every_block():
    raw = yaml.safe_load(read(CONFIG_DIR / "default.yaml"))
    blocks = {
        "run",
        "sampling",
        "controller",
        "bandit",
        "distance",
        "novelty",
        "objective",
        "operators",
    }
    assert blocks <= set(raw)
    assert "decoding" not in raw, "decoding lives in configs/decoding.yaml only"


def test_smoke_config_runs_offline_and_small():
    cfg = Config.load(CONFIG_DIR / "smoke.yaml")
    assert cfg.run.backend == "mock"
    assert cfg.run.benchmark == "synthetic"
    assert cfg.run.budget == 8
    assert cfg.run.max_problems == 4
    assert cfg.sampling.alpha == 1.6
    assert cfg.extra["seeds"] == [1, 2, 3, 4, 5]


def test_paper_config_is_the_paper_setup():
    cfg = Config.load(CONFIG_DIR / "paper.yaml")
    assert cfg.run.backend == "hf"
    assert cfg.run.backend_model == "Qwen/Qwen2.5-7B-Instruct"
    assert cfg.run.reference_model == "Qwen/Qwen2.5-3B-Instruct"
    assert cfg.run.budget == 64
    assert cfg.distance.encoder == "sentence"
    assert cfg.extra["seeds"] == [1, 2, 3, 4, 5]


def benchmark_configs() -> list[Path]:
    return sorted(BENCHMARK_DIR.glob("*.yaml"))


def test_there_is_one_config_per_benchmark_in_the_paper():
    assert {p.stem for p in benchmark_configs()} == set(DESCRIPTOR_M)


@pytest.mark.parametrize("path", benchmark_configs(), ids=lambda p: p.stem)
def test_benchmark_config_matches_the_descriptor_table(path: Path):
    cfg = Config.load(path)
    meta = cfg.extra["benchmark"]
    assert cfg.run.benchmark == path.stem
    assert meta["descriptor_M"] == DESCRIPTOR_M[path.stem]
    assert get_descriptor(cfg.run.benchmark).n_cells == meta["descriptor_M"]


@pytest.mark.parametrize("path", benchmark_configs(), ids=lambda p: p.stem)
def test_benchmark_config_novelty_threshold_matches_the_family_table(path: Path):
    cfg = Config.load(path)
    meta = cfg.extra["benchmark"]
    assert meta["family"] in FAMILIES
    assert cfg.novelty_threshold(meta["family"]) == meta["novelty_threshold"]


@pytest.mark.parametrize("path", benchmark_configs(), ids=lambda p: p.stem)
def test_benchmark_config_verifier_and_metric(path: Path):
    meta = Config.load(path).extra["benchmark"]
    assert meta["verifier"] in VERIFIER_KINDS
    assert str(meta["metric"]).strip()
    assert isinstance(meta["size"], int) and meta["size"] > 0


@pytest.mark.parametrize("path", benchmark_configs(), ids=lambda p: p.stem)
def test_benchmark_config_inherits_the_defaults(path: Path):
    cfg = Config.load(path)
    assert cfg.sampling.alpha == 1.6
    assert cfg.run.budget == 64
    assert cfg.operators.levels == ("token", "mutation", "crossover")
