"""Tests for the tail-index estimator, the stable fits and the paper's tests."""

from __future__ import annotations

import inspect
import json
import math

import numpy as np
import pytest
from scipy import stats as sps

from trope.calibrate import PAPER_ALPHA_FIELD, CalibrationReport, calibrate
from trope.config import Config
from trope.sampling.stable import sample_radicality, sample_stable, stable_logpdf
from trope.stats.gof import (
    BOUNDARY_NOTE,
    ESTIMATOR_NOTE,
    MLE,
    NO_ESTIMATOR,
    QUANTILE,
    ks_statistic,
    ks_test_stable,
    lr_gaussian_vs_stable,
)
from trope.stats.hill import default_k, hill_ci, hill_estimate, hill_plot
from trope.stats.stablefit import (
    StableParams,
    fixed_alpha_fit,
    fixed_alpha_mle_fit,
    gaussian_fit,
    mccullough_fit,
    mle_fit,
    nu_alpha,
    nu_scale,
    stable_nll,
)
from trope.stats.tests import (
    bootstrap_ci,
    holm_bonferroni,
    paired_bootstrap_diff,
    paired_wilcoxon,
    spearman,
)


def _pareto(rng: np.random.Generator, theta: float, size) -> np.ndarray:
    """Exact Pareto(1, theta): P(X > x) = x^-theta on x >= 1."""
    return rng.uniform(0.0, 1.0, size=size) ** (-1.0 / theta)


def test_hill_reciprocal_is_unbiased_on_exact_pareto():
    theta, k, reps = 1.5, 20, 3000
    rng = np.random.default_rng(20260830)
    h = np.array(
        [1.0 / hill_estimate(_pareto(rng, theta, 200), k).alpha for _ in range(reps)]
    )
    se = 1.0 / (theta * math.sqrt(k) * math.sqrt(reps))
    assert abs(h.mean() - 1.0 / theta) < 4.0 * se
    assert h.var(ddof=1) == pytest.approx(1.0 / (k * theta**2), rel=0.08)
    assert abs(h.mean() - (1.0 - 1.0 / k) / theta) > 6.0 * se


def test_hill_divides_by_the_k_plus_first_order_statistic():
    x = np.exp([4.0, 3.0, 2.0, 1.0, 0.0])
    assert hill_estimate(x, k=2).alpha == pytest.approx(1.0 / 1.5)


def test_hill_drops_non_positive_and_non_finite_values():
    x = np.concatenate([np.exp([4.0, 3.0, 2.0, 1.0, 0.0]), [0.0, -3.0, np.nan]])
    result = hill_estimate(x, k=2)
    assert result.n_dropped == 3
    assert result.n_used == 5
    assert result.alpha == pytest.approx(1.0 / 1.5)


def test_hill_counts_ties_at_the_threshold():
    result = hill_estimate(np.array([8.0, 4.0, 2.0, 2.0, 2.0]), k=2)
    assert result.n_ties == 3
    assert math.isfinite(result.alpha)
    assert math.isinf(hill_estimate(np.full(6, 3.0), k=2).alpha)


def test_default_k_is_computed_on_the_surviving_points():
    x = np.concatenate([_pareto(np.random.default_rng(0), 2.0, 100), np.full(5, -1.0)])
    result = hill_estimate(x)
    assert result.n_used == 100
    assert result.k == 21 == default_k(100)
    assert result.k == int(math.floor(100 ** (2.0 / 3.0)))


def test_hill_plot_reproduces_the_pointwise_estimates():
    x = _pareto(np.random.default_rng(7), 1.8, 400)
    ks, alphas = hill_plot(x, ks=[5, 25, 100, 399])
    for k, alpha in zip(ks, alphas, strict=False):
        assert alpha == pytest.approx(hill_estimate(x, int(k)).alpha, rel=1e-12)
    assert hill_plot(x)[0].size == 399


