"""Read run artifacts under ``runs/`` into tidy frames."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from trope.runlog import find_runs, read_trace

SEED_DIR = re.compile(r"^seed(\d+)$")

BENCHMARK_LAYOUT: tuple[tuple[str, str, str], ...] = (
    ("math500", "MATH", "Math"),
    ("aime", "AIME", "Math"),
    ("usamo", "USAMO", "Math"),
    ("livecodebench", "LCB", "Code"),
    ("humaneval_plus", "HE+", "Code"),
    ("noveltybench", "NB", "Creativity"),
    ("creativityprism", "CP", "Creativity"),
    ("uot", "UoT", "Creativity"),
    ("llmsrbench", "SR", "Discovery"),
    ("researchbench", "RB", "Discovery"),
)

FAMILIES: tuple[str, ...] = ("Math", "Code", "Creativity", "Discovery")

_LABEL = {key: label for key, label, _ in BENCHMARK_LAYOUT}
_FAMILY = {key: family for key, _, family in BENCHMARK_LAYOUT}


def benchmark_label(key: str) -> str:
    return _LABEL.get(key, key)


def benchmark_family(key: str) -> str:
    """Paper family group of a benchmark, or "Other" for one not in the main results table (`tab:main`)."""
    return _FAMILY.get(key, "Other")


def ordered_benchmarks(present: Sequence[str]) -> list[str]:
    """Benchmarks in the paper's column order, unknown ones appended."""
    have = set(present)
    ordered = [key for key, _, _ in BENCHMARK_LAYOUT if key in have]
    return ordered + sorted(have - set(ordered))


class MissingRuns(RuntimeError):
    """Raised when the artifacts a table or figure needs are not on disk."""


def missing(what: str, script: str, root: str | Path) -> MissingRuns:
    return MissingRuns(
        f"no run artifacts for {what} under {Path(root)}. "
        f"Produce them with {script} (see README.md), then re-run this "
        f"builder. This repository ships no precomputed results."
    )


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MissingRuns(f"{path} is not valid JSON: {exc}") from exc


@dataclass(slots=True)
class RunRecord:
    path: Path
    manifest: dict[str, Any]
    summary: dict[str, Any]
    ledger: dict[str, Any]
    results: list[dict[str, Any]]

    @classmethod
    def read(cls, path: str | Path) -> RunRecord:
        path = Path(path)
        manifest = _read_json(path / "manifest.json", {})
        if not manifest:
            raise MissingRuns(f"{path} has no readable manifest.json")
        return cls(
            path=path,
            manifest=manifest,
            summary=_read_json(path / "summary.json", {}),
            ledger=_read_json(path / "ledger.json", {}),
            results=_read_json(path / "results.json", []),
        )

    @property
    def config(self) -> dict[str, Any]:
        return self.manifest.get("config") or {}

    @property
    def arm(self) -> str:
        return str(self.manifest.get("baseline") or "trope")

    @property
    def benchmark(self) -> str:
        run = self.config.get("run") or {}
        return str(run.get("benchmark") or self.manifest.get("dataset") or "unknown")

    @property
    def seed(self) -> int:
        seed = self.manifest.get("seed")
        if seed is None:
            seed = (self.config.get("run") or {}).get("seed")
        if seed is None:
            match = SEED_DIR.match(self.path.name)
            seed = match.group(1) if match else -1
        return int(seed)

    @property
    def variant(self) -> str:
        """Configuration name: the directory the launch script named the run."""
        if SEED_DIR.match(self.path.name) and self.path.parent != self.path:
            return self.path.parent.name
        return self.path.name

    @property
    def group(self) -> str:
        """Directory above the variant: the benchmark, or the sweep name."""
        parts = self.path.parts
        depth = 2 if SEED_DIR.match(self.path.name) else 1
        return parts[-depth - 1] if len(parts) > depth else ""

    @property
    def budget(self) -> int | None:
        budget = (self.config.get("run") or {}).get("budget")
        return None if budget is None else int(budget)

    @property
    def backend(self) -> str:
        return str(self.manifest.get("backend") or "")

    @property
    def models(self) -> dict[str, str]:
        return dict(self.manifest.get("models") or {})

    @property
    def n_problems(self) -> int:
        for source in (self.manifest.get("n_problems"), self.summary.get("n_problems")):
            if source:
                return int(source)
        rows = self.rows()
        return len(rows)

    def calls(self, role: str) -> int | None:
        calls = (self.ledger.get("calls") or {}).get(role)
        return None if calls is None else int(calls)

    def tokens(self, role: str) -> int | None:
        tokens = (self.ledger.get("tokens") or {}).get(role)
        return None if tokens is None else int(tokens)

    def trace(self) -> Iterator[dict[str, Any]]:
        path = self.path / "trace.jsonl"
        if not path.exists():
            return iter(())
        return read_trace(path)

    def rows(self) -> list[dict[str, Any]]:
        """One row per problem, from results.json or from the baseline trace."""
        if self.results:
            return [_trope_row(r) for r in self.results]
        rows: list[dict[str, Any]] = []
        for record in self.trace():
            if "iteration" in record or "verified" not in record:
                continue
            rows.append(
                {
                    "problem_id": str(record.get("problem_id", "")),
                    "score": float(bool(record.get("verified"))),
                    "coverage": None,
                    "generator_calls": record.get("generator_calls"),
                    "wall_seconds": None,
                }
            )
        return rows

    def archive_entries(self) -> dict[tuple[str, int], dict[str, Any]]:
        """Archive candidates keyed by (problem, iteration), when recorded."""
        out: dict[tuple[str, int], dict[str, Any]] = {}
        for result in self.results:
            pid = str(result.get("problem_id", ""))
            archive = result.get("archive") or {}
            entries = archive.get("entries") if isinstance(archive, dict) else None
            if entries is None and isinstance(archive, list):
                entries = archive
            for entry in entries or []:
                if not isinstance(entry, dict) or "iteration" not in entry:
                    continue
                out[(pid, int(entry["iteration"]))] = entry
        return out


