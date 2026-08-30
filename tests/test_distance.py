"""Feature map, log-domain Sinkhorn solver and d_struct."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from scipy.spatial.distance import cdist

from trope.backends.base import HashEncoder
from trope.config import Config
from trope.distance import (
    DistanceParams,
    StructuralDistance,
    as_params,
    cloud_distance,
    d_struct,
)
from trope.features import (
    FEATURE_VERSION,
    ISOLATED,
    FeatureCloud,
    representation_features,
    type_label,
    type_of,
)
from trope.sinkhorn import (
    sinkhorn_cost,
    sinkhorn_divergence,
    wasserstein2,
    wasserstein2_exact_1d,
)
from trope.types import (
    Assumption,
    Entity,
    Goal,
    Relation,
    Representation,
    prune_dangling,
)

EXACT_EPS = 0.002
EXACT_ITERS = 6000

CONVERGED = {"stages": 8, "early_exit": True}


def cloud(seed: int, n: int, dim: int = 1, shift: float = 0.0) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=(n, dim)) + shift


@pytest.fixture(scope="module")
def encoder() -> HashEncoder:
    return HashEncoder(dim=8)


@pytest.fixture(scope="module")
def rep() -> Representation:
    entities = tuple(
        Entity(f"e{i}", t, s)
        for i, (t, s) in enumerate(
            [
                ("variable", "side_length"),
                ("parameter", "area"),
                ("output", "total"),
                ("input", "radius"),
                ("constant", "pi"),
                ("coordinate", "axis"),
            ]
        )
    )
    relations = (
        Relation("e0", "e1", "depends_on"),
        Relation("e1", "e2", "maps_to"),
        Relation("e3", "e1", "constrains"),
        Relation("e4", "e0", "bounds"),
        Relation("e5", "e3", "indexes"),
    )
    return Representation(
        entities=entities,
        relations=relations,
        assumptions=(
            Assumption("the shape is convex", load_bearing=True),
            Assumption("measurements are exact"),
        ),
        goal=Goal("compute the total"),
        frame="geometry",
    )


@pytest.fixture(scope="module")
def repeated_labels() -> Representation:
    """Entities that Eq. (4) cannot tell apart, which the parser produces often."""
    return Representation(
        entities=(
            Entity("e0", "variable", "x"),
            Entity("e1", "variable", "x"),
            Entity("e2", "input", "number"),
            Entity("e3", "input", "number"),
            Entity("e4", "output", "total"),
        ),
        relations=(
            Relation("e0", "e2", "depends_on"),
            Relation("e1", "e3", "depends_on"),
            Relation("e2", "e4", "maps_to"),
        ),
        assumptions=(Assumption("values are positive", load_bearing=True),),
        goal=Goal("find the total"),
        frame="algebra",
    )


def truncated(rep: Representation, keep: int = 4) -> Representation:
    """`rep` with its later entities dropped and dangling relations pruned."""
    kept = rep.entities[:keep]
    return replace(
        rep,
        entities=kept,
        relations=prune_dangling(kept, rep.relations),
        frame="physics",
    )


def test_exact_1d_known_answer() -> None:
    assert wasserstein2_exact_1d([0.0, 1.0], [2.0, 5.0]) == pytest.approx(
        np.sqrt((4.0 + 16.0) / 2.0)
    )
    assert wasserstein2_exact_1d([0.0], [1.0, 2.0, 3.0]) == pytest.approx(
        np.sqrt((1.0 + 4.0 + 9.0) / 3.0)
    )
    assert wasserstein2_exact_1d([3.0, 1.0], [1.0, 3.0]) == 0.0


def test_exact_1d_is_translation_covariant() -> None:
    x = cloud(0, 9).ravel()
    for c in (-2.5, 0.0, 0.75):
        assert wasserstein2_exact_1d(x, x + c) == pytest.approx(abs(c))


@pytest.mark.parametrize(("n", "m"), [(8, 8), (7, 11), (1, 5)])
def test_sinkhorn_matches_exact_1d(n: int, m: int) -> None:
    X, Y = cloud(1, n), cloud(2, m, shift=0.7)
    got = wasserstein2(X, Y, EXACT_EPS, EXACT_ITERS)
    assert got == pytest.approx(wasserstein2_exact_1d(X, Y), abs=1e-3)


def test_distinct_clouds_are_strictly_apart() -> None:
    X, Y = cloud(6, 8, dim=3), cloud(7, 8, dim=3, shift=1.5)
    assert wasserstein2(X, Y, 0.01, 200) == pytest.approx(1.96, abs=0.01)


def test_translation_covariance_of_the_solver() -> None:
    X = np.array([[0.0], [1.0], [2.5], [4.0]])
    for c in (0.3, -0.3):
        assert wasserstein2(X, X + c, 0.005, 2000) == pytest.approx(abs(c), abs=1e-3)


def test_no_nan_when_costs_span_nine_orders_of_magnitude() -> None:
    X = np.array([[0.0], [1e-3], [31.6]])
    Y = np.array([[5e-4], [2.0], [31.6]])
    C = cdist(X, Y, "sqeuclidean")
    assert C.min() < 1e-5 and C.max() > 1e2
    result = sinkhorn_cost(np.full(3, 1 / 3), np.full(3, 1 / 3), C, 0.01, 50)
    assert np.isfinite(result.cost)
    assert np.isfinite(wasserstein2(X, Y, 0.01, 50))


def test_the_solver_stays_in_the_log_domain() -> None:
    X, Y = np.array([[0.0], [1.0]]), np.array([[10.0], [12.0]])
    C = cdist(X, Y, "sqeuclidean")
    assert C.min() > 7.5
    K = np.exp(-C / 0.01)
    assert K.max() == 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        scaling = np.full(2, 0.5) / (K @ np.full(2, 0.5))
    assert not np.isfinite(scaling).all()
    assert np.isfinite(wasserstein2(X, Y, 0.01, 50))


def test_marginal_error_and_convergence_flag() -> None:
    X, Y = cloud(8, 6, dim=2), cloud(9, 10, dim=2, shift=0.4)
    C = cdist(X, Y, "sqeuclidean")
    a, b = np.full(6, 1 / 6), np.full(10, 1 / 10)
    one = sinkhorn_cost(a, b, C, 0.1, 1)
    many = sinkhorn_cost(a, b, C, 0.1, 2000)
    assert not one.converged
    assert one.marginal_error == pytest.approx(0.232, abs=1e-3)
    assert many.converged
    assert many.marginal_error < 1e-12


def test_solver_rejects_degenerate_input() -> None:
    a, b = np.full(2, 0.5), np.full(3, 1 / 3)
    C = np.zeros((2, 3))
    with pytest.raises(ValueError):
        sinkhorn_cost(a, b, np.zeros((3, 2)), 0.01, 10)
    with pytest.raises(ValueError):
        sinkhorn_cost(a, b, C, 0.0, 10)
    with pytest.raises(ValueError):
        sinkhorn_cost(np.array([1.0, 0.0]), b, C, 0.01, 10)
    with pytest.raises(ValueError):
        sinkhorn_cost(a, b, C, 0.01, 0)
    with pytest.raises(ValueError):
        wasserstein2(np.zeros((0, 3)), np.zeros((2, 3)), 0.01, 10)
    with pytest.raises(ValueError):
        wasserstein2(cloud(1, 3), cloud(2, 4), 0.01, 10, a=np.ones(2))


def test_entropic_self_cost_is_a_positive_floor() -> None:
    X = np.array([[0.0], [0.02], [0.04]])
    a = np.full(3, 1 / 3)
    self_cost = sinkhorn_cost(a, a, cdist(X, X, "sqeuclidean"), 0.01, 50).cost
    assert self_cost == pytest.approx(5.05e-4, rel=1e-2)
    assert wasserstein2(X, X, 0.01, 50) == pytest.approx(0.02247, abs=1e-5)
    assert sinkhorn_divergence(X, X, 0.01, 50) == 0.0


def test_self_distance_of_a_real_cloud_is_small_but_not_zero(
    rep: Representation, repeated_labels: Representation, encoder: HashEncoder
) -> None:
    """The same floor on real feature clouds, and why `cloud_distance` refuses to pay it."""
    params = DistanceParams(encoder_dim=encoder.dim)
    distinct = representation_features(rep, encoder).atoms
    shared = representation_features(repeated_labels, encoder).atoms
    assert wasserstein2(distinct, distinct, 0.01, 50) == pytest.approx(4.18e-37, rel=1e-2)
    assert wasserstein2(shared, shared, 0.01, 50) == pytest.approx(2.48e-12, rel=1e-2)
    assert d_struct(rep, rep, params, encoder=encoder) == 0.0
    assert d_struct(repeated_labels, repeated_labels, params, encoder=encoder) == 0.0
    between = d_struct(rep, repeated_labels, params, encoder=encoder)
    assert between == pytest.approx(1.5245, abs=1e-3)


def test_fifty_iterations_fall_short_of_the_converged_solve(
    rep: Representation, encoder: HashEncoder
) -> None:
    """What Eq. (4)'s fixed budget buys on a real pair of clouds."""
    other = truncated(rep)
    X = representation_features(rep, encoder).atoms
    Y = representation_features(other, encoder).atoms
    a, b = np.full(len(X), 1.0 / len(X)), np.full(len(Y), 1.0 / len(Y))
    C = cdist(X, Y, "sqeuclidean")

    paper = sinkhorn_cost(a, b, C, 0.01, 50)
    converged = sinkhorn_cost(a, b, C, 0.01, 50, **CONVERGED)
    assert not paper.converged
    assert paper.marginal_error == pytest.approx(0.0833, abs=1e-3)
    assert converged.converged and converged.marginal_error <= 1e-6
    assert paper.marginal_error > 1e4 * converged.marginal_error
    assert (converged.cost - paper.cost) / converged.cost == pytest.approx(
        0.264, abs=0.01
    )

    fifty = wasserstein2(X, Y, 0.01, 50)
    reference = wasserstein2(X, Y, 0.01, 50, **CONVERGED)
    assert fifty == pytest.approx(0.8387, abs=1e-3)
    assert reference == pytest.approx(0.9777, abs=1e-3)
    assert reference - fifty == pytest.approx(0.1390, abs=1e-3)