def test_hill_ci_brackets_the_estimate_and_shrinks_with_k():
    x = _pareto(np.random.default_rng(3), 1.6, 5000)
    for k in (50, 500):
        lo, hi = hill_ci(x, k)
        assert lo < hill_estimate(x, k).alpha < hi
    lo_50, hi_50 = hill_ci(x, 50)
    lo_500, hi_500 = hill_ci(x, 500)
    assert hi_500 - lo_500 < hi_50 - lo_50


def test_hill_ci_covers_the_truth_at_about_the_nominal_rate():
    theta, k, reps = 1.5, 200, 400
    rng = np.random.default_rng(5)
    covered = sum(
        lo <= theta <= hi
        for lo, hi in (hill_ci(_pareto(rng, theta, 4000), k) for _ in range(reps))
    )
    assert 0.90 <= covered / reps <= 0.99


def test_hill_overestimates_alpha_on_stable_data_at_the_default_k():
    rho = np.abs(sample_stable(np.random.default_rng(1), 1.9, size=40_000))
    assert hill_estimate(rho).alpha > 3.0
    assert abs(hill_estimate(rho, k=150).alpha - 1.9) < 0.25


def test_quantile_index_reproduces_mccullough_table_anchors():
    assert nu_alpha(2.0) == pytest.approx(2.439, abs=5e-4)
    assert nu_alpha(1.0) == pytest.approx(6.314, abs=5e-4)
    assert nu_scale(2.0) == pytest.approx(1.908, abs=5e-4)
    assert nu_scale(1.0) == pytest.approx(2.000, abs=5e-4)
    assert nu_alpha(1.2) > nu_alpha(1.6) > nu_alpha(1.9)


@pytest.mark.parametrize("alpha", (1.2, 1.6, 1.9))
def test_quantile_estimator_recovers_known_parameters(alpha):
    x = sample_stable(np.random.default_rng(31), alpha, 0.0, 0.7, 0.2, size=5000)
    fit = mccullough_fit(x)
    assert fit.alpha == pytest.approx(alpha, abs=0.06 if alpha < 1.8 else 0.12)
    assert fit.gamma == pytest.approx(0.7, rel=0.05)
    assert fit.delta == pytest.approx(0.2, abs=0.05)
    assert fit.beta == 0.0


@pytest.mark.parametrize("alpha", (1.2, 1.6, 1.9))
def test_maximum_likelihood_recovers_known_parameters(alpha):
    x = sample_stable(np.random.default_rng(42), alpha, 0.0, 0.7, 0.2, size=5000)
    fit = mle_fit(x)
    assert fit.alpha == pytest.approx(alpha, abs=0.08)
    assert fit.gamma == pytest.approx(0.7, rel=0.05)
    assert fit.delta == pytest.approx(0.2, abs=0.05)


def test_maximum_likelihood_improves_on_its_starting_point():
    x = sample_stable(np.random.default_rng(13), 1.4, 0.0, 0.5, 0.0, size=1500)
    start = StableParams(1.9, 0.0, 1.0, 0.5)
    assert stable_nll(x, mle_fit(x, x0=start)) < stable_nll(x, start)


def test_gaussian_fit_uses_the_stable_scale_convention():
    rng = np.random.default_rng(2)
    x = rng.normal(1.5, 3.0, size=4000)
    fit = gaussian_fit(x)
    assert fit.alpha == 2.0 and fit.beta == 0.0
    assert fit.gamma == pytest.approx(np.std(x) / math.sqrt(2.0), rel=1e-12)
    assert fit.delta == pytest.approx(np.mean(x), rel=1e-12)


