"""Operator policy pi_theta, Eq. (7)."""

from __future__ import annotations

import numpy as np
import pytest

from trope.sampling.bandit import OperatorPolicy

NAMES = ("alpha", "beta", "gamma", "delta")


def policy(**kwargs) -> OperatorPolicy:
    defaults = dict(names=NAMES, eta=0.1, window=8, temperature=1.0)
    defaults.update(kwargs)
    return OperatorPolicy(**defaults)


def test_starts_uniform() -> None:
    p = policy().probabilities()
    assert p == pytest.approx(np.full(len(NAMES), 0.25))


def test_advantage_is_the_window_mean_against_the_pooled_baseline() -> None:
    pi = policy()
    for r in (1.0, 2.0, 3.0):
        pi.observe("alpha", r)
    for r in (0.0, 1.0):
        pi.observe("beta", r)
    assert pi.baseline() == pytest.approx(1.4)
    assert pi.update("alpha") == pytest.approx((2.0 - 1.4) / 1.0)
    p = pi.probabilities()
    assert p[0] > 0.25
    assert p[2] == pytest.approx(p[3])


def test_short_or_constant_windows_do_not_update() -> None:
    pi = policy()
    before = pi.probabilities()

    pi.observe("alpha", 3.0)
    assert pi.update("alpha") == 0.0
    assert pi.probabilities() == pytest.approx(before)

    for _ in range(5):
        pi.observe("beta", 2.0)
    assert pi.update("beta") == 0.0
    assert pi.probabilities() == pytest.approx(before)
    assert np.all(np.isfinite(pi.probabilities()))


def test_probabilities_are_a_distribution() -> None:
    pi = policy()
    for _ in range(40):
        pi.observe("alpha", 5.0 + float(np.random.default_rng(0).normal()))
        pi.observe("beta", -5.0)
        pi.update("alpha")
    p = pi.probabilities()
    assert p.sum() == pytest.approx(1.0)
    assert np.all(np.isfinite(p))
    assert p.min() > 0.0


def test_the_standardised_advantage_is_unbounded() -> None:
    """Eq. (7) divides a pooled difference by the operator's own dispersion."""
    pi = policy()
    for _ in range(4):
        pi.observe("alpha", 5.0)
        pi.observe("alpha", 5.1)
    for _ in range(4):
        pi.observe("beta", -5.0)
        pi.observe("beta", -5.000001)
    assert abs(pi.update("beta")) > 1e6


def test_a_near_constant_bad_window_kills_an_operator_in_one_step() -> None:
    """The consequence of that, and the reason it is worth pinning."""
    pi = policy()
    for _ in range(4):
        pi.observe("alpha", 5.0)
        pi.observe("alpha", 5.1)
    for _ in range(4):
        pi.observe("beta", -5.0)
        pi.observe("beta", -5.000001)
    pi.update("beta")
    assert pi.probabilities()[1] == 0.0
    assert pi.probabilities().sum() == pytest.approx(1.0)


def test_ordinary_reward_noise_leaves_every_operator_reachable() -> None:
    """The regime a run is actually in: rewards with real dispersion."""
    rng = np.random.default_rng(20260830)
    pi = policy()
    for _ in range(64):
        name = pi.sample(rng)
        mean = {"alpha": 1.2, "beta": 0.4}.get(name, 0.8)
        pi.observe(name, float(rng.normal(mean, 0.35)))
        pi.update(name)
    p = pi.probabilities()
    assert p.min() > 1e-6
    assert p[0] > p[1]


def test_consistently_better_rewards_gain_mass() -> None:
    rng = np.random.default_rng(7)
    pi = policy()
    for _ in range(60):
        pi.observe("alpha", 0.8 + 0.1 * float(rng.normal()))
        pi.update("alpha")
        pi.observe("beta", 0.2 + 0.1 * float(rng.normal()))
        pi.update("beta")
    p = pi.probabilities()
    assert p[0] > p[1]
    assert p[0] > 0.25 > p[1]


def test_every_operator_stays_drawable() -> None:
    pi = policy()
    pi.observe("alpha", 1.0)
    pi.observe("alpha", 3.0)
    pi.update("alpha")
    rng = np.random.default_rng(0)
    drawn = {pi.sample(rng) for _ in range(400)}
    assert drawn == set(NAMES)
    assert pi.counts()["gamma"] == 0


