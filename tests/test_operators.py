"""Tests for the 11-operator catalog."""

from __future__ import annotations

import copy
import math
from dataclasses import replace
from itertools import pairwise, permutations

import numpy as np
import pytest

from trope.backends.base import DecodingParams
from trope.isomorphism import (
    _colour_multiset,
    _colours,
    compare,
    structurally_isomorphic,
)
from trope.operators.base import (
    EditResult,
    canonical_parts,
    catalog,
    get,
    load_resources,
    rank_index,
    settled,
    unit_rho,
    well_formed,
)
from trope.types import (
    ENTITY_TYPES,
    RELATION_TYPES,
    Assumption,
    EditRecord,
    Entity,
    Goal,
    Relation,
    Representation,
)

EXPECTED_KIND = {
    "temperature_scaling": "token",
    "nucleus_truncation": "token",
    "entropy_bounded": "token",
    "assumption_violation": "mutation",
    "type_shifting": "mutation",
    "foundational_negation": "mutation",
    "reification": "mutation",
    "structural_transplant": "crossover",
    "categorical_import": "crossover",
    "role_swap": "crossover",
    "goal_pareto_inversion": "crossover",
}

RHOS = (0.0, 0.4, 1.0, 2.41, 3.7, 6.0, 7.9, 8.0, 1e6)

ASSUMPTION_TEXTS = (
    "the triangle inequality holds",
    "the input is read once, in order",
    "samples are independent",
    "the constraints are linear",
    "n is finite",
    " ",
)


@pytest.fixture(scope="module")
def res():
    """Resources with no token_params, so the token operators use defaults."""
    return load_resources()


@pytest.fixture(scope="module")
def res_cfg():
    return load_resources(
        token_params={
            "temperature_scaling": {"T0": 0.2, "T_max": 2.0},
            "nucleus_truncation": {"R_max": 2.0, "p_min": 0.10},
            "entropy_bounded": {"bits_per_rho": 0.5, "min_bits": 0.25, "max_bits": 3.0},
        }
    )


@pytest.fixture(scope="module")
def euclid():
    return Representation(
        entities=(
            Entity("ABC", "constant", "triangle", "the triangle"),
            Entity("K", "output", "area", "its area"),
            Entity("a", "variable", "side_length", "side BC"),
            Entity("b", "variable", "side_length", "side CA"),
        ),
        relations=(
            Relation("K", "ABC", "depends_on"),
            Relation("a", "ABC", "part_of"),
            Relation("b", "ABC", "part_of"),
        ),
        assumptions=(
            Assumption("the triangle inequality holds", load_bearing=True),
            Assumption("K>0", load_bearing=False),
        ),
        goal=Goal("prove a^2 + b^2 + c^2 >= 4 sqrt(3) K", "the triangle is non-degenerate"),
        frame="euclidean-geometry",
    )


@pytest.fixture(scope="module")
def streaming():
    return Representation(
        entities=(
            Entity("M", "parameter", "memory_bound", "memory budget"),
            Entity("est", "output", "estimate", "the reported median"),
            Entity("s", "input", "stream", "the input stream"),
        ),
        relations=(
            Relation("M", "est", "bounds"),
            Relation("est", "s", "depends_on"),
        ),
        assumptions=(Assumption("the input is read once, in order", load_bearing=True),),
        goal=Goal("return the median of the stream", "memory <= M"),
        frame="streaming-algorithms",
    )


def _make_rep(rng: np.random.Generator, res, index: int) -> Representation:
    """A deterministic pseudo-parser, including the degenerate shapes."""
    frames = sorted(res.frames)
    sorts = [*sorted(res.sort_lattice), "", "unlisted_sort"]
    frame = frames[int(rng.integers(len(frames)))]

    n_entities = int(rng.integers(1, 9))
    n_relations = int(rng.integers(0, 2 * n_entities + 1))
    types = [ENTITY_TYPES[int(rng.integers(len(ENTITY_TYPES)))] for _ in range(n_entities)]
    entity_sorts = [sorts[int(rng.integers(len(sorts)))] for _ in range(n_entities)]

    if index == 0:
        n_entities, n_relations = 1, 0
        types, entity_sorts = types[:1], entity_sorts[:1]
    elif index == 1:
        n_relations = 0
    elif index == 2:
        types = ["variable"] * n_entities
    elif index == 3:
        entity_sorts = [""] * n_entities
    elif index == 4:
        entity_sorts = ["memory_bound"] * n_entities

    ids = [f"e{k}" for k in range(n_entities)]
    entities = tuple(
        Entity(eid, t, s, f"label {eid}")
        for eid, t, s in zip(ids, types, entity_sorts, strict=False)
    )
    relations = []
    for _ in range(n_relations):
        src = ids[int(rng.integers(len(ids)))]
        dst = ids[int(rng.integers(len(ids)))] if index != 5 else src
        relations.append(
            Relation(src, dst, RELATION_TYPES[int(rng.integers(len(RELATION_TYPES)))])
        )
    if index == 6 and relations:
        relations.append(relations[0])

    n_assumptions = 1 if index == 7 else int(rng.integers(1, 4))
    assumptions = tuple(
        Assumption(
            ASSUMPTION_TEXTS[int(rng.integers(len(ASSUMPTION_TEXTS)))],
            load_bearing=bool(k == 0),
        )
        for k in range(n_assumptions)
    )
    goal = Goal(
        f"objective {index % 5}",
        "" if index % 3 == 0 else f"constraint {index % 4}",
    )
    entities = tuple(sorted(entities, key=lambda e: e.id))
    relations = tuple(
        sorted(set(relations), key=lambda r: (r.src, r.dst, r.rtype))
    )
    return Representation(
        entities=entities,
        relations=relations,
        assumptions=assumptions,
        goal=goal,
        frame=frame,
    )