def test_gaussian_fit_round_trips_through_the_stable_density():
    rng = np.random.default_rng(6)
    x = rng.normal(-0.4, 2.0, size=500)
    fit = gaussian_fit(x)
    grid = np.linspace(-8.0, 8.0, 65)
    want = sps.norm.logpdf(grid, fit.delta, fit.gamma * math.sqrt(2.0))
    assert np.allclose(stable_logpdf(grid, 2.0, fit.gamma, fit.delta), want, rtol=1e-12)
    assert stable_nll(x, fit) == pytest.approx(
        -float(np.sum(sps.norm.logpdf(x, np.mean(x), np.std(x)))), rel=1e-12
    )


def test_ks_statistic_known_answer():
    x = np.array([0.1, 0.2, 0.5, 0.9])
    assert ks_statistic(x, lambda t: t) == pytest.approx(0.3)
    assert ks_statistic(x, lambda t: t) == pytest.approx(sps.kstest(x, "uniform").statistic)


def test_ks_statistic_agrees_with_scipy_on_random_data():
    rng = np.random.default_rng(8)
    x = rng.normal(size=200)
    mine = ks_statistic(x, sps.norm.cdf)
    assert mine == pytest.approx(sps.kstest(x, sps.norm.cdf).statistic, rel=1e-12)


def test_ks_test_accepts_data_from_the_fitted_family():
    rng = np.random.default_rng(21)
    x = sample_stable(rng, 1.6, 0.0, 0.4, 0.0, size=600)
    result = ks_test_stable(x, n_boot=120, rng=rng)
    assert result.pvalue > 0.05
    assert 0.0 < result.pvalue <= 1.0
    assert result.n_boot == 120 and result.refit is False
    assert result.params.alpha == pytest.approx(1.6, abs=0.2)


def test_ks_test_rejects_a_uniform_sample():
    rng = np.random.default_rng(22)
    result = ks_test_stable(rng.uniform(-1.0, 1.0, size=600), n_boot=120, rng=rng)
    assert result.pvalue < 0.05


def test_ks_test_with_a_fixed_alpha_leaves_alpha_alone():
    rng = np.random.default_rng(23)
    x = sample_stable(rng, 1.6, 0.0, 0.4, 0.0, size=400)
    result = ks_test_stable(x, alpha=1.6, n_boot=60, rng=rng)
    assert result.params.alpha == 1.6
    assert 0.0 < result.pvalue <= 1.0


def test_ks_test_without_a_bootstrap_reports_no_pvalue():
    x = sample_stable(np.random.default_rng(24), 1.6, 0.0, 0.4, 0.0, size=200)
    result = ks_test_stable(x, n_boot=0)
    assert math.isnan(result.pvalue) and result.n_boot == 0 and result.stat > 0.0
    with pytest.raises(ValueError):
        ks_test_stable(x, n_boot=10)


def test_likelihood_ratio_is_small_on_gaussian_data():
    x = np.random.default_rng(25).normal(0.3, 1.2, size=800)
    result = lr_gaussian_vs_stable(x)
    assert 0.0 <= result.statistic < 6.0
    assert result.p_chi2 > 0.05
    assert result.df == 2 and "boundary" in result.note


def test_likelihood_ratio_is_large_on_heavy_tailed_data():
    x = sample_stable(np.random.default_rng(26), 1.2, 0.0, 0.5, 0.0, size=800)
    result = lr_gaussian_vs_stable(x)
    assert result.statistic > 50.0
    assert result.p_chi2 < 1e-6


@pytest.mark.parametrize("seed", (0, 1, 2, 3))
def test_likelihood_ratio_is_never_negative(seed):
    rng = np.random.default_rng(seed)
    for x in (rng.normal(size=300), sample_stable(rng, 1.5, 0.0, 2.0, 1.0, size=300)):
        result = lr_gaussian_vs_stable(x)
        assert result.statistic >= 0.0
        assert 0.0 <= result.p_chi2 <= 1.0


