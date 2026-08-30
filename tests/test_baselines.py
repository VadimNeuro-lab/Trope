"""Contract for the sixteen baseline arms."""

from __future__ import annotations

import json
import re

import numpy as np
import pytest

from trope.backends.base import (
    CallCounter,
    DecodingParams,
    Generation,
    MeteredBackend,
)
from trope.backends.mock import MockBackend
from trope.baselines.common import BaselineResult, run_baseline
from trope.baselines.decoding import DECODING_KEYS, majority_vote
from trope.baselines.evolutionary import (
    FUNSEARCH_ISLANDS,
    MAX_VARIATION_CHARS,
    THINKING_STYLES,
    parse_variation,
)
from trope.baselines.registry import (
    BASELINE_COUNT_PAPER,
    BASELINE_NAMES,
    TASK_COMPATIBILITY,
    get_baseline,
)
from trope.baselines.search import choice_index, parse_verbalized, value_score
from trope.data.synthetic import synthetic_dataset
from trope.rng import RngTree
from trope.verify.base import get_verifier

BUDGET = 12

STOCHASTIC = tuple(name for name in BASELINE_NAMES if name != "greedy")

PAPER_DASH_CELLS: dict[str, set[str]] = {
    "funsearch": {"usamo", "noveltybench", "creativityprism", "uot", "researchbench"},
    "eureka": {
        "math500",
        "aime",
        "usamo",
        "noveltybench",
        "creativityprism",
        "uot",
        "llmsrbench",
        "researchbench",
    },
}