@pytest.fixture(scope="module")
def corpus(res):
    rng = np.random.default_rng(20260829)
    return [_make_rep(rng, res, i) for i in range(200)]


def test_catalog_has_exactly_the_eleven_named_operators():
    ops = catalog()
    assert len(ops) == 11
    assert {op.name for op in ops} == set(EXPECTED_KIND)
    assert {op.name: op.kind for op in ops} == EXPECTED_KIND


def test_catalog_level_sizes_and_arities():
    ops = catalog()
    per_level = {level: [o for o in ops if o.kind == level] for level in
                 ("token", "mutation", "crossover")}
    assert [len(per_level[k]) for k in ("token", "mutation", "crossover")] == [3, 4, 4]
    for op in ops:
        assert op.arity == (2 if op.kind == "crossover" else 1)
        assert get(op.name) is op


def test_token_operators_return_decoding_and_never_touch_r(res, euclid):
    for name in ("temperature_scaling", "nucleus_truncation", "entropy_bounded"):
        result = get(name).apply(euclid, 1.7, np.random.default_rng(0), res)
        assert result.changed
        assert result.representation is None
        assert isinstance(result.decoding, DecodingParams)


def test_temperature_scaling_known_values(res, res_cfg, euclid):
    op = get("temperature_scaling")

    def temp(rho, resources):
        return op.apply(euclid, rho, np.random.default_rng(0), resources).decoding.temperature

    assert temp(0.0, res) == pytest.approx(0.5)
    assert temp(res.rho_max / 2, res) == pytest.approx(1.0)
    assert temp(res.rho_max, res) == pytest.approx(1.5)
    assert temp(1e6, res) == pytest.approx(1.5)
    assert temp(0.0, res_cfg) == pytest.approx(0.2)
    assert temp(2.0, res_cfg) == pytest.approx(0.2 + 0.25 * 1.8)
    assert temp(1e6, res_cfg) == pytest.approx(2.0)


def test_temperature_is_non_decreasing_in_radicality(res, euclid):
    op = get("temperature_scaling")
    temps = [
        op.apply(euclid, rho, np.random.default_rng(0), res).decoding.temperature
        for rho in RHOS
    ]
    assert temps == sorted(temps)
    assert temps[0] < temps[-1]


def test_nucleus_truncation_known_values_and_direction(res, res_cfg, euclid):
    op = get("nucleus_truncation")

    def top_p(rho, resources):
        return op.apply(euclid, rho, np.random.default_rng(0), resources).decoding.top_p

    assert top_p(0.0, res) == pytest.approx(1.0)
    assert top_p(2.0, res) == pytest.approx(0.75)
    assert top_p(4.0, res) == pytest.approx(0.5)
    assert top_p(8.0, res) == pytest.approx(0.05)
    assert top_p(1e6, res) == pytest.approx(0.05)
    assert top_p(1.0, res_cfg) == pytest.approx(0.5)
    assert top_p(1e6, res_cfg) == pytest.approx(0.10)


def test_nucleus_is_non_increasing_in_radicality(res, euclid):
    op = get("nucleus_truncation")
    ps = [
        op.apply(euclid, rho, np.random.default_rng(0), res).decoding.top_p
        for rho in RHOS
    ]
    assert ps == sorted(ps, reverse=True)
    assert ps[0] > ps[-1]


def test_entropy_budget_known_values_and_monotone(res, res_cfg, euclid):
    op = get("entropy_bounded")

    def bits(rho, resources):
        return op.apply(euclid, rho, np.random.default_rng(0), resources).decoding.entropy_budget

    assert bits(0.0, res) == pytest.approx(0.15)
    assert bits(2.41, res) == pytest.approx(2.41)
    assert bits(1e6, res) == pytest.approx(6.0)
    assert bits(1.0, res_cfg) == pytest.approx(0.5)
    assert bits(0.0, res_cfg) == pytest.approx(0.25)
    assert bits(1e6, res_cfg) == pytest.approx(3.0)
    budgets = [bits(rho, res) for rho in RHOS]
    assert budgets == sorted(budgets)