def test_likelihood_ratio_bootstrap_pvalue_is_a_probability():
    rng = np.random.default_rng(27)
    result = lr_gaussian_vs_stable(rng.normal(size=250), n_boot=4, rng=rng)
    assert 0.0 < result.p_boot <= 1.0
    assert math.isnan(lr_gaussian_vs_stable(rng.normal(size=100)).p_boot)
    with pytest.raises(ValueError):
        lr_gaussian_vs_stable(rng.normal(size=100), n_boot=4)


def test_gaussian_scale_convention_keeps_the_ratio_at_zero():
    x = np.random.default_rng(28).normal(0.0, 2.5, size=1000)
    fit = gaussian_fit(x)
    assert fit.gamma == pytest.approx(np.std(x) / math.sqrt(2.0), rel=1e-12)
    assert stable_nll(x, fit) < stable_nll(x, StableParams(2.0, 0.0, np.std(x), np.mean(x)))
    assert lr_gaussian_vs_stable(x).statistic < 6.0


def test_fixed_alpha_mle_holds_alpha_and_beats_the_quantile_fit():
    x = sample_stable(np.random.default_rng(51), 1.6, 0.0, 0.7, 0.2, size=1500)
    fit = fixed_alpha_mle_fit(x, 1.6)
    assert fit.alpha == 1.6 and fit.beta == 0.0
    assert stable_nll(x, fit) <= stable_nll(x, fixed_alpha_fit(x, 1.6))
    assert fit.gamma == pytest.approx(0.7, rel=0.06)
    assert fit.delta == pytest.approx(0.2, abs=0.06)
    with pytest.raises(ValueError):
        fixed_alpha_mle_fit(np.zeros(4), 1.6)


def test_ks_headline_fit_is_the_maximum_likelihood_fit():
    x = sample_stable(np.random.default_rng(52), 1.5, 0.0, 0.6, 0.0, size=1200)
    result = ks_test_stable(x, n_boot=0)
    quantile = mccullough_fit(x)
    assert result.params.as_tuple() == mle_fit(x).as_tuple()
    assert result.params.as_tuple() != quantile.as_tuple()
    assert stable_nll(x, result.params) < stable_nll(x, quantile)
    assert result.params.alpha == pytest.approx(1.5, abs=0.08)
    assert quantile.alpha == pytest.approx(1.5, abs=0.15)


def test_ks_with_a_fixed_alpha_fits_the_rest_by_likelihood():
    x = sample_stable(np.random.default_rng(53), 1.6, 0.0, 0.4, 0.0, size=400)
    result = ks_test_stable(x, alpha=1.6, n_boot=0)
    assert result.params.alpha == 1.6
    assert result.params.as_tuple() == fixed_alpha_mle_fit(x, 1.6).as_tuple()
    assert stable_nll(x, result.params) <= stable_nll(x, fixed_alpha_fit(x, 1.6))


def test_ks_result_records_which_estimator_did_what():
    """The printed procedure fits once and scores the resamples against that fit."""
    x = sample_stable(np.random.default_rng(54), 1.6, 0.0, 0.4, 0.0, size=400)
    default = ks_test_stable(x, n_boot=8, rng=np.random.default_rng(55))
    assert (default.point_estimator, default.bootstrap_estimator) == (MLE, NO_ESTIMATOR)
    assert default.refit is False

    fast = ks_test_stable(x, n_boot=8, rng=np.random.default_rng(55), point_fit=QUANTILE)
    assert fast.point_estimator == QUANTILE
    assert fast.params.as_tuple() == mccullough_fit(x).as_tuple()

    refitted = ks_test_stable(x, n_boot=8, rng=np.random.default_rng(55), refit=True)
    assert refitted.bootstrap_estimator == QUANTILE and refitted.refit is True

    assert ks_test_stable(x, n_boot=0).bootstrap_estimator == NO_ESTIMATOR
    with pytest.raises(ValueError):
        ks_test_stable(x, n_boot=0, point_fit="method-of-moments")


