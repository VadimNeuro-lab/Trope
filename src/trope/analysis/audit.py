"""Sampling for the two human audits, and the agreement statistic."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from trope.analysis.loader import (
    FAMILIES,
    MissingRuns,
    RunRecord,
    RunSet,
    benchmark_family,
)

SEMANTIC_ANNOTATIONS = (
    "parse_faithful",
    "edit_interpretable",
    "solved_only_edited_task",
    "notes",
)
RETRIEVAL_ANNOTATIONS = (
    "topically_relevant",
    "generic_but_harmless",
    "misleading",
    "contains_gold_answer",
    "notes",
)

SEMANTIC_FIELDS = (
    "stratum",
    "run_dir",
    "benchmark",
    "seed",
    "problem_id",
    "iteration",
    "problem",
    "representation_parsed",
    "operator",
    "level",
    "rho",
    "representation_edited",
    "candidate",
    "verdict",
    "novelty",
    "accepted",
)
RETRIEVAL_FIELDS = ("stratum", "passage_id", "source", "problem_id", "passage")

_FAMILY_ALIASES = {
    "math_answer": "Math",
    "math_proof": "Math",
    "math": "Math",
    "code": "Code",
    "creativity": "Creativity",
    "discovery": "Discovery",
}


def _stratum(label: str) -> str:
    return _FAMILY_ALIASES.get(str(label).lower(), str(label))


def _first(mapping: Any, keys: Sequence[str]) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if mapping.get(key) not in (None, ""):
            return mapping[key]
    return None


def _render(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _semantic_rows(run: RunRecord) -> list[dict[str, Any]]:
    """One candidate row per generated trace step, enriched from results.json."""
    archive = run.archive_entries()
    parsed: dict[str, Any] = {}
    for result in run.results:
        parse = result.get("parse") or {}
        parsed[str(result.get("problem_id", ""))] = _first(
            parse, ("representation", "rep", "R")
        )

    rows = []
    for record in run.trace():
        if "iteration" not in record or record.get("verdict") is None:
            continue
        problem_id = str(record.get("problem_id", ""))
        entry = archive.get((problem_id, int(record["iteration"]))) or {}
        rows.append(
            {
                "stratum": benchmark_family(run.benchmark),
                "run_dir": str(run.path),
                "benchmark": run.benchmark,
                "seed": run.seed,
                "problem_id": problem_id,
                "iteration": record["iteration"],
                "problem": _render(_first(entry, ("problem", "problem_text"))),
                "representation_parsed": _render(parsed.get(problem_id)),
                "operator": record.get("operator"),
                "level": record.get("level"),
                "rho": record.get("radicality"),
                "representation_edited": _render(
                    _first(entry, ("representation", "rep"))
                    or record.get("rep_fingerprint")
                ),
                "candidate": _render(_first(entry, ("text", "answer", "candidate"))),
                "verdict": record.get("verdict"),
                "novelty": record.get("novelty"),
                "accepted": record.get("accepted"),
            }
        )
    return rows


def _stratified(
    rows: Sequence[dict[str, Any]], strata: Sequence[str], per_stratum: int, seed: int
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    pools: dict[str, list[dict[str, Any]]] = {s: [] for s in strata}
    for row in rows:
        if row["stratum"] in pools:
            pools[row["stratum"]].append(row)

    short = {s: len(p) for s, p in pools.items() if len(p) < per_stratum}
    if short:
        detail = ", ".join(f"{s}: {n}/{per_stratum}" for s, n in sorted(short.items()))
        raise MissingRuns(
            f"cannot draw a balanced sample: {detail}. The stratification the paper "
            f"describes needs {per_stratum} items per family; run the missing "
            f"benchmark families (see README.md) before sampling."
        )

    sample: list[dict[str, Any]] = []
    for stratum in strata:
        pool = sorted(pools[stratum], key=lambda r: (str(r.get("run_dir")), str(r)))
        picks = rng.choice(len(pool), size=per_stratum, replace=False)
        sample += [pool[int(i)] for i in sorted(picks)]
    return sample


def _write_sheet(
    path: str | Path,
    rows: Iterable[dict[str, Any]],
    fields: Sequence[str],
    annotations: Sequence[str],
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[*fields, *annotations])
        writer.writeheader()
        for row in rows:
            writer.writerow({**{a: "" for a in annotations}, **row})
    return path


def sample_semantic_audit(
    runs_root: str | Path, out_csv: str | Path, n: int = 240, seed: int = 0
) -> Path:
    """Draw the parser--edit pairs of the semantic audit (`tab:semaudit`), n/4 per family."""
    runs = RunSet(runs_root).select(arm="trope")
    if not runs:
        raise MissingRuns(
            f"no TROPE runs under {Path(runs_root)} to sample parser--edit pairs "
            f"from. Produce them with scripts/run_main.sh (README.md)."
        )
    rows: list[dict[str, Any]] = []
    for run in runs.runs:
        rows += _semantic_rows(run)
    if not rows:
        raise MissingRuns(
            f"the TROPE runs under {Path(runs_root)} record no generated candidates "
            f"in trace.jsonl; nothing to audit."
        )
    sample = _stratified(rows, FAMILIES, n // len(FAMILIES), seed)
    return _write_sheet(out_csv, sample, SEMANTIC_FIELDS, SEMANTIC_ANNOTATIONS)


def sample_retrieval_audit(
    corpus_root_or_runs: str | Path, out_csv: str | Path, n: int = 320, seed: int = 0
) -> Path:
    """Draw the evidence passages of the retrieval audit (`tab:retaudit`), n/4 per family."""
    rows = _corpus_rows(Path(corpus_root_or_runs))
    if not rows:
        raise MissingRuns(
            f"no evidence passages under {Path(corpus_root_or_runs)}. The retrieval "
            f"corpus is built at run time by trope.corpus and is not written into "
            f"the run directory; export it (one JSONL record per passage, with "
            f"`family` and `text`) before sampling."
        )
    sample = _stratified(rows, FAMILIES, n // len(FAMILIES), seed)
    return _write_sheet(out_csv, sample, RETRIEVAL_FIELDS, RETRIEVAL_ANNOTATIONS)


def _corpus_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    files = [root] if root.is_file() else sorted(root.rglob("*.jsonl"))
    for path in files:
        if path.suffix != ".jsonl":
            continue
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            record = json.loads(line)
            rows.append(
                {
                    "stratum": _stratum(record.get("family", path.stem)),
                    "passage_id": str(record.get("passage_id", f"{path.stem}:{index}")),
                    "source": str(record.get("source", path)),
                    "problem_id": str(record.get("problem_id", "")),
                    "passage": str(record.get("text", "")),
                }
            )
    if rows or root.is_file():
        return rows
    for path in sorted(root.rglob("*.txt")):
        rows.append(
            {
                "stratum": _stratum(path.parent.name),
                "passage_id": path.stem,
                "source": str(path),
                "problem_id": "",
                "passage": path.read_text(encoding="utf-8").strip(),
            }
        )
    return rows


def cohens_kappa(a: Sequence[Any], b: Sequence[Any]) -> float:
    """Cohen's kappa for two annotators over the same items."""
    first = list(a)
    second = list(b)
    if len(first) != len(second):
        raise ValueError(f"annotators disagree on length: {len(first)} vs {len(second)}")
    if not first:
        raise ValueError("no annotations")

    n = len(first)
    observed = sum(1 for x, y in zip(first, second, strict=False) if x == y) / n
    labels = set(first) | set(second)
    expected = sum(
        (first.count(label) / n) * (second.count(label) / n) for label in labels
    )
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else float("nan")
    return (observed - expected) / (1.0 - expected)
