"""Problem records and the dataset registry."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

FAMILIES: tuple[str, ...] = (
    "math_answer",
    "math_proof",
    "code",
    "creativity",
    "discovery",
)


@dataclass(frozen=True, slots=True)
class Problem:
    id: str
    text: str
    benchmark: str
    family: str
    answer: str | None = None
    tests: tuple[str, ...] = ()
    entry_point: str = ""
    rubric: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise ValueError(f"unknown family {self.family!r} for problem {self.id!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "benchmark": self.benchmark,
            "family": self.family,
            "answer": self.answer,
            "tests": list(self.tests),
            "entry_point": self.entry_point,
            "rubric": self.rubric,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Problem":
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            benchmark=str(data["benchmark"]),
            family=str(data["family"]),
            answer=data.get("answer"),
            tests=tuple(data.get("tests") or ()),
            entry_point=str(data.get("entry_point", "")),
            rubric=str(data.get("rubric", "")),
            metadata=dict(data.get("metadata") or {}),
        )


class Dataset(Sequence[Problem]):
    def __init__(self, name: str, problems: Iterable[Problem]) -> None:
        self.name = name
        self._items = tuple(problems)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index):  # type: ignore[override]
        if isinstance(index, slice):
            return Dataset(self.name, self._items[index])
        return self._items[index]

    def __iter__(self) -> Iterator[Problem]:
        return iter(self._items)

    def __repr__(self) -> str:
        return f"Dataset({self.name!r}, n={len(self._items)})"

    @property
    def family(self) -> str:
        return self._items[0].family if self._items else "math_answer"

    def subset(self, n: int | None) -> "Dataset":
        return self if n is None else Dataset(self.name, self._items[:n])

    def write_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for p in self._items:
                fh.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")

    @classmethod
    def read_jsonl(cls, path: str | Path, name: str | None = None) -> "Dataset":
        path = Path(path)
        items = [
            Problem.from_dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(name or path.stem, items)


_REGISTRY: dict[str, Callable[..., Dataset]] = {}


def register(name: str) -> Callable[[Callable[..., Dataset]], Callable[..., Dataset]]:
    def wrap(fn: Callable[..., Dataset]) -> Callable[..., Dataset]:
        _REGISTRY[name] = fn
        return fn

    return wrap


def _discover() -> None:
    """Import the modules whose `@register` decorators fill the registry."""
    import trope.data.loaders  # noqa: F401
    import trope.data.synthetic  # noqa: F401


def load(name: str, **kwargs: Any) -> Dataset:
    _discover()
    if name not in _REGISTRY:
        raise KeyError(f"unknown benchmark {name!r}; have {sorted(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)


def available() -> tuple[str, ...]:
    _discover()
    return tuple(sorted(_REGISTRY))