def test_ks_bootstrap_default_is_the_paper_s_ten_thousand():
    assert inspect.signature(ks_test_stable).parameters["n_boot"].default == 10_000
    assert Config().sampling.ks_bootstrap == 10_000


def test_holding_the_fit_fixed_raises_the_p_value_against_a_refit():
    """The direction of the printed procedure, measured rather than argued."""
    samples = [
        sample_stable(np.random.default_rng(2000 + s), 1.6, 0.0, 0.4, 0.0, size=400)
        for s in range(8)
    ]
    printed = [
        ks_test_stable(x, n_boot=60, rng=np.random.default_rng(7)).pvalue
        for x in samples
    ]
    refitted = [
        ks_test_stable(x, n_boot=60, rng=np.random.default_rng(7), refit=True).pvalue
        for x in samples
    ]
    assert np.mean(printed) == pytest.approx(0.76, abs=0.05)
    assert np.mean(refitted) == pytest.approx(0.57, abs=0.05)
    assert sum(a >= b for a, b in zip(printed, refitted, strict=True)) == 8
    assert "biased towards accepting heavy-tail consistency" in ESTIMATOR_NOTE


@pytest.mark.parametrize("seed", (11, 12, 13))
def test_likelihood_ratio_stays_non_negative_under_the_mle_headline_fit(seed):
    """Lambda >= 0 still holds now that the KS headline fit is the same MLE."""
    rng = np.random.default_rng(seed)
    for x in (
        rng.normal(0.0, 2.0, size=400),
        sample_stable(rng, 1.7, 0.0, 0.5, 0.0, size=400),
    ):
        headline = ks_test_stable(x, n_boot=0).params
        result = lr_gaussian_vs_stable(x)
        assert result.statistic >= 0.0
        assert result.p_chi2 <= 1.0
        nll_stable = stable_nll(x, gaussian_fit(x)) - result.statistic / 2.0
        assert stable_nll(x, headline) >= nll_stable - 1e-9


def test_boundary_note_states_both_the_reference_and_the_sign():
    assert "boundary" in BOUNDARY_NOTE and "under-rejects" in BOUNDARY_NOTE
    assert "non-negative" in BOUNDARY_NOTE


def _report(collection=None, n_boot=8):
    x = sample_radicality(np.random.default_rng(60), 1.6, 0.3, 200)
    return calibrate(
        x,
        Config(),
        np.random.default_rng(61),
        radicality=x,
        n_boot=n_boot,
        collection=collection,
    )


def test_calibration_notes_name_the_paper_s_tail_index():
    report = _report()
    assert PAPER_ALPHA_FIELD == "alpha_hat" and report.paper_alpha_field == "alpha_hat"
    joined = " ".join(report.notes)
    assert "Section 4.4" in joined
    assert "alpha_hat_radicality" in joined and "no counterpart in the paper" in joined
    summary = report.summary_lines()
    assert "the paper's Section 4.4 number" in summary[0] and "d_struct" in summary[0]
    assert "not in the paper" in summary[1] and "radicality" in summary[1]


def test_calibration_records_which_estimator_did_what():
    report = _report()
    assert report.ks_point_estimator == MLE
    assert report.ks_bootstrap_estimator == NO_ESTIMATOR
    assert report.ks_refit is False
    assert ESTIMATOR_NOTE in " ".join(report.notes)
    assert "point=mle bootstrap=none" in report.summary_lines()[2]


def test_calibration_reports_the_acceptance_rate_of_the_rejection_filter():
    report = _report(
        collection={"attempts": 300, "rejections": 120, "vacuous": 4, "filtered": 1}
    )
    assert report.rejection_filter is True
    assert report.n_proposals == 420 and report.n_vacuous == 4
    assert report.acceptance_rate == pytest.approx(300 / 420)
    joined = " ".join(report.notes)
    assert "rejection filter was applied" in joined and "0.7143" in joined
    assert "acceptance_rate=0.714" in report.summary_lines()[4]