def _trope_row(result: dict[str, Any]) -> dict[str, Any]:
    stats = result.get("stats") or {}
    return {
        "problem_id": str(result.get("problem_id", "")),
        "score": float(bool(result.get("solved"))),
        "coverage": result.get("coverage"),
        "generator_calls": stats.get("generator_calls"),
        "wall_seconds": stats.get("wall_seconds"),
    }


class RunSet:
    """Every run under a root, with the joins the table builders need."""

    def __init__(self, root: str | Path, runs: Sequence[RunRecord] | None = None) -> None:
        self.root = Path(root)
        if runs is None:
            runs = [RunRecord.read(p) for p in find_runs(self.root)]
        self.runs: list[RunRecord] = list(runs)

    def __len__(self) -> int:
        return len(self.runs)

    def __bool__(self) -> bool:
        return bool(self.runs)

    def arms(self) -> tuple[str, ...]:
        return tuple(sorted({r.arm for r in self.runs}))

    def benchmarks(self) -> tuple[str, ...]:
        return tuple(ordered_benchmarks(sorted({r.benchmark for r in self.runs})))

    def variants(self) -> tuple[str, ...]:
        return tuple(sorted({r.variant for r in self.runs}))

    def groups(self) -> tuple[str, ...]:
        return tuple(sorted({r.group for r in self.runs}))

    def seeds(self) -> tuple[int, ...]:
        return tuple(sorted({r.seed for r in self.runs}))

    def select(self, **kwargs: Any) -> RunSet:
        """Subset by any RunRecord property, e.g. ``select(arm="trope")``."""

        def keep(run: RunRecord) -> bool:
            for key, want in kwargs.items():
                value = getattr(run, key)
                if isinstance(want, list | tuple | set | frozenset):
                    if value not in want:
                        return False
                elif value != want:
                    return False
            return True

        return RunSet(self.root, [r for r in self.runs if keep(r)])

    def require(self, what: str, script: str) -> RunSet:
        if not self.runs:
            raise missing(what, script, self.root)
        return self

    def frame(self) -> pd.DataFrame:
        """One row per (arm, benchmark, seed, problem)."""
        rows: list[dict[str, Any]] = []
        for run in self.runs:
            base = {
                "arm": run.arm,
                "variant": run.variant,
                "group": run.group,
                "benchmark": run.benchmark,
                "family": benchmark_family(run.benchmark),
                "seed": run.seed,
                "budget": run.budget,
                "run_dir": str(run.path),
            }
            for row in run.rows():
                rows.append(base | row)
        columns = [
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
        return pd.DataFrame(rows, columns=columns)

    def traces(self, arm: str | None = None) -> Iterator[dict[str, Any]]:
        """Trace records with arm/benchmark/seed/variant attached."""
        for run in self.runs:
            if arm is not None and run.arm != arm:
                continue
            tags = {
                "arm": run.arm,
                "variant": run.variant,
                "benchmark": run.benchmark,
                "family": benchmark_family(run.benchmark),
                "seed": run.seed,
                "run_dir": str(run.path),
            }
            for record in run.trace():
                if "iteration" not in record:
                    continue
                yield record | tags

    def budget_check(self, tolerance: float = 0.02) -> list[str]:
        """Complaints about arms that did not receive a matched budget."""
        complaints: list[str] = []
        per_arm: dict[tuple[str, str], list[tuple[RunRecord, float]]] = {}
        for run in self.runs:
            calls = run.calls("generator")
            if calls is None:
                complaints.append(
                    f"{run.path}: ledger.json records no generator calls; "
                    f"the matched-budget comparison cannot be checked."
                )
                continue
            n = run.n_problems
            if not n:
                complaints.append(f"{run.path}: no problems recorded, cannot normalise.")
                continue
            per_arm.setdefault((run.benchmark, run.arm), []).append((run, calls / n))

        by_benchmark: dict[str, dict[str, float]] = {}
        for (benchmark, arm), entries in per_arm.items():
            by_benchmark.setdefault(benchmark, {})[arm] = sum(
                v for _, v in entries
            ) / len(entries)

        for benchmark, arms in sorted(by_benchmark.items()):
            if len(arms) < 2:
                continue
            top = max(arms.values())
            floor = min(arms.values())
            if top <= 0 or (top - floor) <= tolerance * top:
                continue
            detail = ", ".join(f"{a}={v:.2f}" for a, v in sorted(arms.items()))
            complaints.append(
                f"{benchmark}: generator calls per problem differ by "
                f"{100 * (top - floor) / top:.1f}% across arms "
                f"(tolerance {100 * tolerance:.1f}%): {detail}. "
                f"These arms are not on a matched budget and must not be "
                f"compared in one table."
            )
        return complaints

    def provenance(self) -> list[str]:
        """Run directories behind a table, grouped by configuration."""
        by_dir: dict[str, list[int]] = {}
        for run in self.runs:
            try:
                key = str(run.path.relative_to(self.root))
            except ValueError:
                key = str(run.path)
            if SEED_DIR.match(run.path.name):
                key = str(Path(key).parent)
            by_dir.setdefault(key, []).append(run.seed)
        return [
            f"{key} (seeds {','.join(str(s) for s in sorted(set(seeds)))})"
            for key, seeds in sorted(by_dir.items())
        ]
