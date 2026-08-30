"""Tests for the alpha-stable sampler, its densities, and the rejection loop."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import integrate
from scipy import stats as sps
from scipy.special import gamma as gamma_fn
from scipy.special import ndtr

from trope.sampling import stable as st
from trope.sampling.rejection import (
    RadicalitySampler,
    RejectionLoopStalled,
    _min_statistic,
)
from trope.sampling.stable import (
    folded_stable_cdf,
    folded_stable_ppf,
    sample_radicality,
    sample_stable,
    stable_cdf,
    stable_pdf,
)
from trope.stats.gof import ks_statistic
from trope.stats.hill import hill_estimate

ALPHAS = (1.2, 1.6, 1.9)


def _normal_cdf(x, sd):
    return ndtr(np.asarray(x) / sd)


def _cauchy_cdf(x, scale):
    return 0.5 + np.arctan(np.asarray(x) / scale) / math.pi


def test_alpha_two_draws_are_normal_with_sd_root_two_gamma():
    rng = np.random.default_rng(20260829)
    scale = 1.3
    x = sample_stable(rng, 2.0, 0.0, scale, 0.0, size=20_000)
    result = sps.kstest(x, lambda t: _normal_cdf(t, math.sqrt(2.0) * scale))
    assert result.pvalue > 0.01
    assert sps.kstest(x, lambda t: _normal_cdf(t, scale)).pvalue < 1e-10


def test_alpha_one_draws_are_cauchy_with_scale_gamma():
    rng = np.random.default_rng(20260829)
    scale = 0.7
    x = sample_stable(rng, 1.0, 0.0, scale, 0.0, size=20_000)
    assert sps.kstest(x, lambda t: _cauchy_cdf(t, scale)).pvalue > 0.01


@pytest.mark.parametrize("alpha", ALPHAS)
def test_draws_follow_the_module_cdf(alpha):
    rng = np.random.default_rng(4)
    x = sample_stable(rng, alpha, 0.0, 0.3, 0.05, size=20_000)
    assert sps.kstest(x, lambda t: stable_cdf(t, alpha, 0.3, 0.05)).pvalue > 0.01


def _both_parameterizations(alpha, beta, scale, seed=3, n=32):
    kwargs = dict(size=n)
    a = sample_stable(np.random.default_rng(seed), alpha, beta, scale, 0.0,
                      parameterization="S0", **kwargs)
    b = sample_stable(np.random.default_rng(seed), alpha, beta, scale, 0.0,
                      parameterization="S1", **kwargs)
    return a, b


@pytest.mark.parametrize("alpha", (1.0, 1.2, 1.6, 2.0))
def test_s0_and_s1_coincide_at_beta_zero(alpha):
    a, b = _both_parameterizations(alpha, 0.0, 0.9, seed=11, n=64)
    assert np.array_equal(a, b)


@pytest.mark.parametrize("alpha", (0.8, 1.6, 1.9))
def test_s0_is_the_s1_draw_shifted_when_skewed(alpha):
    a, b = _both_parameterizations(alpha, 0.6, 1.7)
    expected = -1.7 * 0.6 * math.tan(math.pi * alpha / 2.0)
    assert np.allclose(a - b, expected, rtol=1e-12, atol=1e-12)


def test_s0_shift_at_alpha_one_uses_log_gamma():
    a, b = _both_parameterizations(1.0, 0.4, 2.0, n=16)
    expected = -2.0 * 0.4 * (2.0 / math.pi) * math.log(2.0)
    assert np.allclose(a - b, expected, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("alpha", ALPHAS)
def test_scale_is_multiplicative_on_the_same_stream(alpha):
    unit = sample_stable(np.random.default_rng(8), alpha, 0.0, 1.0, 0.0, size=256)
    scaled = sample_stable(np.random.default_rng(8), alpha, 0.0, 2.5, 0.0, size=256)
    assert np.allclose(scaled, 2.5 * unit, rtol=1e-13, atol=0.0)


def test_draws_are_deterministic_given_the_generator_seed():
    first = sample_stable(np.random.default_rng(99), 1.55, 0.3, 0.4, -0.2, size=128)
    second = sample_stable(np.random.default_rng(99), 1.55, 0.3, 0.4, -0.2, size=128)
    assert np.array_equal(first, second)


@pytest.mark.parametrize("alpha", ALPHAS)
def test_empirical_tail_exponent_tracks_alpha(alpha):
    rng = np.random.default_rng(2026)
    rho = sample_radicality(rng, alpha, 0.4, size=400_000)
    assert abs(hill_estimate(rho, k=400).alpha - alpha) < 0.20


def test_sample_radicality_is_the_magnitude_of_the_same_draw():
    rho = sample_radicality(np.random.default_rng(5), 1.6, 0.3, size=100)
    z = sample_stable(np.random.default_rng(5), 1.6, 0.0, 0.3, 0.0, size=100)
    assert np.array_equal(rho, np.abs(z))
    assert np.all(rho >= 0.0)
    assert isinstance(sample_radicality(np.random.default_rng(5), 1.6, 0.3), float)


def test_rejects_impossible_parameters():
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError):
        sample_stable(rng, 2.5)
    with pytest.raises(ValueError):
        sample_stable(rng, 1.6, beta=1.5)
    with pytest.raises(ValueError):
        sample_stable(rng, 1.6, gamma=0.0)
    with pytest.raises(ValueError):
        sample_stable(rng, 1.6, parameterization="S2")


@pytest.mark.parametrize("alpha", (0.8, 1.0, 1.2, 1.6, 1.9, 2.0))
def test_quadrature_pdf_at_zero_matches_the_gamma_identity(alpha):
    got = float(st._cf_pdf(np.array([0.0]), alpha)[0])
    assert got == pytest.approx(gamma_fn(1.0 / alpha) / (math.pi * alpha), rel=1e-8)


def test_quadrature_reproduces_the_gaussian_closed_form():
    u = np.linspace(0.0, 5.0, 41)
    want = np.exp(-(u**2) / 4.0) / math.sqrt(4.0 * math.pi)
    assert np.allclose(st._cf_pdf(u, 2.0), want, rtol=1e-9, atol=0.0)
    assert np.allclose(st._cf_sf(u, 2.0), ndtr(-u / math.sqrt(2.0)), rtol=1e-9, atol=0.0)


def test_quadrature_reproduces_the_cauchy_closed_form():
    u = np.linspace(0.0, 20.0, 81)
    assert np.allclose(st._cf_pdf(u, 1.0), 1.0 / (math.pi * (1.0 + u**2)), rtol=1e-9, atol=0.0)
    assert np.allclose(st._cf_sf(u, 1.0), 0.5 - np.arctan(u) / math.pi, rtol=1e-9, atol=0.0)


@pytest.mark.parametrize("alpha", (0.5, 0.8, 1.05, 1.2, 1.6, 1.9, 1.99))
def test_tail_series_agrees_with_the_quadrature_where_they_meet(alpha):
    u = np.array([8.0, 10.0, 14.0]) if alpha < 1.0 else np.array([20.0, 25.0, 30.0])
    assert np.allclose(st._tail_series(u, alpha, sf=False), st._cf_pdf(u, alpha), rtol=1e-6)
    assert np.allclose(st._tail_series(u, alpha, sf=True), st._cf_sf(u, alpha), rtol=1e-6)


@pytest.mark.parametrize("alpha", (1.2, 1.6, 1.9))
def test_cached_spline_agrees_with_the_direct_quadrature(alpha):
    u = np.linspace(0.0, st._standard(alpha).u_split, 97)
    assert np.allclose(stable_pdf(u, alpha), st._cf_pdf(u, alpha), rtol=1e-6)
    assert np.allclose(1.0 - stable_cdf(u, alpha), st._cf_sf(u, alpha), rtol=1e-6)


@pytest.mark.parametrize("alpha", (1.2, 1.6, 2.0))
def test_density_integrates_to_one(alpha):
    total, _ = integrate.quad(
        lambda t: float(stable_pdf(t, alpha, 0.3, 0.1)), -np.inf, np.inf, limit=400
    )
    assert total == pytest.approx(1.0, abs=1e-7)


@pytest.mark.parametrize("alpha", (1.2, 1.6))
def test_cdf_is_the_integral_of_the_pdf(alpha):
    lo, hi = -1.0, 2.5
    area, _ = integrate.quad(lambda t: float(stable_pdf(t, alpha, 0.4)), lo, hi, limit=400)
    jump = float(stable_cdf(hi, alpha, 0.4)) - float(stable_cdf(lo, alpha, 0.4))
    assert jump == pytest.approx(area, abs=1e-8)


@pytest.mark.parametrize("alpha", (1.2, 1.6, 1.9))
def test_symmetric_cdf_and_pdf_obey_their_symmetries(alpha):
    x = np.array([0.0, 0.1, 0.9, 4.0, 60.0])
    assert np.allclose(stable_cdf(-x, alpha, 0.5), 1.0 - stable_cdf(x, alpha, 0.5), rtol=1e-10)
    assert np.allclose(stable_pdf(-x, alpha, 0.5), stable_pdf(x, alpha, 0.5), rtol=1e-12)


@pytest.mark.parametrize("alpha", (1.2, 1.6, 1.9))
def test_density_scales_as_one_over_gamma(alpha):
    x = np.linspace(-4.0, 4.0, 33)
    scaled = stable_pdf(x / 0.7, alpha, 1.0) / 0.7
    assert np.allclose(stable_pdf(x, alpha, 0.7), scaled, rtol=1e-10)


@pytest.mark.parametrize("alpha", (1.0, 1.2, 1.6, 1.9, 2.0))
def test_folded_cdf_is_a_distribution_function(alpha):
    x = np.concatenate([[-1.0, 0.0], np.geomspace(1e-3, 1e9, 300)])
    values = folded_stable_cdf(x, alpha, 0.3)
    assert np.all((values >= 0.0) & (values <= 1.0))
    assert np.all(np.diff(values) >= -1e-15)
    assert values[0] == 0.0 and values[1] == 0.0
    assert values[-1] == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("alpha", (1.0, 1.2, 1.6, 2.0))
def test_folded_ppf_inverts_the_folded_cdf(alpha):
    q = np.linspace(0.001, 0.999, 41)
    x = folded_stable_ppf(q, alpha, 0.35)
    assert np.all(np.diff(x) > 0.0)
    assert np.allclose(folded_stable_cdf(x, alpha, 0.35), q, atol=1e-9)
    assert folded_stable_ppf(0.0, alpha, 0.35) == pytest.approx(0.0, abs=1e-12)
    assert math.isinf(float(folded_stable_ppf(1.0, alpha, 0.35)))


@pytest.mark.parametrize("alpha", ALPHAS)
def test_folded_cdf_matches_the_empirical_law_of_the_magnitudes(alpha):
    rho = sample_radicality(np.random.default_rng(17), alpha, 0.25, size=20_000)
    assert sps.kstest(rho, lambda t: folded_stable_cdf(t, alpha, 0.25)).pvalue > 0.01


def test_folded_ppf_rejects_levels_outside_the_unit_interval():
    with pytest.raises(ValueError):
        folded_stable_ppf(1.2, 1.6)


KS_95 = math.sqrt(-0.5 * math.log(0.05 / 2.0))


def _critical(n: int) -> float:
    """The asymptotic Kolmogorov critical value the sampler accepts below."""
    return KS_95 / math.sqrt(n)


def _calibrated_run(sampler: RadicalitySampler, rng, n: int) -> list:
    """Draw `n` times, feeding each realised distance back into the window."""
    draws = []
    for _ in range(n):
        draw = sampler.draw(rng)
        sampler.observe_distance(draw.rho)
        draws.append(draw)
    return draws


def test_the_repeat_until_terminates_and_almost_never_rejects():
    rejections: list[int] = []
    for seed in range(5):
        sampler = RadicalitySampler(1.6, 0.3, window=64)
        try:
            draws = _calibrated_run(sampler, np.random.default_rng(seed), 300)
        except RejectionLoopStalled as exc:
            pytest.fail(f"the unbounded loop stalled on seed {seed}: {exc}")
        assert sampler.stats["vacuous"] == 0.0
        rejections.extend(draw.rejections for draw in draws)

    counts = np.bincount(rejections)
    assert len(rejections) == 1500
    assert counts[0] == 1495
    assert max(rejections) == 7
    assert float(np.mean(rejections)) == pytest.approx(12 / 1500)


def test_the_attempt_ceiling_does_not_fire_in_normal_operation():
    """It reports a stall with its numbers; it is not a bound on the loop."""

    def run(**kwargs) -> tuple[list, dict[str, float]]:
        sampler = RadicalitySampler(1.6, 0.3, window=64, **kwargs)
        draws = _calibrated_run(sampler, np.random.default_rng(0), 300)
        return [(d.z, d.rejections, d.vacuous) for d in draws], sampler.stats

    assert RadicalitySampler(1.6).attempt_ceiling == 10_000
    default, default_stats = run()
    tight, tight_stats = run(attempt_ceiling=16)
    assert tight == default
    assert tight_stats == default_stats
    assert tight_stats["attempts"] == 307.0


def test_the_realised_distance_replaces_the_provisional_entry():
    sampler = RadicalitySampler(1.6, 0.3, window=8)
    for value in (0.2, 0.25, 0.3):
        sampler.observe_distance(value)

    draw = sampler.draw(np.random.default_rng(0))
    assert sampler.distance_window.size == 4
    assert sampler.distance_window[-1] == pytest.approx(draw.rho)

    sampler.observe_distance(0.5)
    assert sampler.distance_window.size == 4
    assert sampler.distance_window[-1] == pytest.approx(0.5)
    assert sampler.window[-1] == pytest.approx(float(folded_stable_cdf(0.5, 1.6, 0.3)))


def test_a_draw_whose_distance_never_came_back_is_overwritten():
    sampler = RadicalitySampler(1.6, 0.3, window=8)
    rng = np.random.default_rng(0)
    first = sampler.draw(rng)
    second = sampler.draw(rng)
    assert first.rho != second.rho
    assert sampler.distance_window.size == 1
    assert sampler.distance_window[-1] == pytest.approx(second.rho)


def test_a_window_no_draw_can_rescue_is_accepted_as_vacuous():
    sampler = RadicalitySampler(1.6, 0.3, window=32)
    rng = np.random.default_rng(11)
    for value in rng.uniform(3.0, 4.0, size=32):
        sampler.observe_distance(float(value))

    transformed = sampler.window
    critical = _critical(transformed.size + 1)
    assert transformed.min() > 0.99
    assert _min_statistic(transformed) == pytest.approx(0.9609, abs=1e-4)
    assert critical == pytest.approx(0.2364, abs=1e-4)
    assert _min_statistic(transformed) > critical

    first = sampler.draw(rng)
    assert first.vacuous
    assert first.rejections == 0
    assert first.ks_stat > critical
    assert sampler.stats["vacuous"] == 1.0

    for _ in range(9):
        sampler.draw(rng)
        sampler.observe_distance(float(rng.uniform(3.0, 4.0)))
    assert sampler.stats["vacuous"] == 10.0
    assert sampler.stats["tested"] == 0.0
    assert sampler.stats["acceptance_rate"] == 0.0


MOVING_GAMMAS = (0.08, 0.3, 1.0, 2.5)


def test_the_transform_makes_a_moving_gamma_harmless():
    rng = np.random.default_rng(2026)
    sampler = RadicalitySampler(1.6, MOVING_GAMMAS[0], window=64)
    for i in range(200):
        sampler.set_gamma(MOVING_GAMMAS[i % len(MOVING_GAMMAS)])
        sampler.observe_distance(sampler.draw(rng).rho)

    assert sampler.stats["vacuous"] == 0.0
    assert sampler.stats["attempts"] == 201.0
    assert sampler.stats["acceptance_rate"] == pytest.approx(200 / 201)

    raw = sampler.distance_window
    critical = _critical(raw.size + 1)

    def reference(t):
        return folded_stable_cdf(t, sampler.alpha, sampler.gamma)

    probe = np.random.default_rng(7)
    accepted = 0
    for _ in range(200):
        rho = abs(float(sample_stable(probe, sampler.alpha, 0.0, sampler.gamma, 0.0)))
        accepted += ks_statistic(np.append(raw, rho), reference) <= critical

    assert accepted == 0
    assert critical == pytest.approx(0.1685, abs=1e-4)
    assert ks_statistic(raw, reference) > 0.5


def test_sampler_is_deterministic_given_the_generator_seed():
    def run():
        sampler = RadicalitySampler(1.6, 0.3, window=32)
        draws = _calibrated_run(sampler, np.random.default_rng(1234), 120)
        return [(d.z, d.rho, d.rejections, d.vacuous, d.ks_stat) for d in draws]

    assert run() == run()


def test_accepted_draws_keep_the_target_tail_index():
    sampler = RadicalitySampler(1.6, 0.3, window=32)
    draws = _calibrated_run(sampler, np.random.default_rng(1), 3000)
    rho = np.array([draw.rho for draw in draws])
    assert abs(hill_estimate(rho, k=50).alpha - 1.6) < 0.35


def test_rejection_rate_is_a_live_diagnostic():
    sampler = RadicalitySampler(1.6, 0.3, window=32)
    _calibrated_run(sampler, np.random.default_rng(1), 600)
    stats = sampler.stats
    assert stats["draws"] == 600.0
    assert stats["attempts"] == 606.0
    assert stats["rejection_rate"] == pytest.approx(6 / 606)
    assert stats["mean_rejections"] == pytest.approx(6 / 600)
    assert stats["window_size"] == 32.0
    assert stats["gamma"] == 0.3


def test_set_gamma_clamps_to_the_configured_box():
    sampler = RadicalitySampler(1.6, 0.3, gamma_min=0.05, gamma_max=1.5)
    assert sampler.set_gamma(10.0) == 1.5
    assert sampler.set_gamma(1e-9) == 0.05
    assert RadicalitySampler(1.6, 99.0, gamma_max=1.5).gamma == 1.5


def test_window_holds_the_probability_integral_transform():
    rng = np.random.default_rng(9)
    sampler = RadicalitySampler(1.6, 0.3, window=4)
    first = sampler.draw(rng)
    assert sampler.window[-1] == pytest.approx(folded_stable_cdf(first.rho, 1.6, 0.3))
    sampler.observe_distance(first.rho)

    sampler.set_gamma(1.2)
    second = sampler.draw(rng)
    assert sampler.window[-1] == pytest.approx(folded_stable_cdf(second.rho, 1.6, 1.2))
    assert sampler.window.size == 2
    assert np.allclose(sampler.distance_window, [first.rho, second.rho])


def test_draws_over_rho_max_are_counted_but_not_clipped():
    sampler = RadicalitySampler(1.2, 1.0, window=32, rho_max=2.0)
    draws = _calibrated_run(sampler, np.random.default_rng(3), 300)
    rho = np.array([draw.rho for draw in draws])
    assert np.count_nonzero(rho > 2.0) == 81
    assert rho.max() > 300.0
    assert sampler.stats["saturated"] == 81.0


def test_observe_is_the_alias_that_seeds_the_window():
    sampler = RadicalitySampler(1.6, 0.3, window=4)
    for value in (0.5, 1.5, 2.5):
        sampler.observe_distance(value)
    assert np.allclose(sampler.distance_window, [0.5, 1.5, 2.5])
    assert np.allclose(sampler.window, folded_stable_cdf([0.5, 1.5, 2.5], 1.6, 0.3))

    sampler.observe(0.9)
    assert np.allclose(sampler.distance_window, [0.5, 1.5, 2.5, 0.9])
    assert sampler.stats["window_size"] == 4.0


def test_an_empty_window_accepts_the_first_draw():
    sampler = RadicalitySampler(1.6, 0.3, window=32)
    first = sampler.draw(np.random.default_rng(3))
    assert first.rejections == 0 and not first.vacuous
    assert first.ks_stat >= 0.5
    assert _min_statistic(np.array([])) == pytest.approx(0.5)
    assert _critical(1) == pytest.approx(1.3581, abs=1e-4)


def test_observe_rejects_negative_or_infinite_magnitudes():
    sampler = RadicalitySampler(1.6, 0.3)
    with pytest.raises(ValueError):
        sampler.observe(-1.0)
    with pytest.raises(ValueError):
        sampler.observe(math.inf)
    with pytest.raises(ValueError):
        sampler.observe_distance(math.nan)


def test_sampler_rejects_impossible_configuration():
    with pytest.raises(ValueError):
        RadicalitySampler(1.6, 0.3, window=0)
    with pytest.raises(ValueError):
        RadicalitySampler(1.6, 0.3, ks_alpha=1.0)
    with pytest.raises(ValueError):
        RadicalitySampler(1.6, 0.3, gamma_min=1.0, gamma_max=0.5)
    with pytest.raises(ValueError):
        RadicalitySampler(1.6, 0.3, attempt_ceiling=0)


def test_rejecting_draws_alone_cannot_shape_anything():
    """Why the loop rejects proposals rather than draws of Z."""
    sampler = RadicalitySampler(1.6, 0.3, ks_alpha=0.05, window=64)
    rng = np.random.default_rng(4)
    draws = [sampler.draw(rng) for _ in range(400)]
    rejections = sum(d.rejections for d in draws)
    assert rejections <= 20, rejections
    assert sampler.stats["acceptance_rate"] > 0.95


def test_a_proposal_that_realises_nothing_is_taken_without_a_test():
    """A no-op produces no pair (R, R'), so there is no distance to test."""
    sampler = RadicalitySampler(1.6, 0.3, window=64)
    for value in (0.4, 0.9, 1.3, 0.7):
        sampler.observe_distance(value)
    before = len(sampler.distance_window)

    draw = sampler.draw(np.random.default_rng(0), lambda rho: 0.0)
    assert draw.vacuous and draw.reason == "no-displacement"
    assert draw.rejections == 0
    assert draw.distance == 0.0
    assert len(sampler.distance_window) == before
    assert sampler.stats["zero_displacement"] == 1.0


def test_a_proposal_the_operator_cannot_vary_terminates_as_exhausted():
    """The displacements an operator can realise form a finite set."""
    sampler = RadicalitySampler(1.6, 0.3, ks_alpha=0.05, window=64, stall_window=8)
    window = [0.000526, 0.037986, 0.075844, 0.114521, 0.154497, 0.196356, 0.240852, 0.289022]
    for value in window:
        sampler.observe_distance(value)
    assert _min_statistic(sampler.window) < sampler._critical(len(window) + 1)

    draw = sampler.draw(np.random.default_rng(1), lambda rho: 5.256e-4)
    assert draw.vacuous and draw.reason == "exhausted"
    assert draw.distance == pytest.approx(5.256e-4)
    assert draw.rejections >= 8
    assert sampler.stats["vacuous"] == 1.0


def test_a_proposal_the_operator_can_vary_is_shaped_by_the_filter():
    """The proposal form is what lets the filter move the realised sample."""
    sampler = RadicalitySampler(1.6, 0.3, ks_alpha=0.05, window=32)
    rng = np.random.default_rng(11)
    accepted, rejections = [], 0
    for _ in range(300):
        draw = sampler.draw(rng, lambda rho: 0.5 * rho + 0.01)
        accepted.append(draw.distance)
        rejections += draw.rejections
    assert rejections > 0
    assert all(d > 0.0 for d in accepted)
    assert len(sampler.distance_window) == 32


def test_every_exit_describes_the_proposal_the_caller_still_holds():
    window = [0.000526, 0.037986, 0.075844, 0.114521, 0.154497, 0.196356, 0.240852]
    for realise, expect in (
        (lambda rho: 5.256e-4, "exhausted"),
        (lambda rho: 0.0, "no-displacement"),
        (lambda rho: 0.4 * rho + 0.02, ""),
    ):
        sampler = RadicalitySampler(1.6, 0.3, ks_alpha=0.05, window=64, stall_window=6)
        for value in window:
            sampler.observe_distance(value)
        held: dict[str, float] = {}

        def propose(rho: float, realise=realise, held=held) -> float:
            held["rho"] = rho
            held["distance"] = realise(rho)
            return held["distance"]

        draw = sampler.draw(np.random.default_rng(1), propose)
        assert draw.reason == expect
        assert draw.rho == held["rho"]
        assert draw.distance == held["distance"]
        if draw.distance > 0.0:
            assert sampler.distance_window[-1] == pytest.approx(draw.distance)


def test_a_zero_realising_proposal_takes_its_stand_in_with_it():
    sampler = RadicalitySampler(1.6, 0.3, window=64)
    sampler.draw(np.random.default_rng(0))
    assert len(sampler.distance_window) == 1
    sampler.observe_distance(0.0)
    assert len(sampler.distance_window) == 0
    sampler.draw(np.random.default_rng(1))
    assert len(sampler.distance_window) == 1


def test_the_accepted_proposal_is_the_one_the_caller_keeps():
    """The last call to `propose` is the accepted one, so nothing is applied twice."""
    sampler = RadicalitySampler(1.6, 0.3, ks_alpha=0.05, window=16)
    for value in (0.3, 0.5, 0.4, 0.6):
        sampler.observe_distance(value)
    seen: list[float] = []

    def propose(rho: float) -> float:
        seen.append(rho)
        return 0.5 * rho + 0.05

    draw = sampler.draw(np.random.default_rng(3), propose)
    assert len(seen) == draw.attempts
    assert draw.distance == pytest.approx(0.5 * seen[-1] + 0.05)
    assert sampler.distance_window[-1] == pytest.approx(draw.distance)
