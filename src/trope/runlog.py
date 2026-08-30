"""Run artifacts: per-iteration traces, the call ledger and the manifest."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def _git_revision() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def exact_floats(record: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, str]:
    out = {}
    for key in keys:
        value = record.get(key)
        if isinstance(value, float):
            out[key] = value.hex()
    return out


@dataclass(slots=True)
class RunLog:
    root: Path
    manifest: dict[str, Any] = field(default_factory=dict)
    _trace: Any = None
    _count: int = 0

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        config: Mapping[str, Any],
        backend: str,
        models: Mapping[str, str] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> RunLog:
        log = cls(Path(root))
        log.manifest = {
            "schema_version": SCHEMA_VERSION,
            "config": json.loads(json.dumps(config, default=str)),
            "backend": backend,
            "models": dict(models or {}),
            "git_revision": _git_revision(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "argv": list(sys.argv),
        }
        if extra:
            log.manifest.update(json.loads(json.dumps(dict(extra), default=str)))
        (log.root / "manifest.json").write_text(
            json.dumps(log.manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        log._trace = (log.root / "trace.jsonl").open("w", encoding="utf-8")
        return log

    def step(self, record: Mapping[str, Any]) -> None:
        if self._trace is None:
            return
        payload = dict(record)
        payload["_exact"] = exact_floats(
            payload, ("z", "radicality", "novelty", "gamma", "verdict", "lambda_struct")
        )
        self._trace.write(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str) + "\n"
        )
        self._count += 1
        if self._count % 64 == 0:
            self._trace.flush()

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, default=str),
            encoding="utf-8",
        )
        return path

    def ledger(self, counter: Any) -> Path:
        payload = counter.as_dict() if hasattr(counter, "as_dict") else dict(counter)
        payload["note"] = (
            "The matched budget counts `generator` calls only. Parser calls, "
            "reference-LM scoring and verification are tracked separately and "
            "reported in the cost table."
        )
        return self.write_json("ledger.json", payload)

    def close(self) -> None:
        if self._trace is not None:
            self._trace.close()
            self._trace = None

    def __enter__(self) -> RunLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_trace(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def find_runs(root: str | Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p.parent for p in root.rglob("manifest.json"))