def test_operators_do_not_mutate_their_inputs(res, euclid, streaming):
    before_rep, before_other = copy.deepcopy(euclid), copy.deepcopy(streaming)
    for op in catalog():
        for rho in RHOS:
            op.apply(euclid, rho, np.random.default_rng(3), res, other=streaming)
            assert euclid == before_rep
            assert streaming == before_other


def test_same_seed_reproduces_the_same_representation(res, euclid, streaming):
    for op in catalog():
        for rho in (0.7, 3.7, 9.1):
            a = op.apply(euclid, rho, np.random.default_rng(11), res, other=streaming)
            b = op.apply(euclid, rho, np.random.default_rng(11), res, other=streaming)
            assert a.changed == b.changed
            assert a.detail == b.detail
            if a.representation is not None:
                assert a.representation.fingerprint() == b.representation.fingerprint()
            assert a.decoding == b.decoding


@pytest.mark.parametrize(
    "name", ["assumption_violation", "type_shifting", "reification", "structural_transplant"]
)
def test_stochastic_operators_depend_on_the_seed(res, name, streaming):
    rep = Representation(
        entities=tuple(
            Entity(f"e{i}", ENTITY_TYPES[i % len(ENTITY_TYPES)], "side_length")
            for i in range(6)
        ),
        relations=tuple(Relation(f"e{i}", f"e{i + 1}", "depends_on") for i in range(5)),
        assumptions=tuple(
            Assumption(t, load_bearing=(i == 0))
            for i, t in enumerate(ASSUMPTION_TEXTS[:5])
        ),
        goal=Goal("find x", "x > 0"),
        frame="algebra",
    )
    op = get(name)
    prints = {
        op.apply(rep, 2.0, np.random.default_rng(seed), res, other=streaming)
        .representation.fingerprint()
        for seed in range(8)
    }
    assert len(prints) > 1


@pytest.mark.parametrize("rho", [0.1, 1.0, 1.5, 2.0, 3.4, 12.0, 1e6])
def test_assumption_violation_flips_ceil_rho_assumptions(res, euclid, rho):
    result = get("assumption_violation").apply(euclid, rho, np.random.default_rng(5), res)
    expected = min(math.ceil(rho), len(euclid.assumptions))
    flipped = sum(
        1
        for before, after in zip(euclid.assumptions, result.representation.assumptions, strict=False)
        if before.negated != after.negated
    )
    assert flipped == expected
    assert len(result.representation.assumptions) == len(euclid.assumptions)
    assert [a.text for a in result.representation.assumptions] == [
        a.text for a in euclid.assumptions
    ]


def test_assumption_violation_noops_at_zero_and_without_assumptions(res, euclid):
    op = get("assumption_violation")
    assert not op.apply(euclid, 0.0, np.random.default_rng(5), res).changed
    bare = Representation(
        entities=(Entity("x", "variable"),), goal=Goal("solve"), frame="algebra"
    )
    result = op.apply(bare, 3.0, np.random.default_rng(5), res)
    assert not result.changed and result.representation is None


def test_type_shifting_walks_down_the_similarity_ranking(res):
    rep = Representation(
        entities=(Entity("v", "variable", "side_length"),),
        assumptions=(Assumption("a", load_bearing=True),),
        goal=Goal("solve"),
        frame="algebra",
    )
    row = res.type_similarity["variable"]
    seen = [
        get("type_shifting")
        .apply(rep, rho, np.random.default_rng(2), res)
        .representation.entity("v")
        .type
        for rho in RHOS
    ]
    ranked = sorted((t for t in row if t != "variable"), key=lambda t: (-row[t], t))
    reachable = [
        set(ranked[rank_index(rho, len(ranked), res) :]) or {ranked[-1]} for rho in RHOS
    ]
    assert all(b <= a for a, b in pairwise(reachable))
    assert all(t in pool for t, pool in zip(seen, reachable, strict=True))
    assert min(row[t] for t in seen) <= row[seen[0]]
    assert "variable" not in seen


def test_type_shifting_shifts_sort_only_above_the_gate(res):
    rep = Representation(
        entities=(Entity("M", "parameter", "memory_bound"),),
        assumptions=(Assumption("bounded memory", load_bearing=True),),
        goal=Goal("return the median"),
        frame="streaming-algorithms",
    )
    op = get("type_shifting")
    for rho in (0.0, 1.0, 3.9):
        assert unit_rho(rho, res) <= 0.5
        result = op.apply(rep, rho, np.random.default_rng(4), res)
        assert result.representation.entity("M").sort == "memory_bound"
    for rho in (5.0, 7.9, 1e6):
        assert unit_rho(rho, res) > 0.5
        shifted = op.apply(rep, rho, np.random.default_rng(4), res).representation
        sort = shifted.entity("M").sort
        assert sort != "memory_bound"
        assert res.supertype(sort) == res.supertype("memory_bound")