ALL_BENCHMARKS = (
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


@pytest.fixture(scope="module")
def dataset():
    return synthetic_dataset(n=6, seed=0)


def run_arm(
    name, dataset, *, seed=1, budget=BUDGET, index=0, backend=None, inner=None, **kw
):
    """One arm on one problem, with a fresh counter. Returns (result, counter)."""
    problem = dataset[index]
    counter = CallCounter()
    inner = inner if inner is not None else MockBackend(dataset, seed=0)
    metered = MeteredBackend(inner, counter, budget=budget)
    verifier = get_verifier(problem, backend=metered.for_role("judge"))
    result = get_baseline(name)(
        problem,
        backend if backend is not None else metered,
        verifier,
        budget,
        RngTree(seed).stream(f"baseline/{name}/{problem.id}"),
        **kw,
    )
    return result, counter


VARIATION_ARMS = ("promptbreeder", "evoprompt", "eureka")

PARSED_BUDGET = {"promptbreeder": 24, "evoprompt": 24, "eureka": 18}

MARKER_PHRASE = "rewritten for call"


class Compliant(MockBackend):
    """A backbone that answers a variation call in the format it asked for."""

    _MARKER = re.compile(r'beginning "([A-Za-z]+)"')

    def generate(self, prompt, params, *, seed=None, role="generator"):
        found = self._MARKER.search(prompt)
        if found is None:
            return super().generate(prompt, params, seed=seed, role=role)
        marker = found.group(1)
        text = f"Considering the rewrite.\n{marker}: {marker.lower()} {MARKER_PHRASE} {seed}"
        return Generation(
            text=text,
            prompt_tokens=self.count_tokens(prompt),
            completion_tokens=self.count_tokens(text),
            meta={"role": role, "backend": "compliant"},
        )


class Opaque:
    """A backend that hides `remaining`, so the arm cannot pre-clamp its budget."""

    def __init__(self, inner):
        self.inner = inner
        self.name = inner.name

    def generate(self, prompt, params, *, seed=None, role="generator"):
        return self.inner.generate(prompt, params, seed=seed, role=role)

    def score(self, continuation, prefix=""):
        return self.inner.score(continuation, prefix)

    def count_tokens(self, text):
        return self.inner.count_tokens(text)


@pytest.mark.parametrize("name", BASELINE_NAMES)
def test_every_baseline_runs_end_to_end(name, dataset):
    result, _ = run_arm(name, dataset)
    assert isinstance(result, BaselineResult)
    assert result.candidates, f"{name} produced no candidates"
    for candidate in result.candidates:
        assert set(candidate) == {"text", "verified", "verdict", "iteration", "meta"}
        assert isinstance(candidate["text"], str) and candidate["text"]
        assert isinstance(candidate["verified"], bool)
        assert 0.0 <= candidate["verdict"] <= 1.0
        assert candidate["iteration"] >= 1
    assert result.best in result.candidates


@pytest.mark.parametrize("name", BASELINE_NAMES)
def test_no_baseline_exceeds_the_budget(name, dataset):
    result, counter = run_arm(name, dataset)
    assert counter.get("generator") <= BUDGET
    assert result.generator_calls == counter.get("generator")
    assert len(result.candidates) <= BUDGET


@pytest.mark.parametrize("name", BASELINE_NAMES)
def test_every_baseline_spends_the_whole_budget(name, dataset):
    """Matched budget, not "at most" budget."""
    _, counter = run_arm(name, dataset)
    assert counter.get("generator") == BUDGET


@pytest.mark.parametrize("name", BASELINE_NAMES)
def test_a_tighter_backend_budget_stops_the_arm_cleanly(name, dataset):
    problem = dataset[0]
    counter = CallCounter()
    metered = MeteredBackend(MockBackend(dataset, seed=0), counter, budget=5)
    verifier = get_verifier(problem, backend=metered.for_role("judge"))
    result = get_baseline(name)(
        problem,
        Opaque(metered),
        verifier,
        BUDGET,
        RngTree(1).stream("baseline/tight"),
    )
    assert counter.get("generator") == 5
    assert result.generator_calls <= 5


@pytest.mark.parametrize("name", BASELINE_NAMES)
def test_arms_are_deterministic_under_a_fixed_seed(name, dataset):
    first, counter_a = run_arm(name, dataset, seed=4)
    second, counter_b = run_arm(name, dataset, seed=4)
    assert [c["text"] for c in first.candidates] == [c["text"] for c in second.candidates]
    assert [c["verdict"] for c in first.candidates] == [
        c["verdict"] for c in second.candidates
    ]
    assert counter_a.as_dict() == counter_b.as_dict()


@pytest.mark.parametrize("name", STOCHASTIC)
def test_stochastic_arms_move_with_the_seed(name, dataset):
    first, _ = run_arm(name, dataset, seed=4)
    second, _ = run_arm(name, dataset, seed=5)
    assert [c["text"] for c in first.candidates] != [c["text"] for c in second.candidates]


def test_greedy_does_not_move_with_the_seed(dataset):
    first, _ = run_arm("greedy", dataset, seed=4)
    second, _ = run_arm("greedy", dataset, seed=5)
    texts = [c["text"] for c in first.candidates]
    assert texts == [c["text"] for c in second.candidates]
    assert len(set(texts)) == 1, "argmax decoding returned two different answers"


def test_registry_count_matches_the_papers_arithmetic():
    """Sixteen arms, and the paper's "15", reconciled."""
    methods_in_prose = 14
    temperature_values = 3
    assert len(BASELINE_NAMES) == methods_in_prose - 1 + temperature_values == 16

    config_table_rows = 13
    assert BASELINE_COUNT_PAPER == config_table_rows - 1 + temperature_values == 15
    assert len(BASELINE_NAMES) == BASELINE_COUNT_PAPER + 1
    assert "eta" in BASELINE_NAMES


def test_registry_names_and_order_match_the_tables():
    from trope.analysis.tables import BASELINE_ORDER

    assert tuple(name for name, _ in BASELINE_ORDER) == BASELINE_NAMES
    assert len(DECODING_KEYS) == 8
    assert set(DECODING_KEYS) <= set(BASELINE_NAMES)


def test_unknown_baseline_names_what_exists():
    with pytest.raises(KeyError) as excinfo:
        get_baseline("beam_search")
    message = str(excinfo.value)
    assert "beam_search" in message
    for name in ("greedy", "uot", "self_consistency"):
        assert name in message


def test_task_compatibility_matches_the_paper_dashes():
    for arm, dashed in PAPER_DASH_CELLS.items():
        allowed = set(TASK_COMPATIBILITY[arm])
        assert allowed == set(ALL_BENCHMARKS) - dashed
    assert set(TASK_COMPATIBILITY) == set(PAPER_DASH_CELLS)


def test_tables_reads_the_compatibility_map():
    from trope.analysis.tables import _incompatible, _task_compatibility

    table, note = _task_compatibility()
    assert table is not None and "registry" in note
    assert _incompatible(table, "funsearch", "usamo")
    assert _incompatible(table, "eureka", "math500")
    assert not _incompatible(table, "eureka", "livecodebench")
    assert not _incompatible(table, "self_consistency", "usamo")


def test_majority_vote_counts_and_normalises():
    votes = majority_vote(
        [
            "the answer is 7. This took 3 steps.",
            "so we get \\boxed{07}",
            "clearly \\boxed{12}",
            "Final answer: 7",
            "no answer here",
        ]
    )
    assert votes.answer == "7"
    assert votes.votes == 3
    assert votes.counts == {"7": 3, "12": 1}
    assert votes.winner_index == 0
    assert votes.tied == ("7",)


def test_majority_vote_breaks_ties_towards_the_earlier_answer():
    votes = majority_vote(["\\boxed{5}", "\\boxed{9}", "\\boxed{9}", "\\boxed{5}"])
    assert votes.answer == "5"
    assert votes.tied == ("5", "9")
    assert votes.winner_index == 0


def test_majority_vote_abstains_when_nothing_states_an_answer():
    votes = majority_vote(["I am not sure.", ""])
    assert votes.answer is None
    assert votes.winner_index is None
    assert votes.counts == {}


def test_self_consistency_records_its_vote(dataset):
    result, _ = run_arm("self_consistency", dataset, seed=2)
    meta = result.meta
    assert meta["majority_answer"] is not None
    assert meta["votes"] == max(meta["counts"].values())
    assert sum(meta["counts"].values()) + meta["abstentions"] == len(result.candidates)
    assert result.best["meta"]["majority"] is True
    assert result.best["meta"]["majority"] is not None


def test_tot_splits_its_budget_between_proposal_and_evaluation(dataset):
    result, counter = run_arm("tot", dataset, budget=30, seed=3)
    meta = result.meta
    assert (meta["breadth"], meta["depth"]) == (5, 3)
    assert meta["calls_per_tree"] == 30
    assert meta["proposal_calls"] == len(result.candidates) == 15
    assert meta["value_calls"] == 15
    assert counter.get("generator") == 30
    assert all("value" in c["meta"] for c in result.candidates)


def test_uot_applies_all_three_regimes(dataset):
    result, _ = run_arm("uot", dataset, budget=24, seed=3)
    assert all(count > 0 for count in result.meta["by_regime"].values())
    assert set(result.meta["by_regime"]) == {
        "exploratory",
        "combinatorial",
        "transformational",
    }
    assert all(0.0 <= c["meta"]["novelty"] <= 1.0 for c in result.candidates)


def test_funsearch_spreads_its_calls_over_the_islands(dataset):
    result, _ = run_arm("funsearch", dataset, budget=8, seed=3)
    islands = {c["meta"]["island"] for c in result.candidates}
    assert islands == {0, 1, 2, 3}


def test_funsearch_splits_K_across_the_islands(dataset):
    """the baseline hyperparameter table (`tab:baselinecfg`) against its own caption, and which reading the code takes."""
    budget = 8
    problem = dataset[0]
    counter = CallCounter()
    backend = MeteredBackend(
        MockBackend(dataset, seed=0), counter, budget=budget * FUNSEARCH_ISLANDS
    )
    verifier = get_verifier(problem, backend=backend.for_role("judge"))
    result = get_baseline("funsearch")(
        problem,
        backend,
        verifier,
        budget,
        RngTree(1).stream("baseline/funsearch/split"),
    )
    assert counter.get("generator") == budget
    assert result.meta["matched_budget"] is True
    assert result.meta["budget_requested"] == budget
    assert result.meta["islands"] == FUNSEARCH_ISLANDS
    assert sum(result.meta["island_sizes"]) == len(result.candidates)


@pytest.mark.parametrize("name", VARIATION_ARMS)
def test_the_evolutionary_arms_pay_for_their_variation_calls(name, dataset):
    """Variation is LLM-driven, and charged to K like anything else."""
    result, counter = run_arm(name, dataset, seed=3)
    stats = result.meta["variation_calls"]
    assert stats["calls"] >= 1
    assert counter.get("generator") == BUDGET
    assert len(result.candidates) + stats["calls"] == BUDGET


@pytest.mark.parametrize("name", VARIATION_ARMS)
def test_llm_variation_is_paid_for_in_candidates_not_in_budget(name, dataset):
    """The honest consequence: fewer candidates, never more than K calls."""
    result, counter = run_arm(name, dataset, budget=64, seed=3)
    assert counter.get("generator") == 64
    nominal = result.meta["nominal_generations"]
    per_generation = result.meta.get("population") or result.meta["samples_per_generation"]
    assert nominal * per_generation == 64
    assert len(result.candidates) < 64


@pytest.mark.parametrize("name", VARIATION_ARMS)
def test_a_variation_reply_that_parses_becomes_the_next_instruction(name, dataset):
    result, counter = run_arm(
        name,
        dataset,
        seed=3,
        budget=PARSED_BUDGET[name],
        inner=Compliant(dataset, seed=0),
    )
    stats = result.meta["variation_calls"]
    assert stats["calls"] >= 1
    assert stats["parsed"] == stats["calls"] and stats["unparsed"] == 0
    assert counter.get("generator") == PARSED_BUDGET[name]
    used = " ".join(
        [str(result.meta.get("reflection", ""))]
        + [str(c["meta"].get("instruction", "")) for c in result.candidates]
    )
    assert MARKER_PHRASE in used


@pytest.mark.parametrize("name", VARIATION_ARMS)
def test_an_unusable_variation_reply_falls_back_to_the_catalogue(name, dataset):
    """The mock never emits the marker line, so every reply is unusable."""
    result, _ = run_arm(name, dataset, seed=3, budget=24)
    stats = result.meta["variation_calls"]
    assert stats["calls"] >= 1
    assert stats["parsed"] == 0 and stats["unparsed"] == stats["calls"]
    instructions = [str(c["meta"].get("instruction", "")) for c in result.candidates]
    assert all(MARKER_PHRASE not in text for text in instructions)
    if name != "eureka":
        assert any(text in THINKING_STYLES for text in instructions)


@pytest.mark.parametrize("name", VARIATION_ARMS)
def test_llm_variation_is_deterministic_under_a_fixed_seed(name, dataset):
    first, counter_a = run_arm(
        name, dataset, seed=7, budget=24, inner=Compliant(dataset, seed=0)
    )
    second, counter_b = run_arm(
        name, dataset, seed=7, budget=24, inner=Compliant(dataset, seed=0)
    )
    assert [c["text"] for c in first.candidates] == [c["text"] for c in second.candidates]
    assert first.meta["variation_calls"] == second.meta["variation_calls"]
    assert counter_a.as_dict() == counter_b.as_dict()


def test_parse_variation_reads_the_marked_line_only():
    assert (
        parse_variation("Reasoning.\nInstruction: name the constraints first.", "Instruction")
        == "name the constraints first."
    )
    assert (
        parse_variation("Instruction: first try\nInstruction: the second try", "Instruction")
        == "the second try"
    )
    assert (
        parse_variation("- **Rule:** rewrite it to demand a check", "Rule")
        == "rewrite it to demand a check"
    )
    assert (
        parse_variation("instruction: case does not matter", "Instruction")
        == "case does not matter"
    )


def test_parse_variation_rejects_a_reply_it_cannot_use():
    assert parse_variation("Working in the algebra frame.\nStep 1: reduce.", "Instruction") is None
    assert parse_variation("Instruction: no", "Instruction") is None
    assert parse_variation("Instruction: the answer is \\boxed{42}", "Instruction") is None
    assert parse_variation("Rule: rewrite the instruction", "Instruction") is None
    body = parse_variation("Instruction: " + "restate the goal. " * 100, "Instruction")
    assert body is not None and len(body) <= MAX_VARIATION_CHARS


def test_verbalized_distribution_is_parsed_and_falls_back():
    items, parsed = parse_verbalized(
        "0.5 | use the closed form\n"
        "2. 0.3 | expand the first few terms\n"
        "p = 0.2 | bound it and check the bound\n"
        "Step 1: this line is not an option\n",
        limit=10,
    )
    assert parsed
    assert [round(w, 2) for w, _ in items] == [0.5, 0.3, 0.2]
    assert items[0][1] == "use the closed form"

    items, parsed = parse_verbalized(
        "Working in the algebra frame.\nStep 1: reduce.", limit=10
    )
    assert not parsed
    assert len(items) == 2 and all(w == 1.0 for w, _ in items)


def test_backbone_numbers_are_read_with_the_verifiers_extractor():
    assert value_score("I rate this \\boxed{8}") == pytest.approx(0.8)
    assert value_score("no number at all") == pytest.approx(0.5)
    assert 0.0 <= value_score("the answer is 137") <= 1.0
    assert choice_index("the best is \\boxed{2}", 4) == 2
    assert choice_index("\\boxed{9}", 4) == 1


@pytest.mark.parametrize("name", ["funsearch", "eureka"])
def test_the_code_adapted_arms_run_on_a_code_benchmark(name):
    data = synthetic_dataset(n=2, family="code", seed=0)
    result, counter = run_arm(name, data, budget=4, seed=1)
    assert counter.get("generator") == 4
    assert any(c["verified"] for c in result.candidates)


def test_run_baseline_dispatches_by_name(dataset):
    problem = dataset[0]
    counter = CallCounter()
    backend = MeteredBackend(MockBackend(dataset, seed=0), counter, budget=4)
    verifier = get_verifier(problem, backend=backend.for_role("judge"))
    result = run_baseline(
        "temp_1.0", problem, backend, verifier, 4, np.random.default_rng(0)
    )
    assert result.generator_calls == 4
    assert result.meta["arm"] == "temp_1.0"


def test_decoding_arms_use_the_configured_parameters(dataset):
    from trope.baselines.common import baseline_params

    greedy = baseline_params("greedy")
    assert greedy == DecodingParams(temperature=0.0, max_tokens=greedy.max_tokens)
    assert baseline_params("temperature_12").temperature == 1.2
    assert baseline_params("top_p").top_p == 0.95
    assert baseline_params("min_p").min_p == 0.1
    assert baseline_params("top_h").entropy_budget == 1.0
    assert baseline_params("eta_sampling").eta == 0.0003
    assert baseline_params("temperature_10").top_p is None


@pytest.mark.parametrize("name", BASELINE_NAMES)
def test_results_survive_a_round_trip_through_json(name, dataset):
    result, _ = run_arm(name, dataset, budget=6)
    blob = json.dumps(result.to_dict())
    assert json.loads(blob)["generator_calls"] == result.generator_calls
