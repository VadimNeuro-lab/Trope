"""Typed structural representation R = (E, Rel, T, A, G, F) and its edit trail."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

ENTITY_TYPES: tuple[str, ...] = (
    "constant",
    "variable",
    "parameter",
    "input",
    "output",
    "coordinate",
)

RELATION_TYPES: tuple[str, ...] = (
    "has",
    "relates",
    "depends_on",
    "constrains",
    "part_of",
    "maps_to",
    "equals",
    "bounds",
    "indexes",
    "applies_to",
    "derived_from",
)


class SchemaError(ValueError):
    """Raised when a representation violates the parser schema."""


class OperatorError(RuntimeError):
    """Raised when an operator cannot be applied to its inputs."""


@dataclass(frozen=True, slots=True)
class Entity:
    """A thing the problem talks about."""

    id: str
    type: str
    sort: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise SchemaError("entity id must be non-empty")
        if self.type not in ENTITY_TYPES:
            raise SchemaError(f"unknown entity type {self.type!r}")


@dataclass(frozen=True, slots=True)
class Relation:
    """An edge of Rel."""

    src: str
    dst: str
    rtype: str
    aux: str = ""

    def __post_init__(self) -> None:
        if self.rtype not in RELATION_TYPES:
            raise SchemaError(f"unknown relation type {self.rtype!r}")

    @property
    def arity(self) -> int:
        return 3 if self.aux else 2

    @property
    def endpoints(self) -> tuple[str, ...]:
        return (self.src, self.dst, self.aux) if self.aux else (self.src, self.dst)


@dataclass(frozen=True, slots=True)
class Assumption:
    text: str
    load_bearing: bool = False
    negated: bool = False

    def negate(self) -> Assumption:
        return replace(self, negated=not self.negated)

    def rendered(self) -> str:
        return f"not ({self.text})" if self.negated else self.text


@dataclass(frozen=True, slots=True)
class Goal:
    objective: str
    constraint: str = ""


@dataclass(frozen=True, slots=True)
class EditRecord:
    """One entry of the audit trail the Ethics section commits us to keeping."""

    operator: str
    radicality: float
    detail: str = ""
    parents: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Representation:
    entities: tuple[Entity, ...] = ()
    relations: tuple[Relation, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    goal: Goal = Goal("")  # noqa: RUF009 - Goal is frozen, so sharing one is safe
    frame: str = "unspecified"
    history: tuple[EditRecord, ...] = ()
    source_text: str = ""

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.entities)

    def entity(self, eid: str) -> Entity:
        for e in self.entities:
            if e.id == eid:
                return e
        raise KeyError(eid)

    def types(self) -> dict[str, str]:
        """The T component of the six-tuple, as an explicit map."""
        return {e.id: e.type for e in self.entities}

    def degree(self, eid: str) -> int:
        return sum(1 for r in self.relations if eid in r.endpoints)

    def incident(self, eid: str) -> tuple[Relation, ...]:
        return tuple(r for r in self.relations if eid in r.endpoints)

    def neighbours(self, eid: str) -> tuple[str, ...]:
        out: list[str] = []
        for r in self.relations:
            if eid in r.endpoints:
                out.extend(x for x in r.endpoints if x != eid)
        return tuple(dict.fromkeys(out))

    def with_edit(self, record: EditRecord, **changes: Any) -> Representation:
        return replace(self, history=(*self.history, record), **changes)

    def to_dict(self, *, with_history: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "entities": [
                {"id": e.id, "type": e.type, "sort": e.sort, "label": e.label}
                for e in self.entities
            ],
            "relations": [
                (
                    {"src": r.src, "dst": r.dst, "rtype": r.rtype, "aux": r.aux}
                    if r.aux
                    else {"src": r.src, "dst": r.dst, "rtype": r.rtype}
                )
                for r in self.relations
            ],
            "assumptions": [
                {"text": a.text, "load_bearing": a.load_bearing, "negated": a.negated}
                for a in self.assumptions
            ],
            "goal": {
                "objective": self.goal.objective,
                "constraint": self.goal.constraint,
            },
            "frame": self.frame,
        }
        if with_history:
            out["history"] = [
                {
                    "operator": h.operator,
                    "radicality": h.radicality,
                    "detail": h.detail,
                    "parents": list(h.parents),
                }
                for h in self.history
            ]
        return out

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], *, source_text: str = ""
    ) -> Representation:
        try:
            entities = tuple(
                Entity(
                    id=str(e["id"]),
                    type=str(e["type"]),
                    sort=str(e.get("sort", "")),
                    label=str(e.get("label", "")),
                )
                for e in data.get("entities", [])
            )
            relations = tuple(
                Relation(
                    src=str(r["src"]),
                    dst=str(r["dst"]),
                    rtype=str(r["rtype"]),
                    aux=str(r.get("aux", "")),
                )
                for r in data.get("relations", [])
            )
            assumptions = tuple(
                Assumption(
                    text=str(a["text"]),
                    load_bearing=bool(a.get("load_bearing", False)),
                    negated=bool(a.get("negated", False)),
                )
                for a in data.get("assumptions", [])
            )
            goal_raw = data.get("goal") or {}
            goal = Goal(
                objective=str(goal_raw.get("objective", "")),
                constraint=str(goal_raw.get("constraint", "")),
            )
        except (KeyError, TypeError) as exc:
            raise SchemaError(f"malformed representation: {exc}") from exc
        history = tuple(
            EditRecord(
                operator=str(h.get("operator", "")),
                radicality=float(h.get("radicality", 0.0)),
                detail=str(h.get("detail", "")),
                parents=tuple(str(p) for p in h.get("parents", ())),
            )
            for h in data.get("history", [])
        )
        return cls(
            entities=entities,
            relations=relations,
            assumptions=assumptions,
            goal=goal,
            frame=str(data.get("frame", "unspecified")),
            history=history,
            source_text=source_text or str(data.get("source_text", "")),
        )

    def to_json(self, *, with_history: bool = False, indent: int | None = 2) -> str:
        return json.dumps(
            self.to_dict(with_history=with_history), indent=indent, sort_keys=True
        )

    def fingerprint(self) -> str:
        """Stable hash of the structural content, ignoring the edit trail."""
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def dedupe_relations(relations: Iterable[Relation]) -> tuple[Relation, ...]:
    return tuple(dict.fromkeys(relations))


def prune_dangling(
    entities: Sequence[Entity], relations: Iterable[Relation]
) -> tuple[Relation, ...]:
    """Drop relations that reference entities which no longer exist."""
    known = {e.id for e in entities}
    return tuple(r for r in relations if all(x in known for x in r.endpoints))


@dataclass(slots=True)
class Candidate:
    """One generated solution plus everything needed to audit its acceptance."""

    text: str
    representation: Representation
    operator: str
    radicality: float
    novelty: float = 0.0
    verdict: float = 0.0
    descriptor: tuple[int, ...] = ()
    iteration: int = -1
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "operator": self.operator,
            "radicality": self.radicality,
            "novelty": self.novelty,
            "verdict": self.verdict,
            "descriptor": list(self.descriptor),
            "iteration": self.iteration,
            "representation": self.representation.to_dict(with_history=True),
            "meta": self.meta,
        }