def test_type_shifting_retypes_incident_relations_consistently(res):
    rep = Representation(
        entities=(Entity("y", "variable", "estimate"), Entity("x", "input", "stream")),
        relations=(Relation("y", "x", "depends_on"), Relation("x", "y", "part_of")),
        assumptions=(Assumption("a", load_bearing=True),),
        goal=Goal("solve"),
        frame="algebra",
    )
    op = get("type_shifting")
    new = next(
        r.representation
        for r in (op.apply(rep, 3.7, np.random.default_rng(s), res) for s in range(20))
        if r.representation.entity("y").type == "output"
    )
    assert new.entity("x").type == "input"
    assert set(new.relations) == {
        Relation("y", "x", "derived_from"),
        Relation("x", "y", "part_of"),
    }


def test_foundational_negation_targets_deeper_axioms_as_rho_grows(res, euclid):
    spec = res.frame(euclid.frame)
    ranked = spec.ranked_axioms()
    depths = []
    for rho in RHOS:
        result = get("foundational_negation").apply(euclid, rho, np.random.default_rng(1), res)
        name = ranked[rank_index(rho, len(ranked), res)].name
        assert name in result.detail
        depths.append(spec.depth(name))
    assert depths == sorted(depths)
    assert depths[0] < depths[-1]


def test_foundational_negation_negates_the_matching_assumption(res, euclid):
    ranked = res.frame(euclid.frame).ranked_axioms()
    index = next(i for i, a in enumerate(ranked) if a.name == "triangle-inequality")
    rho = res.rho_max * (index + 0.5) / len(ranked)
    result = get("foundational_negation").apply(euclid, rho, np.random.default_rng(1), res)
    new = result.representation
    assert "triangle-inequality" in result.detail
    assert len(new.assumptions) == len(euclid.assumptions)
    hit = next(a for a in new.assumptions if "triangle inequality" in a.text)
    assert hit.negated and hit.load_bearing
    assert new.frame == euclid.frame


def test_foundational_negation_moves_the_frame_with_the_deepest_axiom(res, euclid):
    op = get("foundational_negation")
    ranked = res.frame(euclid.frame).ranked_axioms()
    deepest = 8.0
    assert ranked[rank_index(deepest, len(ranked), res)] is ranked[-1]
    moved = op.apply(euclid, deepest, np.random.default_rng(1), res).representation
    assert moved.frame != euclid.frame
    assert moved.frame == res.frame_ranking(euclid.frame)[0]
    assert len(moved.assumptions) == len(euclid.assumptions) + 1
    assert moved.assumptions[-1].negated and moved.assumptions[-1].load_bearing


def test_reification_replaces_one_relation_with_the_paper_pattern(res, euclid):
    result = get("reification").apply(euclid, 1.0, np.random.default_rng(6), res)
    new = result.representation
    added = [e for e in new.entities if e.id not in set(euclid.entity_ids)]
    assert len(added) == 1
    predicate = added[0]
    assert predicate.type == "parameter"
    assert predicate.sort in RELATION_TYPES

    gone = set(euclid.relations) - set(new.relations)
    assert len(gone) == 1
    original = gone.pop()
    assert predicate.sort == original.rtype
    fresh = set(new.relations) - set(euclid.relations)
    assert fresh == {
        Relation(original.src, predicate.id, "has"),
        Relation(original.dst, predicate.id, "has"),
        Relation(predicate.id, original.src, "relates", aux=original.dst),
    }
    assert len(new.relations) == len(euclid.relations) + 2
    ternary = next(r for r in fresh if r.rtype == "relates")
    assert ternary.arity == 3
    assert ternary.endpoints == (predicate.id, original.src, original.dst)


def test_reification_noops_without_relations(res):
    bare = Representation(
        entities=(Entity("x", "variable"),),
        assumptions=(Assumption("a", load_bearing=True),),
        goal=Goal("solve"),
        frame="algebra",
    )
    assert not get("reification").apply(bare, 4.0, np.random.default_rng(0), res).changed


def test_structural_transplant_grows_with_radicality_and_stays_connected(
    res, euclid, streaming
):
    op = get("structural_transplant")
    sizes = []
    for rho in RHOS:
        new = op.apply(euclid, rho, np.random.default_rng(9), res, other=streaming).representation
        grafted = [e for e in new.entities if e.id.startswith("t_")]
        sizes.append(len(grafted))
        assert 1 <= len(grafted) <= len(streaming.entities)
        assert {e.id for e in euclid.entities} <= {e.id for e in new.entities}
        reached, frontier = set(euclid.entity_ids), list(euclid.entity_ids)
        while frontier:
            for nb in new.neighbours(frontier.pop()):
                if nb not in reached:
                    reached.add(nb)
                    frontier.append(nb)
        assert {e.id for e in grafted} <= reached
    assert sizes == sorted(sizes)
    assert sizes[0] == 1 and sizes[-1] == len(streaming.entities)


