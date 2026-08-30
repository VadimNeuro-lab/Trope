"""Tests for the analysis package."""

from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

import numpy as np
import pytest

from trope.analysis import audit, equalcompute, figures, tables
from trope.analysis.loader import BENCHMARK_LAYOUT, MissingRuns, RunSet

BENCHMARKS = ("math500", "livecodebench", "uot", "llmsrbench")
ARMS = ("trope", "self_consistency", "greedy")
OPERATORS = (
    ("temperature_scaling", "token"),
    ("assumption_violation", "mutation"),
    ("categorical_import", "crossover"),
)
DEFAULT_REFERENCE = "Qwen/Qwen2.5-3B-Instruct"


def _config(benchmark: str, seed: int, budget: int, reference: str) -> dict:
    return {
        "run": {
            "benchmark": benchmark,
            "budget": budget,
            "seed": seed,
            "backend": "mock",
            "backend_model": "Qwen/Qwen2.5-7B-Instruct",
            "reference_model": reference,
            "out_dir": "runs",
        },
        "controller": {
            "lambda_min": 0.05,
            "lambda_max": 0.40,
            "setpoint": 0.22,
            "window": 2,
            "refresh_every": 1,
        },
        "sampling": {"alpha": 1.6, "gamma_init": 0.3, "hill_exponent": 2.0 / 3.0},
        "operators": {"levels": ["token", "mutation", "crossover"]},
        "novelty": {"threshold": 0.5},
    }


def _rng(*parts: object) -> np.random.Generator:
    entropy = [zlib.crc32(str(p).encode("utf-8")) for p in parts]
    return np.random.default_rng(entropy)


def _score(arm: str, benchmark: str, seed: int, index: int) -> bool:
    rate = {"trope": 0.75, "self_consistency": 0.5, "greedy": 0.35}.get(arm, 0.6)
    return bool(_rng(arm, benchmark, seed, index).random() < rate)


def _ledger(n_problems: int, budget: int, *, arm: str, factor: float = 1.0) -> dict:
    calls = {"generator": int(budget * n_problems * factor)}
    tokens = {"generator": int(120 * budget * n_problems * factor)}
    if arm == "trope":
        calls |= {"parser": n_problems, "reference": (budget + 1) * n_problems}
        tokens |= {"parser": 400 * n_problems, "reference": 250 * (budget + 1) * n_problems}
    return {"calls": calls, "tokens": tokens, "note": "matched budget counts generator"}


def _trace_records(benchmark: str, seed: int, n_problems: int, budget: int) -> list[dict]:
    records = []
    for index in range(n_problems):
        problem_id = f"{benchmark}-p{index}"
        rng = _rng("trace", benchmark, seed, index)
        for t in range(1, budget + 1):
            name, level = OPERATORS[t % len(OPERATORS)]
            records.append(
                {
                    "iteration": t,
                    "problem_id": problem_id,
                    "operator": name,
                    "level": level,
                    "z": float(rng.standard_normal()),
                    "radicality": float(abs(rng.standard_cauchy()) * 0.3) + 0.01,
                    "gamma": 0.3 + 0.01 * t,
                    "rejections": int(rng.integers(0, 3)),
                    "rejected_exhausted": False,
                    "masked": [],
                    "well_formed": True,
                    "wf_reason": "",
                    "changed": True,
                    "detail": f"edit {t}",
                    "d_struct": float(rng.random()),
                    "novelty": float(rng.random() * 2),
                    "verdict": float(rng.random()),
                    "verified": bool(rng.random() < 0.4),
                    "accepted": bool(rng.random() < 0.6),
                    "descriptor": [t % 3, t % 4],
                    "advantage": float(rng.standard_normal()),
                    "lambda_struct": 0.05 + 0.4 * float(rng.random()),
                    "generator_calls": t - 1,
                    "rep_fingerprint": f"fp{t:03d}",
                    "_exact": {},
                }
            )
    return records


