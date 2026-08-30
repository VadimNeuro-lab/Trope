"""Operator protocol, shared resources and the catalog registry."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

import numpy as np

from trope.backends.base import DecodingParams, Encoder
from trope.types import (
    Entity,
    Relation,
    Representation,
    dedupe_relations,
    prune_dangling,
)

TOKEN = "token"
MUTATION = "mutation"
CROSSOVER = "crossover"
LEVELS: tuple[str, ...] = (TOKEN, MUTATION, CROSSOVER)


@dataclass(frozen=True, slots=True)
class Axiom:
    """`supports` names the axioms that fail if this one is negated."""

    name: str
    text: str
    supports: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FrameSpec:
    name: str
    keywords: tuple[str, ...]
    sorts: tuple[str, ...]
    axioms: tuple[Axiom, ...]

    def depth(self, name: str) -> int:
        """Number of axioms that transitively rest on `name`."""
        by_name = {a.name: a for a in self.axioms}
        if name not in by_name:
            return 0
        seen: set[str] = set()
        stack = list(by_name[name].supports)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            child = by_name.get(cur)
            if child is not None:
                stack.extend(child.supports)
        return len(seen)

    def ranked_axioms(self) -> tuple[Axiom, ...]:
        """Least load-bearing first, so rho indexes into the tail."""
        return tuple(sorted(self.axioms, key=lambda a: (self.depth(a.name), a.name)))


@dataclass(frozen=True, slots=True)
class Resources:
    """Everything the catalog needs that is not the representation itself."""

    frames: Mapping[str, FrameSpec]
    type_similarity: Mapping[str, Mapping[str, float]]
    sort_lattice: Mapping[str, str]
    discipline_similarity: Mapping[str, Mapping[str, float]]
    encoder: Encoder
    tau_mu: float = 0.6
    rho_max: float = 8.0
    token_params: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    default_supertype: str = "quantity"

    def frame(self, name: str) -> FrameSpec:
        return self.frames.get(name) or self.frames["unspecified"]

    def frame_ranking(self, source: str) -> tuple[str, ...]:
        """Frames ordered from nearest to furthest from `source`."""
        row = self.discipline_similarity.get(source)
        if not row:
            return tuple(sorted(self.frames))
        others = [f for f in row if f != source]
        return tuple(sorted(others, key=lambda f: (-row[f], f)))

    def supertype(self, sort: str) -> str:
        return self.sort_lattice.get(sort, self.default_supertype)


@dataclass(frozen=True, slots=True)
class EditResult:
    """What an operator did."""

    representation: Representation | None = None
    decoding: DecodingParams | None = None
    detail: str = ""
    changed: bool = True

    @classmethod
    def noop(cls, detail: str) -> EditResult:
        return cls(representation=None, decoding=None, detail=detail, changed=False)


def canonical_parts(
    entities: Iterable[Entity], relations: Iterable[Relation]
) -> tuple[tuple[Entity, ...], tuple[Relation, ...]]:
    """Sorted, deduped, dangle-free (E, Rel) so fingerprints are canonical."""
    ents = tuple(sorted(entities, key=lambda e: e.id))
    rels = dedupe_relations(prune_dangling(ents, relations))
    return ents, tuple(sorted(rels, key=lambda r: (r.src, r.dst, r.rtype, r.aux)))


def settled(
    old: Representation, new: Representation, detail: str, res: Resources
) -> EditResult:
    """Report the edit, or a no-op when it left the structure alone."""
    ents, rels = canonical_parts(old.entities, old.relations)
    if new.fingerprint() != replace(old, entities=ents, relations=rels).fingerprint():
        return EditResult(representation=new, detail=detail)
    return EditResult.noop("unchanged")


def nothing_to_do(rep: Representation, detail: str, res: Resources) -> EditResult:
    """An operator that found nothing to act on."""
    return EditResult.noop(detail)


class Operator(Protocol):
    name: str
    kind: str
    arity: int

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult: ...


_CATALOG: dict[str, Operator] = {}


def register(op: Operator) -> Operator:
    if op.name in _CATALOG:
        raise ValueError(f"operator {op.name!r} registered twice")
    if op.kind not in LEVELS:
        raise ValueError(f"operator {op.name!r} has unknown kind {op.kind!r}")
    _CATALOG[op.name] = op
    return op


def catalog(levels: Sequence[str] | None = None, enabled: Sequence[str] | None = None):
    import trope.operators.crossover
    import trope.operators.mutation
    import trope.operators.token  # noqa: F401

    names = sorted(_CATALOG)
    if levels is not None:
        names = [n for n in names if _CATALOG[n].kind in levels]
    if enabled:
        allowed = set(enabled)
        unknown = allowed - set(_CATALOG)
        if unknown:
            raise KeyError(f"unknown operators: {sorted(unknown)}")
        names = [n for n in names if n in allowed]
    return tuple(_CATALOG[n] for n in names)


def get(name: str) -> Operator:
    catalog()
    return _CATALOG[name]


def clamp_rho(rho: float, res: Resources) -> float:
    """Saturate radicality for operators that consume it as a bounded quantity."""
    return float(min(max(rho, 0.0), res.rho_max))


def unit_rho(rho: float, res: Resources) -> float:
    """Squash radicality into [0, 1] monotonically."""
    return clamp_rho(rho, res) / res.rho_max


def rank_index(rho: float, n: int, res: Resources) -> int:
    """Map radicality onto an index into a ranked list of length n."""
    if n <= 0:
        return 0
    return int(min(n - 1, np.floor(unit_rho(rho, res) * n)))


def load_resources(
    frames_path: str | None = None,
    types_path: str | None = None,
    discipline_path: str | None = None,
    *,
    encoder: Encoder | None = None,
    tau_mu: float = 0.6,
    rho_max: float = 8.0,
    token_params: Mapping[str, Mapping[str, float]] | None = None,
) -> Resources:
    import json
    from pathlib import Path

    from trope.backends.base import HashEncoder
    from trope.config import ASSET_DIR

    frames_file = Path(frames_path) if frames_path else ASSET_DIR / "frames.json"
    types_file = Path(types_path) if types_path else ASSET_DIR / "type_similarity.json"
    disc_file = (
        Path(discipline_path)
        if discipline_path
        else ASSET_DIR / "disciplinary_similarity.json"
    )

    raw_frames = json.loads(frames_file.read_text(encoding="utf-8"))["frames"]
    frames = {
        name: FrameSpec(
            name=name,
            keywords=tuple(spec.get("keywords", ())),
            sorts=tuple(spec.get("sorts", ())),
            axioms=tuple(
                Axiom(a["name"], a["text"], tuple(a.get("supports", ())))
                for a in spec.get("axioms", ())
            ),
        )
        for name, spec in raw_frames.items()
    }
    types = json.loads(types_file.read_text(encoding="utf-8"))
    disc = json.loads(disc_file.read_text(encoding="utf-8"))
    return Resources(
        frames=frames,
        type_similarity=types["similarity"],
        sort_lattice=types["sort_lattice"],
        discipline_similarity=disc["similarity"],
        encoder=encoder or HashEncoder(),
        tau_mu=tau_mu,
        rho_max=rho_max,
        token_params=dict(token_params or {}),
        default_supertype=types.get("default_supertype", "quantity"),
    )


WellFormedCheck = Callable[[Representation], tuple[bool, str]]


def well_formed(rep: Representation) -> tuple[bool, str]:
    """Post-operator structural check."""
    ids = [e.id for e in rep.entities]
    if not ids:
        return False, "no entities left"
    if len(set(ids)) != len(ids):
        return False, "duplicate entity ids"
    known = set(ids)
    for r in rep.relations:
        missing = [x for x in r.endpoints if x not in known]
        if missing:
            return False, f"relation references missing entity ({', '.join(missing)})"
    if not rep.goal.objective.strip():
        return False, "goal objective is empty"
    if not rep.assumptions:
        return False, "no assumptions left"
    return True, ""


def rename(prefix: str, eid: str, taken: set[str]) -> str:
    """Fresh entity id derived from `eid`, avoiding everything in `taken`."""
    base = f"{prefix}{eid}"
    if base not in taken:
        return base
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return f"{base}_{i}"


def describe(op: Operator) -> dict[str, Any]:
    return {"name": op.name, "kind": op.kind, "arity": op.arity}