def test_the_fixed_iteration_solve_depends_on_argument_order(
    rep: Representation, encoder: HashEncoder
) -> None:
    other = truncated(rep)
    X = representation_features(rep, encoder).atoms
    Y = representation_features(other, encoder).atoms

    forward = wasserstein2(X, Y, 0.01, 50)
    backward = wasserstein2(Y, X, 0.01, 50)
    assert forward != backward
    assert forward == pytest.approx(0.8387, abs=1e-3)
    assert backward == pytest.approx(0.9310, abs=1e-3)
    assert abs(forward - backward) == pytest.approx(0.0923, abs=1e-3)
    assert abs(forward - backward) / max(forward, backward) > 0.09

    ref_forward = wasserstein2(X, Y, 0.01, 50, **CONVERGED)
    ref_backward = wasserstein2(Y, X, 0.01, 50, **CONVERGED)
    assert abs(ref_forward - ref_backward) < 1e-6


def test_feature_version_is_pinned() -> None:
    assert FEATURE_VERSION == 3
    assert DistanceParams().feature_version == FEATURE_VERSION
    assert StructuralDistance().feature_version == FEATURE_VERSION


def test_one_atom_per_entity_laid_out_as_eq_four(
    rep: Representation, encoder: HashEncoder
) -> None:
    fc = representation_features(rep, encoder, degree_scale=0.25)
    dim = encoder.dim
    assert fc.version == FEATURE_VERSION
    assert fc.n_atoms == len(rep.entities) == 6
    assert fc.atoms.shape == (6, 2 * dim + 1)
    roles = encoder.encode([type_of(e) for e in rep.entities])
    incident = encoder.encode([type_label(rep, e.id) for e in rep.entities])
    assert fc.atoms[:, :dim] == pytest.approx(roles)
    assert fc.atoms[:, dim] == pytest.approx(0.25 * np.array([2, 3, 1, 2, 1, 1.0]))
    assert fc.atoms[:, dim + 1 :] == pytest.approx(incident)