def test_categorical_import_reaches_further_frames_as_rho_grows(res, euclid, streaming):
    row = res.discipline_similarity[euclid.frame]
    sims = []
    for rho in RHOS:
        result = get("categorical_import").apply(
            euclid, rho, np.random.default_rng(0), res, other=streaming
        )
        assert result.changed
        sims.append(row[result.representation.frame])
    assert sims == sorted(sims, reverse=True)
    assert sims[0] > sims[-1]


def test_categorical_import_drops_unmatched_entities_and_leaves_no_dangling(
    res, corpus
):
    op = get("categorical_import")
    dropped_total = 0
    for i, rep in enumerate(corpus[:60]):
        for rho in (0.0, 2.41, 7.9):
            result = op.apply(rep, rho, np.random.default_rng(i), res, other=corpus[0])
            if not result.changed:
                continue
            new = result.representation
            ids = {e.id for e in new.entities}
            assert all(r.src in ids and r.dst in ids for r in new.relations)
            target_sorts = set(res.frame(new.frame).sorts)
            survivors = [e for e in new.entities if e.id in set(rep.entity_ids)]
            assert all(e.sort in target_sorts for e in survivors)
            assert len(survivors) <= len(rep.entities)
            dropped_total += len(rep.entities) - len(survivors)
    assert dropped_total > 0


def test_categorical_import_maps_sorts_through_the_supertype_lattice(res):
    rep = Representation(
        entities=(
            Entity("m", "parameter", "memory_bound"),
            Entity("q", "variable", "quixotic_sort"),
        ),
        assumptions=(Assumption("a", load_bearing=True),),
        goal=Goal("solve"),
        frame="streaming-algorithms",
    )
    ranking = res.frame_ranking(rep.frame)
    rho = next(
        r for r in np.arange(0.0, 8.0, 0.05)
        if ranking[rank_index(float(r), len(ranking), res)] == "algorithm-design"
    )
    new = get("categorical_import").apply(
        rep, float(rho), np.random.default_rng(0), res, other=rep
    ).representation
    assert new.frame == "algorithm-design"
    survivors = {e.id: e.sort for e in new.entities if e.id in {"m", "q"}}
    assert "m" in survivors
    assert res.supertype(survivors["m"]) == res.supertype("memory_bound")
    assert "q" not in survivors


def test_role_swap_preserves_topology_and_moves_meaning(res):
    left = Representation(
        entities=(
            Entity("p", "variable", "side_length", "a side"),
            Entity("q", "output", "area", "an area"),
        ),
        relations=(Relation("p", "q", "depends_on"),),
        assumptions=(Assumption("a", load_bearing=True),),
        goal=Goal("solve"),
        frame="euclidean-geometry",
    )
    right = Representation(
        entities=(
            Entity("u", "variable", "entropy", "an entropy"),
            Entity("v", "output", "temperature", "a temperature"),
        ),
        relations=(Relation("u", "v", "depends_on"),),
        assumptions=(Assumption("b", load_bearing=True),),
        goal=Goal("maximise"),
        frame="thermodynamics",
    )
    new = get("role_swap").apply(left, 8.0, np.random.default_rng(0), res, other=right).representation
    assert new.entity_ids == left.entity_ids
    assert new.relations == left.relations
    assert [e.type for e in new.entities] == [e.type for e in left.entities]
    assert new.entity("p").sort == "entropy"
    assert new.entity("q").sort == "temperature"
    assert new.entity("q").label == "a temperature"


def test_role_swap_takes_more_pairs_at_higher_radicality(res):
    left = Representation(
        entities=tuple(Entity(f"l{i}", "variable", f"left_{i}") for i in range(4)),
        assumptions=(Assumption("a", load_bearing=True),),
        goal=Goal("solve"),
        frame="algebra",
    )
    right = Representation(
        entities=tuple(Entity(f"r{i}", "variable", f"right_{i}") for i in range(4)),
        assumptions=(Assumption("b", load_bearing=True),),
        goal=Goal("solve"),
        frame="algebra",
    )
    op = get("role_swap")
    counts = []
    for rho in RHOS:
        new = op.apply(left, rho, np.random.default_rng(0), res, other=right).representation
        counts.append(sum(1 for e in new.entities if e.sort.startswith("right_")))
    assert counts == sorted(counts)
    assert counts[0] == 1 and counts[-1] == 4


def test_role_swap_noops_without_an_equivalent_pair(res, euclid):
    lonely = Representation(
        entities=(Entity("z", "coordinate", "angle"),),
        relations=(),
        assumptions=(Assumption("a", load_bearing=True),),
        goal=Goal("solve"),
        frame="algebra",
    )
    assert not get("role_swap").apply(
        euclid, 3.0, np.random.default_rng(0), res, other=lonely
    ).changed


