"""MAP-Elites archive A: the three acceptance filters and the coverage metric."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from trope.descriptors import Descriptor, flat_index
from trope.types import Candidate, Representation


def verifies(verdict: float) -> bool:
    """Algorithm 1 line 11: `V_P(s) > 0`."""
    return verdict > 0.0


@dataclass(frozen=True, slots=True)
class InsertResult:
    inserted: bool
    replaced: bool
    cell: tuple[int, ...] | None
    reason: str


@dataclass(slots=True)
class Elite:
    candidate: Candidate
    cell: tuple[int, ...]
    order: int
    losses: int = 0

    @property
    def key(self) -> tuple[float, float]:
        return (self.candidate.verdict, self.candidate.novelty)


class Archive:
    """One grid per problem. Insertion is the only way in; nothing is evicted."""

    __slots__ = ("_cells", "_order", "descriptor", "novelty_threshold")

    def __init__(self, descriptor: Descriptor, *, novelty_threshold: float) -> None:
        self.descriptor = descriptor
        self.novelty_threshold = float(novelty_threshold)
        self._cells: dict[tuple[int, ...], Elite] = {}
        self._order = 0

    @staticmethod
    def verified(verdict: float) -> bool:
        return verifies(verdict)

    def insert(self, candidate: Candidate) -> InsertResult:
        """Apply the two runtime filters, then the MAP-Elites replacement rule."""
        if candidate.novelty < self.novelty_threshold:
            return InsertResult(False, False, None, "novelty")
        if not self.verified(candidate.verdict):
            return InsertResult(False, False, None, "verified")

        cell = tuple(self.descriptor(candidate.text, candidate.representation))
        candidate.descriptor = cell
        self._order += 1
        current = self._cells.get(cell)
        if current is None:
            self._cells[cell] = Elite(candidate, cell, self._order)
            return InsertResult(True, False, cell, "inserted")
        if (candidate.verdict, candidate.novelty) > current.key:
            self._cells[cell] = Elite(candidate, cell, self._order, current.losses + 1)
            return InsertResult(True, True, cell, "replaced")
        current.losses += 1
        return InsertResult(False, False, cell, "dominated")

    def coverage(self) -> float:
        """Eq. (2): fraction of cells holding a verified solution."""
        n_cells = self.descriptor.n_cells
        if n_cells <= 0:
            return 0.0
        filled = sum(1 for e in self._cells.values() if self.verified(e.candidate.verdict))
        return filled / n_cells

    def best(self) -> Candidate | None:
        elites = sorted(self._cells.values(), key=lambda e: (-e.key[0], -e.key[1], e.order))
        return elites[0].candidate if elites else None

    def elites(self) -> tuple[Candidate, ...]:
        return tuple(e.candidate for e in self._sorted())

    def cells(self) -> Mapping[tuple[int, ...], Elite]:
        return dict(self._cells)

    def losses(self) -> int:
        return sum(e.losses for e in self._cells.values())

    def __len__(self) -> int:
        return len(self._cells)

    def __contains__(self, cell: Sequence[int]) -> bool:
        return tuple(cell) in self._cells

    def __iter__(self) -> Iterator[Elite]:
        return iter(self._sorted())

    def _sorted(self) -> list[Elite]:
        return sorted(self._cells.values(), key=lambda e: e.cell)

    def to_dict(self) -> dict[str, Any]:
        shape = tuple(self.descriptor.shape)
        return {
            "descriptor": getattr(self.descriptor, "name", ""),
            "shape": list(shape),
            "n_cells": self.descriptor.n_cells,
            "novelty_threshold": self.novelty_threshold,
            "coverage": self.coverage(),
            "occupied": len(self._cells),
            "losses": self.losses(),
            "entries": [
                {
                    "cell": list(e.cell),
                    "cell_index": flat_index(e.cell, shape),
                    "order": e.order,
                    "losses": e.losses,
                    "iteration": e.candidate.iteration,
                    "operator": e.candidate.operator,
                    "radicality": e.candidate.radicality,
                    "novelty": e.candidate.novelty,
                    "verdict": e.candidate.verdict,
                    "text": e.candidate.text,
                    "representation": e.candidate.representation.to_dict(with_history=True),
                    "meta": e.candidate.meta,
                }
                for e in self._sorted()
            ],
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        descriptor: Descriptor,
    ) -> Archive:
        """Rebuild an archive from `to_dict`, cells as recorded."""
        archive = cls(
            descriptor,
            novelty_threshold=float(data.get("novelty_threshold", 0.0)),
        )
        for entry in data.get("entries", ()):
            cell = tuple(int(i) for i in entry["cell"])
            candidate = Candidate(
                text=str(entry.get("text", "")),
                representation=Representation.from_dict(entry.get("representation") or {}),
                operator=str(entry.get("operator", "")),
                radicality=float(entry.get("radicality", 0.0)),
                novelty=float(entry.get("novelty", 0.0)),
                verdict=float(entry.get("verdict", 0.0)),
                descriptor=cell,
                iteration=int(entry.get("iteration", -1)),
                meta=dict(entry.get("meta") or {}),
            )
            order = int(entry.get("order", archive._order + 1))
            archive._cells[cell] = Elite(candidate, cell, order, int(entry.get("losses", 0)))
            archive._order = max(archive._order, order)
        return archive