def test_calibration_says_so_when_the_filter_was_not_applied():
    for collection in (None, {"attempts": 300, "rejections": 0, "filtered": 0}):
        report = _report(collection=collection)
        assert report.rejection_filter is False
        assert report.acceptance_rate is None and report.n_proposals == 0
        assert "rejection filter was NOT applied" in " ".join(report.notes)
        assert "NOT applied" in report.summary_lines()[4]


def test_calibration_report_round_trips_through_json(tmp_path):
    report = _report(
        collection={"attempts": 100, "rejections": 25, "exhausted": 0, "filtered": 1}
    )
    path = report.save(tmp_path / "calibration.json")
    loaded = CalibrationReport.load(path)
    assert loaded.acceptance_rate == pytest.approx(0.8)
    assert loaded.ks_point_estimator == MLE and loaded.paper_alpha_field == "alpha_hat"
    assert json.loads(path.read_text(encoding="utf-8"))["lr_p_boot"] is None


def test_an_older_artifact_without_the_new_fields_still_loads(tmp_path):
    fields = {
        "n_distances": 1000, "alpha_hat": 1.62, "alpha_ci": [1.51, 1.74],
        "alpha_target": 1.6, "k": 100, "ks_stat": 0.02, "ks_pvalue": 0.4,
        "ks_n_boot": 10000, "alpha_hat_radicality": 1.7, "radicality_ci": [1.5, 1.9],
        "n_radicality": 1000, "lr_statistic": 12.0, "lr_p_chi2": 0.002,
        "lr_p_boot": None,
    }
    path = tmp_path / "old.json"
    path.write_text(json.dumps(fields), encoding="utf-8")
    loaded = CalibrationReport.load(path)
    assert loaded.rejection_filter is False and loaded.acceptance_rate is None
    assert loaded.paper_alpha_field == PAPER_ALPHA_FIELD


def test_the_rejection_filter_really_runs_during_collection(synthetic, repo_root):
    """Entry 3c asks whether the filter really runs during collection."""
    from trope.calibrate import calibrate_dataset
    from trope.pipeline import Pipeline

    cfg = Config.load(repo_root / "configs" / "smoke.yaml")
    report, counts = calibrate_dataset(
        synthetic, Pipeline.build(cfg, problems=synthetic), cfg, n=32, seed=0, n_boot=8
    )
    assert counts["filtered"] == 1
    assert report.rejection_filter is True
    assert report.n_proposals >= counts["attempts"] > 0
    assert 0.0 < report.acceptance_rate <= 1.0
    assert report.acceptance_rate == pytest.approx(
        counts["attempts"] / (counts["attempts"] + counts["rejections"])
    )


def test_paired_wilcoxon_agrees_with_scipy():
    rng = np.random.default_rng(30)
    a, b = rng.normal(size=40), rng.normal(size=40)
    mine = paired_wilcoxon(a, b)
    theirs = sps.wilcoxon(a, b)
    assert mine.statistic == pytest.approx(theirs.statistic)
    assert mine.pvalue == pytest.approx(theirs.pvalue)
    assert mine.n == 40 and mine.n_nonzero == 40


def test_paired_wilcoxon_survives_all_zero_differences():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    result = paired_wilcoxon(a, a.copy())
    assert result.pvalue == 1.0 and result.statistic == 0.0
    assert result.n == 4 and result.n_nonzero == 0


def test_paired_wilcoxon_counts_the_pairs_that_moved():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([1.0, 1.0, 3.0, 2.0, 4.0])
    assert paired_wilcoxon(a, b).n_nonzero == 3


def test_wilcoxon_cannot_beat_the_paper_s_floor_at_n_six():
    a = np.array([2.0, 4.0, 6.0, 8.0, 10.0, 12.0])
    b = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert paired_wilcoxon(a, b).pvalue == pytest.approx(2.0 * 2.0**-6)