def test_goal_pareto_inversion_switches_on_the_midpoint(res, euclid, streaming):
    op = get("goal_pareto_inversion")
    low = op.apply(euclid, 1.0, np.random.default_rng(0), res, other=streaming)
    high = op.apply(euclid, 7.0, np.random.default_rng(0), res, other=streaming)
    assert unit_rho(1.0, res) <= 0.5 < unit_rho(7.0, res)
    assert low.representation.goal == Goal(
        streaming.goal.objective, euclid.goal.constraint
    )
    assert high.representation.goal == streaming.goal
    assert "objective only" in low.detail
    assert "constraint" in high.detail
    for result in (low, high):
        assert result.representation.entities == euclid.entities
        assert result.representation.relations == euclid.relations


def test_goal_pareto_inversion_noops_when_objectives_agree(res, euclid):
    twin = Representation(
        entities=euclid.entities,
        assumptions=euclid.assumptions,
        goal=Goal(euclid.goal.objective, "a different constraint"),
        frame="algebra",
    )
    assert not get("goal_pareto_inversion").apply(
        euclid, 5.0, np.random.default_rng(0), res, other=twin
    ).changed


def test_generated_corpus_is_itself_well_formed(corpus):
    assert len(corpus) == 200
    for rep in corpus:
        ok, why = well_formed(rep)
        assert ok, why
    assert any(len(r.entities) == 1 for r in corpus)
    assert any(not r.relations for r in corpus)
    assert len({r.frame for r in corpus}) > 5


def test_every_operator_over_the_corpus_is_a_noop_or_well_formed(res, corpus):
    ops = catalog()
    failures: list[str] = []
    noops = changed = 0
    for i, rep in enumerate(corpus):
        other = corpus[(i + 1) % len(corpus)]
        for op in ops:
            for rho in RHOS:
                try:
                    result = op.apply(
                        rep, rho, np.random.default_rng(1000 + i), res, other=other
                    )
                except Exception as exc:
                    failures.append(f"{op.name} raised {exc!r} at rho={rho} on rep {i}")
                    continue
                if not result.changed:
                    noops += 1
                    assert result.representation is None
                    assert result.detail
                    continue
                changed += 1
                if op.kind == "token":
                    assert result.representation is None
                    assert result.decoding is not None
                    continue
                ok, why = well_formed(result.representation)
                if not ok:
                    failures.append(f"{op.name} at rho={rho} on rep {i}: {why}")
    assert not failures, failures[:10]
    total = noops + changed
    assert total == len(corpus) * len(ops) * len(RHOS)
    assert 0.02 < noops / total < 0.25


def test_extreme_radicality_is_accepted_by_every_operator(res, corpus):
    for rho in (0.0, 1e6):
        for op in catalog():
            for rep, other in ((corpus[0], corpus[1]), (corpus[7], corpus[3])):
                result = op.apply(rep, rho, np.random.default_rng(0), res, other=other)
                if result.changed and result.representation is not None:
                    assert well_formed(result.representation)[0]


def test_history_records_the_operator_and_its_parents(res, euclid, streaming):
    for op in catalog():
        result = op.apply(euclid, 2.5, np.random.default_rng(0), res, other=streaming)
        if result.representation is None:
            continue
        record = result.representation.history[-1]
        assert record.operator == op.name
        assert record.radicality == pytest.approx(2.5)
        assert record.detail
        assert record.parents[0] == euclid.fingerprint()
        assert len(record.parents) == op.arity


def _canonical(rep: Representation) -> Representation:
    ents, rels = canonical_parts(rep.entities, rep.relations)
    return replace(rep, entities=ents, relations=rels)


def _leaves_r_alone(rep: Representation, result: EditResult) -> bool:
    """Whether an application left R's fingerprint where it found it."""
    if not result.changed or result.representation is None:
        return True
    return result.representation.fingerprint() == _canonical(rep).fingerprint()


def test_categorical_import_edits_almost_every_representation(res, corpus):
    """mu runs over the vocabularies that differ between frames, so it bites."""
    op = get("categorical_import")
    unchanged = 0
    for i, rep in enumerate(corpus):
        other = corpus[(i + 1) % len(corpus)]
        for rho in RHOS:
            result = op.apply(rep, rho, np.random.default_rng(1000 + i), res, other=other)
            unchanged += _leaves_r_alone(rep, result)
    total = len(corpus) * len(RHOS)
    assert unchanged / total < 0.05, f"{unchanged} of {total} left R alone"


