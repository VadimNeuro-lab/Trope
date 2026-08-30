"""PI controller on gamma, and the divergence probe that drives it."""

from __future__ import annotations

import math

import numpy as np
import pytest

from trope.control.divergence import (
    DivergenceResult,
    estimate_divergence,
    perturb_single_name,
)
from trope.control.pi import PIController
from trope.sinkhorn import wasserstein2_exact_1d
from trope.types import Assumption, Entity, Goal, Relation, Representation


def controller(**kwargs) -> PIController:
    defaults = dict(
        kp=0.50,
        ki=0.10,
        window=8,
        setpoint=0.22,
        gamma_init=0.3,
        gamma_min=0.02,
        gamma_max=3.0,
        lambda_min=0.05,
        lambda_max=0.40,
    )
    defaults.update(kwargs)
    return PIController(**defaults)


@pytest.fixture
def rep() -> Representation:
    return Representation(
        entities=(
            Entity("e0", "variable", "side_length", "the side"),
            Entity("e1", "parameter", "area"),
            Entity("e2", "output", "total"),
        ),
        relations=(Relation("e0", "e1", "depends_on"), Relation("e1", "e2", "maps_to")),
        assumptions=(Assumption("the shape is convex", load_bearing=True),),
        goal=Goal("compute the total"),
        frame="geometry",
    )


def test_sign_convention() -> None:
    """Below the setpoint the edits are too timid, so the scale must rise."""
    low = controller()
    assert low.update(0.10) > 0.3
    high = controller()
    assert high.update(0.35) < 0.3
    flat = controller()
    assert flat.update(0.22) == pytest.approx(0.3)


def test_the_integral_is_a_sliding_window_of_the_last_w_errors() -> None:
    """A running total and Eq. (9)'s sum agree until the oldest error leaves."""
    pi = controller(window=3)
    gammas = [
        pi.update(pi.setpoint - 0.5),
        pi.update(0.22),
        pi.update(0.22),
        pi.update(0.22),
    ]
    assert [step.error for step in pi.history] == pytest.approx([0.5, 0.0, 0.0, 0.0])
    assert [step.integral for step in pi.history] == pytest.approx([0.5, 0.5, 0.5, 0.0])
    assert gammas == pytest.approx([0.6, 0.65, 0.7, 0.7])

    assert gammas[1] - gammas[0] == pytest.approx(0.05)
    assert gammas[2] - gammas[1] == pytest.approx(0.05)
    assert gammas[3] == pytest.approx(gammas[2])
    assert len(pi.errors) == 3 and pi.errors.maxlen == 3


def test_a_sustained_error_pins_gamma_at_a_bound_and_flags_it() -> None:
    up = controller()
    for _ in range(200):
        up.update(-5.0)
    assert up.gamma == pytest.approx(3.0)
    assert all(step.saturated for step in up.history)

    down = controller()
    for _ in range(200):
        down.update(5.0)
    assert down.gamma == pytest.approx(0.02)
    assert down.gamma > 0.0
    assert all(step.saturated for step in down.history)

    ordinary = controller()
    ordinary.update(0.10)
    assert ordinary.gamma == pytest.approx(0.372)
    assert not ordinary.history[0].saturated


def test_gamma_never_leaves_the_actuator_box() -> None:
    pi = controller()
    rng = np.random.default_rng(4)
    drive = np.concatenate([rng.normal(0.22, 0.5, 300), rng.standard_cauchy(100) * 5])
    for value in drive:
        gamma = pi.update(float(value))
        assert pi.gamma_min <= gamma <= pi.gamma_max
    gammas = [step.gamma for step in pi.history]
    assert len(gammas) == 400
    assert min(gammas) == pytest.approx(0.02) and max(gammas) == pytest.approx(3.0)
    assert sum(step.saturated for step in pi.history) == 175


def test_lambda_hat_reaches_the_error_unclipped() -> None:
    """The band is what the controller holds, not a filter on its measurement."""
    pi = controller()
    pi.update(50.0)
    assert pi.history[0].lambda_hat == 50.0
    assert pi.history[0].error == pytest.approx(0.22 - 50.0)
    assert not pi.history[0].in_band
    assert pi.gamma == pytest.approx(0.02) and pi.history[0].saturated


def test_tracks_a_linear_plant() -> None:
    """lambda(gamma) = c gamma has the fixed point gamma* = setpoint / c."""
    c = 0.5
    pi = controller()
    gamma = pi.gamma
    for _ in range(80):
        gamma = pi.update(c * gamma)
    assert gamma == pytest.approx(pi.setpoint / c, abs=1e-3)
    assert pi.band_occupancy().steady == pytest.approx(1.0)
    assert not any(step.saturated for step in pi.history)


def test_band_occupancy_counts_raw_estimates() -> None:
    pi = controller(window=2)
    for value in (0.9, 0.9, 0.9, 0.22, 0.22, 0.22, 0.9, 0.22):
        pi.update(value)
    occ = pi.band_occupancy()
    assert occ.n == 8 and occ.n_steady == 6
    assert occ.overall == pytest.approx(4 / 8)
    assert occ.steady == pytest.approx(4 / 6)
    assert pi.history[0].lambda_hat == 0.9
    assert PIController().band_occupancy() == (0.0, 0.0, 0, 0)


def test_reset_clears_the_window_and_settles_the_scale() -> None:
    pi = controller()
    pi.update(0.10)
    pi.reset(99.0)
    assert pi.gamma == pytest.approx(3.0)
    assert pi.history == [] and not pi.errors