def test_the_typing_embedded_is_the_role_and_the_sort_together(
    encoder: HashEncoder,
) -> None:
    by_sort = Representation(
        entities=(
            Entity("a", "parameter", "side_length"),
            Entity("b", "parameter", "area"),
        ),
        relations=(),
        assumptions=(Assumption("both are positive", load_bearing=True),),
        goal=Goal("relate them"),
    )
    assert [type_of(e) for e in by_sort.entities] == [
        "parameter side_length",
        "parameter area",
    ]
    atoms = representation_features(by_sort, encoder).atoms
    assert not np.array_equal(atoms[0], atoms[1])
    assert not np.array_equal(atoms[0, : encoder.dim], atoms[1, : encoder.dim])
    role_only = np.asarray(encoder.encode([e.type for e in by_sort.entities]))
    assert np.array_equal(role_only[0], role_only[1])


@pytest.mark.parametrize("degree_scale", [0.0, 0.25, 2.0])
def test_the_degree_column_is_the_scaled_degree(
    rep: Representation, encoder: HashEncoder, degree_scale: float
) -> None:
    fc = representation_features(rep, encoder, degree_scale=degree_scale)
    degrees = np.array([rep.degree(e.id) for e in rep.entities], dtype=float)
    assert fc.atoms[:, encoder.dim] == pytest.approx(degree_scale * degrees)