def test_categorical_import_moves_the_frame_and_the_sorts(res, euclid, streaming):
    result = get("categorical_import").apply(
        euclid, 6.0, np.random.default_rng(0), res, other=streaming
    )
    new = result.representation
    assert result.changed
    assert new.frame != euclid.frame
    assert {e.sort for e in new.entities} != {e.sort for e in euclid.entities}
    declared = set(res.frame(new.frame).sorts)
    assert {e.sort for e in new.entities} <= declared
    assert well_formed(new)[0]


def test_unmatched_sorts_are_dropped_with_their_entities_and_relations(
    euclid, streaming
):
    """The Appendix's other two clauses, on the input that reaches them."""
    res = load_resources(tau_mu=1.5)
    result = get("categorical_import").apply(
        euclid, 4.0, np.random.default_rng(0), res, other=streaming
    )
    new = result.representation

    assert result.changed
    assert all(e.id.startswith("imported_") for e in new.entities)
    assert {e.sort for e in new.entities} == set(res.frame(new.frame).sorts)
    assert new.relations == ()
    assert well_formed(new)[0]


def test_the_import_threshold_is_the_papers_tau_mu(res):
    assert res.tau_mu == pytest.approx(0.6)


def _rebuilt_identically(rep: Representation) -> Representation:
    """R with a fresh edit record and its parts handed over out of order."""
    record = EditRecord(
        operator="none", radicality=1.0, detail="none", parents=(rep.fingerprint(),)
    )
    ents, rels = canonical_parts(reversed(rep.entities), reversed(rep.relations))
    return rep.with_edit(record, entities=ents, relations=rels)


def test_settled_calls_a_structurally_identical_rebuild_a_noop(res, euclid):
    result = settled(euclid, _rebuilt_identically(euclid), "did nothing", res)
    assert not result.changed
    assert result.representation is None
    assert result.detail == "unchanged"


def test_nothing_to_do_reports_why(res, euclid):
    """The no-op that actually occurs: an operator declining before it edits."""
    twin = replace(euclid, goal=Goal(euclid.goal.objective, "another constraint"))
    result = get("goal_pareto_inversion").apply(
        euclid, 5.0, np.random.default_rng(0), res, other=twin
    )
    assert not result.changed
    assert result.representation is None
    assert "objectives already agree" in result.detail


def test_a_noop_is_R_itself_and_is_well_formed(res, corpus):
    """R_new = R for a no-op, which Algorithm 1 generates from like any other."""
    noops = edits = 0
    for i, rep in enumerate(corpus[:40]):
        other = corpus[(i + 1) % len(corpus)]
        for op in catalog():
            for rho in (0.0, 2.41, 7.9):
                result = op.apply(rep, rho, np.random.default_rng(i), res, other=other)
                if result.changed:
                    edits += 1
                else:
                    noops += 1
                    assert well_formed(result.representation or rep)[0]
    assert edits > 0
    assert noops > 0


def _typed_graph(
    edges: list[tuple[int, int]], n: int, *, hub: bool = False
) -> Representation:
    """n identically typed entities wired by `edges`, plus an optional hub."""
    entities = [Entity(f"e{i}", "variable", "point", "a point") for i in range(n)]
    relations = [Relation(f"e{a}", f"e{b}", "relates") for a, b in edges]
    if hub:
        entities.append(Entity("h", "parameter", "hub", "the hub"))
        relations.extend(Relation("h", f"e{i}", "relates") for i in range(n))
    return Representation(
        entities=tuple(sorted(entities, key=lambda e: e.id)),
        relations=tuple(sorted(relations, key=lambda r: (r.src, r.dst, r.rtype))),
        assumptions=(Assumption("the graph is what it is", load_bearing=True),),
        goal=Goal("decide the isomorphism"),
        frame="algebra",
    )


def _cycle(nodes: list[int]) -> list[tuple[int, int]]:
    return [(nodes[k], nodes[(k + 1) % len(nodes)]) for k in range(len(nodes))]


def test_colour_refinement_cannot_tell_an_eight_cycle_from_two_four_cycles():
    """Why refinement prunes the search rather than deciding it."""
    eight = _typed_graph(_cycle(list(range(8))), 8)
    two_fours = _typed_graph(_cycle(list(range(4))) + _cycle(list(range(4, 8))), 8)

    assert _colour_multiset(_colours(eight)) == _colour_multiset(_colours(two_fours))
    verdict = compare(eight, two_fours)
    assert not verdict.isomorphic and not verdict.undecided
    assert verdict.reason == "different number of components"
    assert not structurally_isomorphic(eight, two_fours)


def test_a_hub_over_one_cycle_is_not_a_hub_over_two():
    """The same failure of refinement on a connected shape."""
    wheel = _typed_graph(_cycle(list(range(8))), 8, hub=True)
    split = _typed_graph(
        _cycle(list(range(4))) + _cycle(list(range(4, 8))), 8, hub=True
    )

    assert _colour_multiset(_colours(wheel)) == _colour_multiset(_colours(split))
    verdict = compare(wheel, split)
    assert not verdict.isomorphic and not verdict.undecided