def test_sampling_is_deterministic_given_a_seeded_generator() -> None:
    def run() -> list[str]:
        pi = policy()
        stream = np.random.default_rng(4)
        drawn = []
        for _ in range(30):
            name = pi.sample(stream)
            drawn.append(name)
            pi.observe(name, float(stream.normal()))
            pi.update(name)
        return drawn

    first, second = run(), run()
    assert first == second
    assert len(set(first)) > 1


def test_state_dict_round_trip() -> None:
    rng = np.random.default_rng(2)
    pi = policy()
    for _ in range(30):
        name = pi.sample(rng)
        pi.observe(name, float(rng.normal()))
        pi.update(name)
    state = pi.state_dict()

    restored = policy()
    restored.load_state_dict(state)
    assert restored.probabilities() == pytest.approx(pi.probabilities())
    assert restored.counts() == pi.counts()
    assert restored.baseline() == pytest.approx(pi.baseline())
    assert restored.sample(np.random.default_rng(9)) == pi.sample(
        np.random.default_rng(9)
    )
    a = np.random.default_rng(3)
    b = np.random.default_rng(3)
    for _ in range(10):
        left, right = pi.sample(a), restored.sample(b)
        assert left == right
        reward = float(a.normal())
        b.normal()
        pi.observe(left, reward)
        restored.observe(right, reward)
        assert pi.update(left) == pytest.approx(restored.update(right))

    with pytest.raises(ValueError):
        policy(names=("alpha", "beta")).load_state_dict(state)


def test_never_produces_nan_under_a_thousand_mixed_cycles() -> None:
    rng = np.random.default_rng(20260830)
    pi = policy(eta=0.5)
    constant = {"delta": 0.5}
    for _ in range(1000):
        name = pi.sample(rng)
        if name in constant:
            reward = constant[name]
        elif rng.random() < 0.1:
            reward = 0.0
        else:
            reward = float(rng.normal(loc=0.3, scale=2.0))
        pi.observe(name, reward)
        advantage = pi.update(name)
        assert np.isfinite(advantage)
        p = pi.probabilities()
        assert np.all(np.isfinite(p))
        assert p.sum() == pytest.approx(1.0)
        assert p.min() > 0.0
    assert pi.probabilities().min() > 0.0


def test_rejects_bad_construction_and_unknown_names() -> None:
    with pytest.raises(ValueError):
        OperatorPolicy(())
    with pytest.raises(ValueError):
        OperatorPolicy(("a", "a"))
    with pytest.raises(ValueError):
        OperatorPolicy(("a", "b"), window=0)
    with pytest.raises(ValueError):
        OperatorPolicy(("a", "b"), temperature=0.0)
    pi = policy()
    with pytest.raises(KeyError):
        pi.observe("nope", 1.0)
    with pytest.raises(KeyError):
        pi.update("nope")


def test_a_lone_operator_has_nothing_to_be_better_than() -> None:
    """With one operator observed, the baseline is its own mean, so A is zero."""
    pi = policy()
    for r in (0.0, 1.0, 2.0, 6.0):
        pi.observe("alpha", r)
        assert pi.update("alpha") == pytest.approx(0.0)
    assert pi.probabilities() == pytest.approx(np.full(len(NAMES), 0.25))


def test_temperature_flattens_the_distribution() -> None:
    pi = policy()
    for r in (0.0, 1.0, 2.0, 6.0):
        pi.observe("alpha", r)
        pi.observe("beta", -r)
        pi.update("alpha")
    sharp = pi.probabilities()
    assert sharp.max() > 0.25
    pi.temperature = 10.0
    flat = pi.probabilities()
    assert flat.max() < sharp.max()
    assert flat.sum() == pytest.approx(1.0)


def test_window_is_bounded_by_W() -> None:
    pi = policy(window=3)
    for r in range(10):
        pi.observe("alpha", float(r))
    assert pi.counts()["alpha"] == 3
    assert pi.baseline() == pytest.approx((7.0 + 8.0 + 9.0) / 3.0)