def test_the_incident_column_embeds_the_sorted_relation_type_set(
    rep: Representation,
) -> None:
    assert type_label(rep, "e1") == "constrains depends_on maps_to"
    assert type_label(rep, "e2") == "maps_to"
    shuffled = replace(rep, relations=tuple(reversed(rep.relations)))
    assert [type_label(shuffled, e.id) for e in shuffled.entities] == [
        type_label(rep, e.id) for e in rep.entities
    ]


def test_an_entity_no_relation_touches_gets_the_isolated_label(
    encoder: HashEncoder,
) -> None:
    r = Representation(
        entities=(
            Entity("a", "variable", "x"),
            Entity("b", "output", "y"),
            Entity("c", "constant", "pi"),
        ),
        relations=(Relation("a", "b", "maps_to"),),
        assumptions=(Assumption("x exists", load_bearing=True),),
        goal=Goal("find y"),
    )
    assert ISOLATED == "isolated"
    assert type_label(r, "c") == ISOLATED
    dim = encoder.dim
    atoms = representation_features(r, encoder).atoms
    assert atoms[2, dim] == 0.0
    assert atoms[2, dim + 1 :] == pytest.approx(encoder.encode([ISOLATED])[0])
    assert np.any(atoms[2, dim + 1 :] != 0.0)
    assert not np.allclose(atoms[2, dim + 1 :], atoms[0, dim + 1 :])


def test_an_empty_representation_gets_one_zero_atom(encoder: HashEncoder) -> None:
    empty = Representation(goal=Goal("nothing to model"))
    fc = representation_features(empty, encoder)
    assert fc.atoms.shape == (1, 2 * encoder.dim + 1)
    assert np.all(fc.atoms == 0.0)
    assert cloud_distance(fc, fc, DistanceParams(encoder_dim=encoder.dim)) == 0.0


def test_dangling_relations_contribute_no_degree(encoder: HashEncoder) -> None:
    r = Representation(
        entities=(Entity("a", "variable", "x"),),
        relations=(Relation("a", "ghost", "depends_on"),),
        assumptions=(Assumption("x exists", load_bearing=True),),
        goal=Goal("find x"),
    )
    fc = representation_features(r, encoder)
    assert fc.atoms[:, encoder.dim] == pytest.approx([0.0])
    assert fc.atoms[0, encoder.dim + 1 :] == pytest.approx(encoder.encode([ISOLATED])[0])
    bare = representation_features(replace(r, relations=()), encoder)
    assert np.array_equal(fc.atoms, bare.atoms)


def test_row_order_does_not_make_a_cloud_a_different_measure(
    rep: Representation, encoder: HashEncoder
) -> None:
    params = DistanceParams(encoder_dim=encoder.dim)
    atoms = representation_features(rep, encoder).atoms
    permuted = atoms[np.random.default_rng(0).permutation(len(atoms))]
    assert not np.array_equal(atoms, permuted)

    left, right = FeatureCloud(atoms=atoms), FeatureCloud(atoms=permuted)
    assert cloud_distance(left, right, params) == 0.0
    assert wasserstein2(atoms, permuted, 0.01, 50) > 0.0


def test_cloud_distance_refuses_to_mix_feature_map_versions(
    rep: Representation, encoder: HashEncoder
) -> None:
    fc = representation_features(rep, encoder)
    stale = FeatureCloud(atoms=fc.atoms, version=FEATURE_VERSION - 1)
    with pytest.raises(ValueError, match="feature maps disagree"):
        cloud_distance(stale, fc, DistanceParams(encoder_dim=encoder.dim))