def test_rejects_impossible_settings() -> None:
    with pytest.raises(ValueError):
        controller(gamma_min=0.0)
    with pytest.raises(ValueError):
        controller(gamma_min=1.0, gamma_max=0.5)
    with pytest.raises(ValueError):
        controller(lambda_min=0.5, lambda_max=0.1)
    with pytest.raises(ValueError):
        controller(window=0)


def scaling_probe(rate: float, steps: int = 16, seed: int = 0) -> DivergenceResult:
    """Both branches scaled by exp(rate) per step, so d_t = d_0 exp(rate t)."""
    start = np.array([[0.0], [1.0], [2.0]])
    return estimate_divergence(
        start,
        lambda x, r: x * math.exp(rate),
        lambda x, y: wasserstein2_exact_1d(x.ravel(), y.ravel()),
        np.random.default_rng(seed),
        steps=steps,
        epsilon=0.0,
        perturb_fn=lambda x, r: x + 0.5,
    )


@pytest.mark.parametrize("rate", [0.22, -0.15, 1.0])
def test_recovers_a_known_divergence_rate(rate: float) -> None:
    result = scaling_probe(rate)
    assert result.estimate == pytest.approx(rate, abs=1e-6)
    assert result.degenerate == 0
    assert len(result.ratios) == 16
    assert all(r == pytest.approx(rate, abs=1e-6) for r in result.ratios)


def test_a_static_dynamic_has_zero_divergence() -> None:
    assert scaling_probe(0.0).estimate == pytest.approx(0.0, abs=1e-12)


def test_collapsed_branches_are_reported_not_averaged_in() -> None:
    """Identical branches with eps_div off give log(0/0), which must not be 0."""
    result = estimate_divergence(
        np.zeros((2, 1)),
        lambda x, r: x,
        lambda x, y: 0.0,
        np.random.default_rng(0),
        steps=5,
        epsilon=0.0,
        perturb_fn=lambda x, r: x,
    )
    assert result.degenerate == 5
    assert result.ratios == ()
    assert result.estimate == 0.0


def test_epsilon_div_rescues_a_zero_start() -> None:
    distances = iter([0.0] + [0.1] * 4)
    result = estimate_divergence(
        object(),
        lambda x, r: x,
        lambda x, y: next(distances),
        np.random.default_rng(0),
        steps=4,
        epsilon=1e-6,
        perturb_fn=lambda x, r: x,
    )
    assert result.degenerate == 0
    assert result.ratios[0] == pytest.approx(math.log(0.100001 / 1e-6))
    assert result.ratios[1:] == pytest.approx((0.0, 0.0, 0.0))


def test_probe_is_deterministic_and_costs_exactly_two_steps_per_iteration() -> None:
    calls = {"n": 0}

    def counting_step(x, r):
        calls["n"] += 1
        return x + float(r.normal())

    def run(seed: int) -> DivergenceResult:
        return estimate_divergence(
            0.0,
            counting_step,
            lambda x, y: abs(x - y),
            np.random.default_rng(seed),
            steps=7,
            epsilon=1e-6,
            perturb_fn=lambda x, r: x + 1e-3,
        )

    first = run(11)
    assert calls["n"] == 14
    second = run(11)
    assert first == second
    assert run(12) != first


def test_branches_are_driven_by_independent_streams() -> None:
    """Two parallel trajectories, not one trajectory and a coupled copy."""
    result = estimate_divergence(
        0.0,
        lambda x, r: x + float(r.normal()),
        lambda x, y: abs(x - y),
        np.random.default_rng(5),
        steps=6,
        epsilon=1e-9,
        perturb_fn=lambda x, r: x,
    )
    assert result.distances[0] == 0.0
    assert all(d > 0.0 for d in result.distances[1:])


def test_the_estimate_telescopes_to_the_endpoints() -> None:
    """Eq. (8) is a sum of consecutive log-ratios, so only d_0 and d_T survive."""
    eps = 1e-6
    result = estimate_divergence(
        0.0,
        lambda x, r: x + float(r.normal()),
        lambda x, y: abs(x - y),
        np.random.default_rng(21),
        steps=12,
        epsilon=eps,
        perturb_fn=lambda x, r: x + 0.05,
    )
    assert result.degenerate == 0
    expected = math.log((result.distances[-1] + eps) / (result.distances[0] + eps)) / 12
    assert result.estimate == pytest.approx(expected, rel=1e-12)


def test_perturb_touches_one_entity_and_d_struct_can_see_it(rep: Representation) -> None:
    from trope.distance import StructuralDistance

    out = perturb_single_name(rep, np.random.default_rng(3))
    changed = [
        (a, b) for a, b in zip(rep.entities, out.entities, strict=True) if a != b
    ]
    assert len(changed) == 1
    before, after = changed[0]
    assert after.id == before.id and after.type == before.type
    assert after.sort != before.sort and after.sort.startswith(before.sort)
    assert out.relations == rep.relations
    assert out.history[-1].operator == "perturb_single_name"

    distance = StructuralDistance()
    separation = distance(rep, out)
    assert separation > 0.0
    assert separation < distance(rep, Representation(
        entities=rep.entities[:1],
        relations=(),
        assumptions=rep.assumptions,
        goal=rep.goal,
    ))


def test_perturb_leaves_an_entityless_representation_alone() -> None:
    bare = Representation(goal=Goal("nothing"))
    assert perturb_single_name(bare, np.random.default_rng(0)) is bare


def test_probe_rejects_bad_settings() -> None:
    with pytest.raises(ValueError):
        estimate_divergence(
            0.0, lambda x, r: x, lambda x, y: 1.0, np.random.default_rng(0), steps=0
        )
    with pytest.raises(ValueError):
        estimate_divergence(
            0.0, lambda x, r: x, lambda x, y: 1.0, np.random.default_rng(0), epsilon=-1.0
        )
