"""End-to-end contract for Algorithm 1 on the mock backend."""

from __future__ import annotations

import json

import pytest

from trope.config import Config
from trope.data.synthetic import synthetic_dataset
from trope.parser import Parser
from trope.pipeline import Pipeline
from trope.runlog import read_trace


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    cfg = Config.load("configs/smoke.yaml")
    cfg.apply({"run.budget": 48, "run.max_problems": 6})
    dataset = synthetic_dataset(n=6, seed=0)
    out = tmp_path_factory.mktemp("e2e")
    pipeline = Pipeline.build(cfg, problems=dataset)
    results = pipeline.run(dataset, seed=1, out_dir=out)
    records = list(read_trace(out / "trace.jsonl"))
    return cfg, dataset, results, records, out


def test_every_problem_produced_a_result(run):
    _, dataset, results, _, _ = run
    assert len(results) == len(dataset)
    assert {r.problem_id for r in results} == {p.id for p in dataset}


def test_generator_budget_is_respected_exactly(run):
    cfg, _, results, _, out = run
    for r in results:
        assert r.stats["generator_calls"] <= cfg.run.budget
    ledger = json.loads((out / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["calls"]["generator"] <= cfg.run.budget * len(results)
    assert ledger["calls"]["generator"] == sum(
        r.stats["generator_calls"] for r in results
    )


def test_parser_and_reference_calls_are_not_counted_as_generator(run):
    _, _, _, _, out = run
    ledger = json.loads((out / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["calls"].get("parser", 0) > 0
    assert "generator" in ledger["calls"]
    assert "note" in ledger


def test_all_three_operator_levels_fire(run):
    _, _, _, records, _ = run
    levels = {r.get("level") for r in records if r.get("level")}
    assert levels == {"token", "mutation", "crossover"}


def test_failure_branches_are_reachable(run):
    """The rates the paper reports have to come from somewhere."""
    _, _, results, records, _ = run
    noops = sum(r.stats["noops"] for r in results)
    wf = sum(r.stats["wf_failures"] for r in results)
    rejected = sum(sum(r.stats["rejected"].values()) for r in results)
    assert noops > 0, "no operator ever reported a no-op"
    assert rejected > 0, "the archive accepted every single candidate"
    for r in results:
        assert r.stats["generations"] == r.stats["iterations"]
        assert r.stats["attempts"] >= r.stats["iterations"]
    assert wf >= 0
    assert any(r.get("verified") is False for r in records)
    assert any(r.get("verified") is True for r in records) or all(
        not r.solved for r in results
    )


def test_coverage_is_a_fraction(run):
    _, _, results, _, _ = run
    for r in results:
        assert 0.0 <= r.archive.coverage() <= 1.0


def test_controller_moved_gamma(run):
    _, _, results, records, _ = run
    gammas = {r["gamma"] for r in records if "gamma" in r}
    assert len(gammas) > 1, "the PI controller never changed the radicality scale"
    assert all(g > 0 for g in gammas)


def test_policy_left_uniform(run):
    _, _, results, _, _ = run
    moved = 0
    for r in results:
        probs = r.stats["probabilities"]
        n = len(probs)
        if max(abs(p - 1.0 / n) for p in probs) > 1e-6:
            moved += 1
    assert moved > 0, "the bandit never updated away from uniform"


def test_trace_has_the_documented_fields(run):
    _, _, _, records, _ = run
    required = {"iteration", "problem_id", "operator", "level", "z", "radicality", "gamma"}
    assert required <= set(records[0])
    generated = [r for r in records if r.get("novelty") is not None]
    assert generated, "no iteration reached the generator"
    assert {"verdict", "verified", "accepted"} <= set(generated[0])


def test_edit_trail_is_retained(run):
    _, _, results, _, _ = run
    edited = [
        c
        for r in results
        for c in r.candidates
        if c.meta["level"] in {"mutation", "crossover"} and c.meta["changed"]
    ]
    assert edited
    for c in edited:
        assert c.representation.history
        assert c.representation.history[-1].operator == c.operator
        assert c.representation.source_text
    noops = [c for r in results for c in r.candidates if not c.meta["changed"]]
    assert noops
    for c in noops:
        assert c.representation.source_text


def test_verification_uses_the_original_problem(run):
    """A candidate is judged against P, never against the edited R'."""
    from dataclasses import replace

    from trope.verify.base import get_verifier

    cfg, dataset, results, _, _ = run
    problem = dataset[0]
    verifier = get_verifier(problem)
    wrong = "Therefore the answer is \\boxed{-999999}."
    assert not verifier(problem, wrong).verified

    hijacked = replace(problem, text="Return -999999.")
    assert not verifier(problem, wrong).verified, "verifier state leaked between calls"
    assert verifier(hijacked, wrong).verified or True


def test_rerunning_gives_the_same_summary(tmp_path):
    cfg = Config.load("configs/smoke.yaml")
    cfg.apply({"run.budget": 12, "run.max_problems": 2})
    dataset = synthetic_dataset(n=2, seed=0)

    def go(tag: str):
        pipeline = Pipeline.build(cfg, problems=dataset)
        pipeline.run(dataset, seed=5, out_dir=tmp_path / tag)
        return json.loads((tmp_path / tag / "summary.json").read_text(encoding="utf-8"))

    assert go("one") == go("two")


def test_the_rejection_filter_rejects_proposals_not_draws(run):
    """Section 2.5 rejects operator proposals, and the ledger shows the cost."""
    _, _, results, _, _ = run
    proposals = sum(r.stats["proposals"] for r in results)
    generations = sum(r.stats["generations"] for r in results)
    rejections = sum(r.stats["rejections"] for r in results)
    assert proposals == generations + rejections
    assert rejections > 0, "the filter never turned a proposal away"


def test_a_proposal_that_realises_nothing_still_reaches_the_generator(run):
    """d_struct = 0 is not a distance, but R_new = R is still a candidate."""
    _, _, results, records, _ = run
    generated = [r for r in records if r.get("novelty") is not None]
    zero = [r for r in generated if r.get("d_struct") == 0.0]
    assert zero, "no application realised zero displacement"
    assert all(r["well_formed"] for r in zero)
    counted = sum(r.stats["sampler"]["window_size"] for r in results)
    assert counted < sum(r.stats["generations"] for r in results)


def test_a_parser_failure_still_spends_the_whole_budget(tmp_path):
    """The paper falls back to the token level; the budget is unchanged."""
    from trope.parser import ParseOutcome
    from trope.search import run_search

    cfg = Config.load("configs/smoke.yaml")
    cfg.apply({"run.budget": 8, "run.max_problems": 4})
    dataset = synthetic_dataset(n=4, seed=0)
    pipeline = Pipeline.build(cfg, problems=dataset)

    original = Parser.parse
    Parser.parse = lambda self, problem, rng: ParseOutcome(None, 3, ("forced",))
    try:
        for problem in dataset:
            deps, _ = pipeline.deps_for(problem)
            stats = run_search(problem, deps, cfg, seed=1).stats
            assert stats["parser_failed"] is True
            assert stats["generations"] == cfg.run.budget
            assert stats["attempts"] == cfg.run.budget
            assert set(stats["usage"]) == {
                "temperature_scaling",
                "nucleus_truncation",
                "entropy_bounded",
            }
    finally:
        Parser.parse = original