def test_the_feature_map_cannot_see_goal_frame_or_assumption_edits(
    rep: Representation, encoder: HashEncoder
) -> None:
    params = DistanceParams(encoder_dim=encoder.dim)
    bare = Representation(
        entities=(Entity("a", "parameter", "side_length"),),
        relations=(),
        assumptions=(Assumption("the triangle inequality holds", True),),
        goal=Goal("prove the inequality"),
        frame="euclidean-geometry",
    )
    for base in (bare, rep):
        assert d_struct(base, base, params, encoder=encoder) == 0.0
        edits = (
            replace(base, goal=Goal("minimise the area")),
            replace(base, frame="topology"),
            replace(base, assumptions=(Assumption("nothing holds", True, True),)),
        )
        for changed in edits:
            assert changed.fingerprint() != base.fingerprint()
            assert d_struct(base, changed, params, encoder=encoder) == 0.0

    grown = replace(bare, entities=(*bare.entities, Entity("b", "output", "y")))
    visible = d_struct(bare, grown, params, encoder=encoder)
    assert visible == pytest.approx(0.4748, abs=1e-3)
    assert visible > 0.4


def test_distance_ignores_the_edit_trail(rep: Representation) -> None:
    from trope.types import EditRecord

    tagged = rep.with_edit(EditRecord(operator="whatever", radicality=3.0))
    assert d_struct(rep, tagged) == d_struct(rep, rep)


def test_d_struct_is_exactly_symmetric(rep: Representation) -> None:
    other = truncated(rep)
    assert d_struct(rep, other) == d_struct(other, rep)

    sd = StructuralDistance()
    assert sd(rep, other) == sd(other, rep)
    fresh = StructuralDistance()
    assert fresh(other, rep) == sd(rep, other)
    assert sd(rep, other) == d_struct(rep, other)
    assert sd(rep, other) == pytest.approx(1.2520, abs=1e-3)


def test_single_type_change_is_smaller_than_a_frame_change_plus_deletions(
    rep: Representation,
) -> None:
    from trope.operators.base import get, load_resources, well_formed

    res = load_resources()
    small = get("type_shifting").apply(rep, 0.3, np.random.default_rng(1), res)
    assert small.changed
    imported = get("categorical_import").apply(
        rep, 1.0, np.random.default_rng(1), res, other=replace(rep, frame="physics")
    )
    assert imported.changed and imported.representation.frame != rep.frame
    kept = imported.representation.entities[:-3]
    big = replace(
        imported.representation,
        entities=kept,
        relations=prune_dangling(kept, imported.representation.relations),
    )
    assert well_formed(small.representation)[0] and well_formed(big)[0]

    sd = StructuralDistance()
    assert 0.0 < sd(rep, small.representation) < sd(rep, big)


def test_cache_returns_the_same_value_it_would_have_computed(
    rep: Representation,
) -> None:
    other = truncated(rep, keep=3)
    sd = StructuralDistance()
    first = sd(rep, other)
    assert sd.cache_info().misses == 1 and sd.cache_info().hits == 0
    assert sd.cache_info().cloud_misses == 2
    assert sd(other, rep) == first
    assert sd.cache_info().hits == 1
    assert first == d_struct(rep, other)
    sd.cache_clear()
    assert sd.cache_info().currsize == 0
    assert sd.cache_info().cloud_misses == 0
    assert sd(rep, other) == first


def test_cache_evicts_and_stays_correct(rep: Representation) -> None:
    variants = [truncated(rep, keep=k) for k in (5, 4, 3, 2)]
    sd = StructuralDistance(maxsize=2)
    values = [sd(rep, v) for v in variants]
    assert len(set(values)) == 4
    assert sd.cache_info().currsize == 2
    assert [sd(rep, v) for v in variants] == values


def test_config_block_is_accepted(rep: Representation) -> None:
    cfg = Config()
    cfg.distance.sinkhorn_iters = 20
    assert as_params(cfg).sinkhorn_iters == 20
    assert as_params(cfg.distance).sinkhorn_iters == 20
    assert as_params(None) == DistanceParams()
    assert as_params(DistanceParams(encoder_dim=8)).encoder_dim == 8
    assert d_struct(rep, rep, cfg) < 1e-40
    assert (DistanceParams().sinkhorn_eps, DistanceParams().sinkhorn_iters) == (0.01, 50)
    assert not hasattr(cfg, "compat")


def test_provenance_records_the_map_and_the_solver() -> None:
    assert StructuralDistance().provenance() == {
        "feature_version": 3,
        "encoder": "HashEncoder",
        "encoder_dim": 64,
        "sinkhorn_eps": 0.01,
        "sinkhorn_iters": 50,
    }