def write_run(
    path: Path,
    *,
    benchmark: str,
    seed: int,
    arm: str = "trope",
    n_problems: int = 10,
    budget: int = 8,
    reference: str = DEFAULT_REFERENCE,
    ledger_factor: float = 1.0,
) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "config": _config(benchmark, seed, budget, reference),
        "backend": "mock",
        "models": {"backbone": "Qwen/Qwen2.5-7B-Instruct", "reference": reference},
        "model_params": {"backbone": 7.6e9, "reference": 3.1e9},
        "git_revision": "0" * 40,
        "python": "3.13.0",
        "platform": "test",
        "argv": [],
        "seed": seed,
        "dataset": benchmark,
        "n_problems": n_problems,
    }
    if arm != "trope":
        manifest["baseline"] = arm
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    scores = [_score(arm, benchmark, seed, i) for i in range(n_problems)]
    (path / "summary.json").write_text(
        json.dumps(
            {
                "n_problems": n_problems,
                "solved": sum(scores),
                "solve_rate": sum(scores) / n_problems,
                "mean_coverage": 0.4 + 0.01 * seed,
                "mean_novelty": 0.7 + 0.01 * seed,
                "generator_calls": budget * n_problems,
            }
        ),
        encoding="utf-8",
    )
    (path / "ledger.json").write_text(
        json.dumps(_ledger(n_problems, budget, arm=arm, factor=ledger_factor)),
        encoding="utf-8",
    )

    if arm == "trope":
        results = []
        for index, solved in enumerate(scores):
            problem_id = f"{benchmark}-p{index}"
            results.append(
                {
                    "problem_id": problem_id,
                    "solved": solved,
                    "coverage": 0.4 + 0.02 * index,
                    "stats": {
                        "generator_calls": budget,
                        "wall_seconds": 1.5 + 0.1 * index,
                        "iterations": budget,
                        "usage": {name: budget // len(OPERATORS) for name, _ in OPERATORS},
                    },
                    "parse": {
                        "failed": False,
                        "attempts": 1,
                        "representation": {"frame": "algebra", "entities": []},
                    },
                    "archive": {
                        "entries": [
                            {
                                "iteration": 2,
                                "text": f"candidate for {problem_id}",
                                "operator": "assumption_violation",
                                "novelty": 1.4,
                                "verdict": 1.0,
                            }
                        ]
                    },
                }
            )
        (path / "results.json").write_text(json.dumps(results), encoding="utf-8")
        records = _trace_records(benchmark, seed, n_problems, budget)
    else:
        records = [
            {
                "problem_id": f"{benchmark}-p{i}",
                "verified": scores[i],
                "generator_calls": budget,
                "_exact": {},
            }
            for i in range(n_problems)
        ]
    with (path / "trace.jsonl").open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    return path


@pytest.fixture(scope="module")
def main_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("runs") / "main"
    for benchmark in BENCHMARKS:
        for arm in ARMS:
            for seed in (1, 2):
                write_run(
                    root / benchmark / arm / f"seed{seed}",
                    benchmark=benchmark,
                    seed=seed,
                    arm=arm,
                )
    (root / "calibration.json").write_text(
        json.dumps(
            {
                "n_distances": 1000,
                "alpha_hat": 1.62,
                "alpha_ci": [1.51, 1.74],
                "alpha_target": 1.6,
                "k": 100,
                "hill_plot_k": list(range(20, 200, 10)),
                "hill_plot_alpha": [1.5 + 0.01 * i for i in range(18)],
            }
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture(scope="module")
def ablation_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("runs") / "ablations"
    variants = [
        "tok",
        "mut",
        "cross",
        "tok_mut",
        "tok_cross",
        "mut_cross",
        "full",
        "no_parser",
        "no_heavytail",
        "no_novelty",
        "no_divctrl",
        "no_rejection",
        "no_mapelites",
        "loo_temperature_scaling",
        "loo_assumption_violation",
        "loo_categorical_import",
        "only_assumption_violation",
        "minus_assumption_pair",
    ]
    for benchmark in ("math500", "aime", "uot", "llmsrbench"):
        for variant in variants:
            write_run(
                root / benchmark / variant / "seed1",
                benchmark=benchmark,
                seed=1,
                n_problems=4,
                budget=4,
            )
    return root


@pytest.fixture(scope="module")
def sensitivity_root(tmp_path_factory) -> Path:
    """As scripts/run_sensitivity.sh lays it out: one sweep root per benchmark."""
    root = tmp_path_factory.mktemp("runs") / "sensitivity"
    for benchmark in ("math500", "uot"):
        for alpha in ("1.4", "1.6"):
            write_run(
                root / benchmark / "alpha" / alpha / "seed1",
                benchmark=benchmark,
                seed=1,
                n_problems=4,
                budget=4,
            )
        for reference in (DEFAULT_REFERENCE, "meta-llama/Llama-3.2-3B-Instruct"):
            write_run(
                root / benchmark / "lmref" / reference.replace("/", "_") / "seed1",
                benchmark=benchmark,
                seed=1,
                n_problems=4,
                budget=4,
                reference=reference,
            )
    for k in (32, 64):
        write_run(
            root / "math500" / "budget" / str(k) / "seed1",
            benchmark="math500",
            seed=1,
            n_problems=4,
            budget=k // 8,
        )
    return root


MULTICOLUMN = re.compile(r"\\multicolumn\{(\d+)\}")


def _row_width(row: str) -> int:
    return sum(
        int(MULTICOLUMN.search(cell).group(1)) if MULTICOLUMN.search(cell) else 1
        for cell in row.split("&")
    )


def assert_valid_tabular(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(r"\begin{tabular}") == text.count(r"\end{tabular}") == 1
    assert text.count(r"\toprule") == text.count(r"\bottomrule") == 1
    assert text.splitlines()[0].startswith("%"), "missing provenance comment"

    colspec = re.search(r"\\begin\{tabular\}\{(.+)\}", text).group(1)
    expected = len(re.findall(r"[lcr]", re.sub(r"@\{[^}]*\}", "", colspec)))
    widths = {
        _row_width(line.rstrip()[:-2])
        for line in text.splitlines()
        if line.rstrip().endswith(r"\\")
    }
    assert widths, f"{path} has no data rows"
    assert widths == {expected}, f"{path}: rows {sorted(widths)} against colspec {expected}"


def test_paper_table_layout_is_ten_benchmarks_in_four_families():
    assert len(BENCHMARK_LAYOUT) == 10
    spans = tables._spans([key for key, _, _ in BENCHMARK_LAYOUT])
    assert spans == [("Math", 3), ("Code", 2), ("Creativity", 3), ("Discovery", 2)]


def test_runset_discovers_runs_and_builds_a_frame(main_root):
    runs = RunSet(main_root)
    assert len(runs) == len(BENCHMARKS) * len(ARMS) * 2
    assert set(runs.arms()) == set(ARMS)
    assert runs.seeds() == (1, 2)

    frame = runs.frame()
    assert len(frame) == len(runs) * 10
    assert list(frame.columns) == [
        "arm",
        "variant",
        "group",
        "benchmark",
        "family",
        "seed",
        "problem_id",
        "score",
        "coverage",
        "generator_calls",
        "wall_seconds",
        "budget",
        "run_dir",
    ]
    assert set(frame["family"]) == {"Math", "Code", "Creativity", "Discovery"}
    assert set(frame["variant"]) == set(ARMS)
    assert set(frame["group"]) == set(BENCHMARKS)


def test_traces_carry_run_tags(main_root):
    records = list(RunSet(main_root).traces(arm="trope"))
    assert records
    assert all({"arm", "benchmark", "seed", "iteration"} <= set(r) for r in records)
    assert {r["arm"] for r in records} == {"trope"}


def test_budget_check_is_quiet_on_matched_runs(main_root):
    assert RunSet(main_root).budget_check(0.02) == []


def test_budget_check_flags_mismatch_and_tables_refuse(tmp_path):
    root = tmp_path / "runs"
    write_run(root / "math500" / "trope" / "seed1", benchmark="math500", seed=1)
    write_run(
        root / "math500" / "greedy" / "seed1",
        benchmark="math500",
        seed=1,
        arm="greedy",
        ledger_factor=2.0,
    )
    complaints = RunSet(root).budget_check(0.02)
    assert len(complaints) == 1
    assert "matched budget" in complaints[0]
    assert "greedy" in complaints[0] and "trope" in complaints[0]

    with pytest.raises(tables.BudgetMismatch) as excinfo:
        tables.build_tables(root, tmp_path / "out", which="main")
    assert "refusing to build a comparison table" in str(excinfo.value)
    assert not (tmp_path / "out" / "main.tex").exists()


def test_budget_check_tolerance_admits_small_drift(tmp_path):
    root = tmp_path / "runs"
    write_run(root / "math500" / "trope" / "seed1", benchmark="math500", seed=1)
    write_run(
        root / "math500" / "greedy" / "seed1",
        benchmark="math500",
        seed=1,
        arm="greedy",
        ledger_factor=0.99,
    )
    assert RunSet(root).budget_check(0.02) == []
    assert RunSet(root).budget_check(0.001)


def test_missing_artifacts_name_the_script(tmp_path):
    with pytest.raises(MissingRuns) as excinfo:
        tables.build_tables(tmp_path / "empty", tmp_path / "out")
    assert "README.md" in str(excinfo.value)
    assert "ships no precomputed results" in str(excinfo.value)


def test_missing_ablations_name_run_ablations(main_root, tmp_path):
    with pytest.raises(MissingRuns) as excinfo:
        tables.build_tables(main_root, tmp_path / "out", which="loo")
    assert "scripts/run_ablations.sh" in str(excinfo.value)


def test_main_and_fullse_tables(main_root, tmp_path):
    out = tmp_path / "tables"
    written = tables.build_tables(main_root, out, which="main,fullse")
    assert {p.name for p in written} == {
        "main.csv",
        "main.tex",
        "fullse.csv",
        "fullse.tex",
    }
    for path in written:
        assert path.stat().st_size > 0
        if path.suffix == ".tex":
            assert_valid_tabular(path)

    import pandas as pd

    frame = pd.read_csv(out / "main.csv")
    assert set(frame["benchmark"]) == set(BENCHMARKS)
    summary = frame[frame["row_type"] == "summary"]
    assert set(summary["row"]) == {"strongest_baseline"}
    assert set(summary["n_paired"]) == {10}

    text = (out / "main.tex").read_text(encoding="utf-8")
    assert r"\TROPE{} (ours)" in text
    assert "Strongest baseline" in text and "$p$ (Wilcoxon)" in text
    assert "seeds (n=2): 1,2" in text
    assert f"{Path('math500') / 'trope'} (seeds 1,2)" in text


def test_ablation_family_tables(ablation_root, tmp_path):
    out = tmp_path / "tables"
    written = tables.build_tables(ablation_root, out, which="ablations")
    names = {p.name for p in written}
    for stem in ("decomposition", "ablation", "component", "loo", "pairdiag"):
        assert f"{stem}.csv" in names and f"{stem}.tex" in names
        assert_valid_tabular(out / f"{stem}.tex")

    loo = (out / "loo.tex").read_text(encoding="utf-8")
    assert "Removed operator" in loo
    assert "Assumption violation" in loo


def test_budget_table_uses_baselines_when_they_are_swept(tmp_path):
    root = tmp_path / "runs"
    for k in (16, 32, 64):
        for seed in (1, 2):
            write_run(
                root / "math500" / "budget" / str(k) / f"seed{seed}",
                benchmark="math500",
                seed=seed,
                n_problems=6,
                budget=max(2, k // 8),
            )
        write_run(
            root / "math500" / "budget" / str(k),
            benchmark="math500",
            seed=1,
            arm="self_consistency",
            n_problems=6,
            budget=max(2, k // 8),
        )
    tables.build_tables(root, tmp_path / "tables", which="budget")
    assert_valid_tabular(tmp_path / "tables" / "budget.tex")

    import pandas as pd

    frame = pd.read_csv(tmp_path / "tables" / "budget.csv")
    assert frame["best_baseline"].notna().all()
    assert set(frame["best_baseline_arm"]) == {"self_consistency"}


def test_sensitivity_tables(sensitivity_root, tmp_path):
    out = tmp_path / "tables"
    written = tables.build_tables(sensitivity_root, out, which="sensitivity")
    names = {p.name for p in written}
    for stem in ("alpha", "crossfamily", "lmrefsize", "budget"):
        assert f"{stem}.tex" in names
        assert_valid_tabular(out / f"{stem}.tex")
    budget = (out / "budget.tex").read_text(encoding="utf-8")
    assert "Best baseline" in budget
    assert "column is empty" in budget

    import pandas as pd

    alpha = pd.read_csv(out / "alpha.csv")
    assert set(alpha["benchmark"]) == {"math500", "uot"}
    assert set(alpha["alpha"]) == {1.4, 1.6}
    cross = pd.read_csv(out / "crossfamily.csv")
    default = DEFAULT_REFERENCE.replace("/", "_")
    assert default in set(cross["reference_lm"])
    assert (
        f"default reference LM: {default}"
        in (out / "crossfamily.tex").read_text(encoding="utf-8")
    )


def test_trace_band_cost_usage_tables(main_root, tmp_path):
    out = tmp_path / "tables"
    written = tables.build_tables(
        main_root, out, which="trace,band,cost,usage,equalcompute"
    )
    names = {p.name for p in written}
    for stem in ("trace", "band", "cost", "overhead", "usage", "equalcompute"):
        assert f"{stem}.tex" in names, stem
        assert_valid_tabular(out / f"{stem}.tex")

    import pandas as pd

    usage = pd.read_csv(out / "usage.csv")
    assert set(usage["family"]) == {"Math", "Code", "Creativity", "Discovery"}
    shares = usage[["token_pct", "mutation_pct", "crossover_pct"]].sum(axis=1)
    assert np.allclose(shares, 100.0)

    band = pd.read_csv(out / "band.csv")
    assert "all" in set(band["family"])
    assert band["steady_occupancy_pct"].between(0, 100).all()

    cost = pd.read_csv(out / "cost.csv")
    stages = set(cost[cost["row"] == "trope"]["stage"].dropna())
    assert stages == {"parser", "generation", "novelty", "distance"}
    assert cost["gpu_hours_per_100"].isna().all()


def test_commute_table_reads_the_probe_json(main_root, tmp_path):
    (main_root / "commutativity.json").write_text(
        json.dumps(
            {
                "seed": 1,
                "n_representations": 12,
                "rates": {"mut-mut": 72.0, "mut-cross": 41.0, "cross-cross": 23.0},
                "counts": {"mut-mut": 100, "mut-cross": 120, "cross-cross": 60},
                "token": {"n_pairs": 40},
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "tables"
    tables.build_tables(main_root, out, which="commute")
    assert_valid_tabular(out / "commute.tex")
    text = (out / "commute.tex").read_text(encoding="utf-8")
    assert r"mut$\circ$mut" in text
    assert "Token pairs" in text
    (main_root / "commutativity.json").unlink()


def test_build_all_skips_what_is_absent_but_still_emits(main_root, tmp_path):
    written = tables.build_tables(main_root, tmp_path / "tables", which="all")
    stems = {p.stem for p in written}
    assert {"main", "fullse", "cost", "usage", "band", "trace"} <= stems
    assert "decomposition" not in stems


def test_figures_build_headless(main_root, sensitivity_root, tmp_path):
    written = figures.build_figures(main_root, tmp_path / "figures")
    stems = {p.stem for p in written}
    assert {"hill_plot", "operator_usage", "radicality_hist", "controller_trace"} <= stems
    for path in written:
        assert path.stat().st_size > 0
    for stem in stems:
        assert (tmp_path / "figures" / f"{stem}.pdf").read_bytes()[:4] == b"%PDF"

    curve = figures.build_figures(sensitivity_root, tmp_path / "figures2")
    assert any(p.stem == "budget_curve" for p in curve)


def test_figures_without_runs_raise(tmp_path):
    with pytest.raises(MissingRuns):
        figures.build_figures(tmp_path / "empty", tmp_path / "figures")


def test_equalcompute_prints_one_integer(main_root, capsys):
    code = equalcompute.main(
        ["--runs", str(main_root), "--benchmark", "math500", "--baseline", "greedy"]
    )
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.isdigit()
    assert int(out) > 8


def test_equalcompute_explains_its_arithmetic(main_root, capsys):
    equalcompute.main(
        [
            "--runs",
            str(main_root),
            "--benchmark",
            "math500",
            "--baseline",
            "greedy",
            "--explain",
        ]
    )
    captured = capsys.readouterr()
    assert captured.out.strip().isdigit()
    assert "eff_K = floor(" in captured.err
    assert "model_params" in captured.err


def test_equalcompute_fails_loudly_on_missing_runs(tmp_path, capsys):
    code = equalcompute.main(
        ["--runs", str(tmp_path / "nope"), "--benchmark", "aime", "--baseline", "uot"]
    )
    assert code == 2
    assert "run_main.sh" in capsys.readouterr().err


def test_cohens_kappa_known_answer():
    a = [1, 1, 1, 1, 0, 0, 0, 0, 1, 0]
    b = [1, 1, 1, 0, 0, 0, 0, 1, 1, 0]
    assert audit.cohens_kappa(a, b) == pytest.approx(0.6)


def test_cohens_kappa_perfect_and_chance():
    labels = ["y", "n", "y", "n", "y", "n"]
    assert audit.cohens_kappa(labels, labels) == pytest.approx(1.0)
    rng = np.random.default_rng(0)
    x = list(rng.integers(0, 2, size=4000))
    y = list(rng.integers(0, 2, size=4000))
    assert abs(audit.cohens_kappa(x, y)) < 0.05
    assert audit.cohens_kappa(["y"] * 5, ["y"] * 5) == 1.0


def test_cohens_kappa_rejects_ragged_input():
    with pytest.raises(ValueError):
        audit.cohens_kappa([1, 2, 3], [1, 2])


def test_semantic_audit_sampler_is_stratified(main_root, tmp_path):
    import pandas as pd

    path = audit.sample_semantic_audit(main_root, tmp_path / "semantic.csv", n=240, seed=0)
    frame = pd.read_csv(path, keep_default_na=False)
    assert len(frame) == 240
    assert frame["stratum"].value_counts().to_dict() == {
        "Math": 60,
        "Code": 60,
        "Creativity": 60,
        "Discovery": 60,
    }
    for column in audit.SEMANTIC_ANNOTATIONS:
        assert column in frame.columns
        assert (frame[column] == "").all(), f"{column} must be left for the annotator"
    assert (frame["operator"] != "").all()
    assert (frame["candidate"] != "").any()
    assert audit.sample_semantic_audit(
        main_root, tmp_path / "again.csv", n=240, seed=0
    ).read_text(encoding="utf-8") == path.read_text(encoding="utf-8")


def test_semantic_audit_refuses_an_unbalanced_sample(main_root, tmp_path):
    with pytest.raises(MissingRuns) as excinfo:
        audit.sample_semantic_audit(main_root, tmp_path / "big.csv", n=4000)
    assert "per family" in str(excinfo.value)


def test_retrieval_audit_sampler_is_stratified(tmp_path):
    import pandas as pd

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for family in ("math_answer", "code", "creativity", "discovery"):
        with (corpus / f"{family}.jsonl").open("w", encoding="utf-8") as fh:
            for i in range(100):
                fh.write(
                    json.dumps(
                        {
                            "family": family,
                            "passage_id": f"{family}-{i}",
                            "text": f"passage {i} about {family}",
                            "source": "wikipedia",
                        }
                    )
                    + "\n"
                )
    path = audit.sample_retrieval_audit(corpus, tmp_path / "retrieval.csv", n=320, seed=0)
    frame = pd.read_csv(path, keep_default_na=False)
    assert len(frame) == 320
    assert set(frame["stratum"].value_counts()) == {80}
    for column in audit.RETRIEVAL_ANNOTATIONS:
        assert (frame[column] == "").all()


def test_retrieval_audit_without_a_corpus_says_so(tmp_path):
    with pytest.raises(MissingRuns) as excinfo:
        audit.sample_retrieval_audit(tmp_path / "nothing", tmp_path / "r.csv")
    assert "not written into the run directory" in str(excinfo.value)


def test_commutativity_rates_on_hand_built_representations():
    from trope.analysis.commutativity import PAIR_KINDS, commutativity_rates
    from trope.operators.base import catalog, load_resources
    from trope.types import Assumption, Entity, Goal, Relation, Representation

    def make(index: int) -> Representation:
        entities = tuple(
            Entity(id=f"e{i}", type=t, sort=s, label=f"{s} {i}")
            for i, (t, s) in enumerate(
                [("variable", "count"), ("parameter", "bound"), ("constant", "modulus")]
            )
        )
        return Representation(
            entities=entities,
            relations=(
                Relation("e0", "e1", "bounds"),
                Relation("e1", "e2", "depends_on"),
            ),
            assumptions=(
                Assumption(f"n is a positive integer below {index + 3}", load_bearing=True),
                Assumption("the modulus is prime"),
            ),
            goal=Goal(objective=f"count the solutions for case {index}"),
            frame="number-theory",
        )

    reps = [make(i) for i in range(6)]
    report = commutativity_rates(reps, catalog(), load_resources(), seed=3)

    assert set(report["rates"]) == set(PAIR_KINDS)
    assert report["n_representations"] == 6
    assert report["token"]["commute_rate_pct"] == 100.0
    assert report["token"]["operators"]
    for kind in PAIR_KINDS:
        rate = report["rates"][kind]
        assert rate is None or 0.0 <= rate <= 100.0
        assert report["agreements"][kind] <= report["counts"][kind]
    assert sum(report["counts"].values()) + report["skipped"]["noop_or_malformed"] == (
        6 * len([o for o in catalog() if o.kind != "token"]) * (len([o for o in catalog() if o.kind != "token"]) - 1)
    )


def test_commutativity_is_deterministic():
    from trope.analysis.commutativity import commutativity_rates
    from trope.operators.base import catalog, load_resources
    from trope.types import Assumption, Entity, Goal, Relation, Representation

    rep = Representation(
        entities=(Entity("e0", "variable", "count"), Entity("e1", "parameter", "bound")),
        relations=(Relation("e0", "e1", "bounds"),),
        assumptions=(Assumption("n is positive", load_bearing=True),),
        goal=Goal(objective="find n"),
        frame="number-theory",
    )
    resources = load_resources()
    first = commutativity_rates([rep, rep], catalog(), resources, seed=7)
    second = commutativity_rates([rep, rep], catalog(), resources, seed=7)
    assert first["rates"] == second["rates"]
    assert first["counts"] == second["counts"]


def test_expand_rejects_unknown_tables():
    assert tables.expand("sensitivity") == ["alpha", "lmref", "budget"]
    assert tables.expand("main,main") == ["main"]
    with pytest.raises(KeyError):
        tables.expand("nonsense")