def test_paired_wilcoxon_rejects_mismatched_inputs():
    with pytest.raises(ValueError):
        paired_wilcoxon(np.zeros(3), np.zeros(4))


def test_bootstrap_ci_covers_the_true_mean_at_the_nominal_rate():
    rng = np.random.default_rng(31)
    covered = 0
    reps = 300
    for _ in range(reps):
        _, lo, hi = bootstrap_ci(rng.normal(0.0, 1.0, size=40), n_boot=400, rng=rng)
        covered += lo <= 0.0 <= hi
    assert 0.88 <= covered / reps <= 0.99


def test_bootstrap_ci_returns_the_point_estimate_and_brackets_it():
    rng = np.random.default_rng(32)
    x = rng.normal(5.0, 1.0, size=200)
    point, lo, hi = bootstrap_ci(x, n_boot=2000, rng=rng)
    assert point == pytest.approx(float(np.mean(x)))
    assert lo < point < hi
    assert hi - lo == pytest.approx(2 * 1.96 / math.sqrt(200), rel=0.2)


def test_bootstrap_ci_accepts_a_statistic_without_an_axis_argument():
    rng = np.random.default_rng(33)
    x = rng.normal(size=60)
    point, lo, hi = bootstrap_ci(x, statistic=lambda v: float(np.median(v)), n_boot=300, rng=rng)
    assert point == pytest.approx(float(np.median(x)))
    assert lo < point < hi


def test_bootstrap_requires_an_explicit_generator():
    with pytest.raises(ValueError):
        bootstrap_ci(np.arange(10.0), n_boot=10)


def test_paired_bootstrap_diff_is_the_bootstrap_of_the_difference():
    a = np.arange(20.0)
    b = np.arange(20.0) * 0.5
    first = paired_bootstrap_diff(a, b, n_boot=500, rng=np.random.default_rng(34))
    second = bootstrap_ci(a - b, n_boot=500, rng=np.random.default_rng(34))
    assert first == second


def test_spearman_is_invariant_to_a_monotone_transform():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert spearman(x, np.exp(x)) == pytest.approx(1.0)
    assert spearman(x, -x) == pytest.approx(-1.0)
    rng = np.random.default_rng(35)
    a, b = rng.normal(size=50), rng.normal(size=50)
    assert spearman(a, b) == pytest.approx(sps.spearmanr(a, b).statistic)


def test_holm_bonferroni_known_answer():
    adjusted = holm_bonferroni([0.01, 0.02, 0.03])
    assert np.allclose(adjusted, [0.03, 0.04, 0.04])


def test_holm_bonferroni_is_monotone_and_conservative():
    rng = np.random.default_rng(36)
    p = rng.uniform(size=25)
    adjusted = holm_bonferroni(p)
    order = np.argsort(p)
    assert np.all(np.diff(adjusted[order]) >= -1e-15)
    assert np.all(adjusted >= p - 1e-15)
    assert np.all(adjusted <= 1.0)
    assert holm_bonferroni([0.4])[0] == pytest.approx(0.4)


def test_holm_bonferroni_rejects_values_outside_the_unit_interval():
    with pytest.raises(ValueError):
        holm_bonferroni([0.5, 1.5])


def test_hill_bias_on_stable_data_is_upward_and_shrinks_with_n() -> None:
    """Calibration reports alpha_hat well above alpha* and that is expected."""
    from trope.sampling.stable import sample_radicality

    alpha = 1.6
    means = []
    for n in (1000, 10000):
        estimates = [
            hill_estimate(sample_radicality(np.random.default_rng(s), alpha, 0.3, n)).alpha
            for s in range(12)
        ]
        means.append(float(np.mean(estimates)))

    assert means[0] > alpha, "Hill is biased upward on stable data"
    assert means[1] < means[0], "the bias must shrink as the sample grows"
    assert alpha < means[1] < means[0] < 2.6