def test_a_relabelled_copy_is_recognised():
    wheel = _typed_graph(_cycle(list(range(6))), 6, hub=True)
    relabelled = _typed_graph(_cycle([0, 2, 4, 1, 3, 5]), 6, hub=True)

    assert wheel.fingerprint() != relabelled.fingerprint()
    assert compare(wheel, relabelled).isomorphic


def test_a_symmetric_shape_is_decided_rather_than_declined():
    """Nine interchangeable leaves: 9! orderings, settled by edge pruning."""
    nine = _typed_graph([], 9, hub=True)
    same = _typed_graph([], 9, hub=True)

    verdict = compare(nine, same)
    assert verdict.isomorphic and not verdict.undecided


def _cycle_covers(
    rng: np.random.Generator, n: int = 6, count: int = 60
) -> list[Representation]:
    """Random cycle covers of n same-typed entities: one n-cycle, or two."""
    covers = []
    while len(covers) < count:
        order = [int(x) for x in rng.permutation(n)]
        parts = [order] if int(rng.integers(2)) else [order[: n // 2], order[n // 2 :]]
        covers.append(_typed_graph([e for part in parts for e in _cycle(part)], n))
    return covers


def test_nothing_is_left_undecided_on_the_shapes_refinement_cannot_separate():
    """Sixty random cycle covers of six identically typed entities, paired."""
    sample = _cycle_covers(np.random.default_rng(20260829))
    pairs = list(pairwise(sample))
    disagreements = 0
    for a, b in pairs:
        verdict = compare(a, b)
        assert not verdict.undecided
        refinement = _colour_multiset(_colours(a)) == _colour_multiset(_colours(b))
        if refinement != verdict.isomorphic:
            assert refinement and not verdict.isomorphic
            disagreements += 1

    assert len(pairs) == 59
    assert disagreements >= 20, f"{disagreements} of {len(pairs)}"


def test_the_operator_composition_probe_is_decided_everywhere(res, corpus):
    """The sample the commutativity table is actually computed on."""
    structural = [op for op in catalog() if op.kind != "token"]
    seeds = {op.name: 100 + i for i, op in enumerate(structural)}

    def compose(ops, rep, other, rho):
        current = rep
        for op in ops:
            edit = op.apply(
                current, rho, np.random.default_rng(seeds[op.name]), res, other=other
            )
            if not edit.changed or edit.representation is None:
                return None
            if not well_formed(edit.representation)[0]:
                return None
            current = edit.representation
        return current

    pairs = isomorphic = undecided = 0
    for i, rep in enumerate(corpus[:16]):
        other = corpus[(i + 1) % len(corpus)]
        rho = RHOS[i % len(RHOS)]
        for first, second in permutations(structural, 2):
            a = compose((first, second), rep, other, rho)
            b = compose((second, first), rep, other, rho)
            if a is None or b is None:
                continue
            pairs += 1
            verdict = compare(a, b)
            isomorphic += verdict.isomorphic
            undecided += verdict.undecided

    report = f"{pairs} pairs, {isomorphic} isomorphic, {undecided} undecided"
    assert pairs > 500, report
    assert undecided == 0, report
    assert 0 < isomorphic < pairs, report


def test_structural_transplant_carries_a_ternary_relation_whole(res):
    """A reified donor's `relates(e_p, e_i, e_j)` must arrive with all three."""
    base = Representation(
        entities=(
            Entity("a", "variable", "x"),
            Entity("b", "output", "y"),
            Entity("c", "input", "z"),
        ),
        relations=(Relation("a", "b", "constrains"), Relation("b", "c", "constrains")),
        assumptions=(Assumption("something", load_bearing=True),),
        goal=Goal("solve"),
        frame="algebra",
    )
    reify = get("reification")
    donor = reify.apply(base, 1.0, np.random.default_rng(0), res).representation
    donor = reify.apply(donor, 1.0, np.random.default_rng(1), res).representation
    assert any(r.aux for r in donor.relations)

    grafted = get("structural_transplant").apply(
        base, 8.0, np.random.default_rng(0), res, other=donor
    )
    new = grafted.representation
    assert grafted.changed
    ternary = [r for r in new.relations if r.arity == 3]
    assert ternary, "the graft kept no ternary relation"
    known = set(new.entity_ids)
    assert all(all(x in known for x in r.endpoints) for r in ternary)
    assert well_formed(new)[0]


def test_well_formed_catches_a_dangling_third_argument():
    dangling = Representation(
        entities=(Entity("a", "variable", "x"), Entity("b", "output", "y")),
        relations=(Relation("a", "b", "relates", aux="ghost"),),
        assumptions=(Assumption("something", load_bearing=True),),
        goal=Goal("solve"),
        frame="algebra",
    )
    ok, reason = well_formed(dangling)
    assert not ok
    assert "ghost" in reason
