"""Conceptual-mutation operators: each edits one component of R. All four are pure and rebuild R through `rep.with_edit`, so the edit trail the Ethics section commits us to keeping survives every application."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

import numpy as np

from trope.operators.base import (
    MUTATION,
    Axiom,
    EditResult,
    Resources,
    nothing_to_do,
    rank_index,
    register,
    rename,
    settled,
    unit_rho,
)
from trope.types import (
    Assumption,
    EditRecord,
    Entity,
    Relation,
    Representation,
    dedupe_relations,
    prune_dangling,
)

_RETYPE_RULES: dict[tuple[str, str, str], str] = {
    ("src", "output", "depends_on"): "derived_from",
    ("src", "input", "derived_from"): "depends_on",
    ("src", "parameter", "derived_from"): "depends_on",
    ("src", "coordinate", "depends_on"): "indexes",
    ("dst", "output", "constrains"): "bounds",
}

_NON_WORD = re.compile(r"[^0-9a-z]+")


def _canonical_parts(
    entities: Iterable[Entity], relations: Iterable[Relation]
) -> tuple[tuple[Entity, ...], tuple[Relation, ...]]:
    """Sorted, deduped, dangle-free (E, Rel) so fingerprints are canonical."""
    ents = tuple(sorted(entities, key=lambda e: e.id))
    rels = dedupe_relations(prune_dangling(ents, relations))
    return ents, tuple(sorted(rels, key=lambda r: (r.src, r.dst, r.rtype, r.aux)))


def _rebuild(
    rep: Representation,
    record: EditRecord,
    entities: Iterable[Entity],
    relations: Iterable[Relation],
    **changes: Any,
) -> Representation:
    ents, rels = _canonical_parts(entities, relations)
    return rep.with_edit(record, entities=ents, relations=rels, **changes)


def _settled(
    old: Representation, new: Representation, detail: str, res: Resources
) -> EditResult:
    """Report the edit, or a no-op when it left the structure alone."""
    return settled(old, new, detail, res)


def _normalise(text: str) -> str:
    return " ".join(_NON_WORD.split(text.lower())).strip()


def _matches(text: str, axiom: Axiom) -> bool:
    """Whether an assumption states `axiom`."""
    normalised = _normalise(text)
    name = _normalise(axiom.name)
    return normalised == _normalise(axiom.text) or (bool(name) and name in normalised)


class AssumptionViolation:
    """Flip min(ceil(rho), |A|) assumptions to their negations."""

    name = "assumption_violation"
    kind = MUTATION
    arity = 1

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        if not rep.assumptions:
            return nothing_to_do(rep, "no assumptions to flip", res)
        k = int(np.ceil(np.clip(rho, 0.0, len(rep.assumptions))))
        if k == 0:
            return nothing_to_do(rep, "radicality rounds to zero flips", res)
        picked = sorted(
            int(i) for i in rng.choice(len(rep.assumptions), size=k, replace=False)
        )
        assumptions = list(rep.assumptions)
        for i in picked:
            assumptions[i] = assumptions[i].negate()
        detail = f"flipped {k}/{len(assumptions)}: " + ", ".join(
            rep.assumptions[i].text.strip()[:32] for i in picked
        )
        record = EditRecord(
            operator=self.name,
            radicality=float(rho),
            detail=detail,
            parents=(rep.fingerprint(),),
        )
        new = _rebuild(
            rep,
            record,
            rep.entities,
            rep.relations,
            assumptions=tuple(assumptions),
        )
        return _settled(rep, new, detail, res)


class TypeShifting:
    """Retype one entity and repair its incident relations."""

    name = "type_shifting"
    kind = MUTATION
    arity = 1

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        if not rep.entities:
            return nothing_to_do(rep, "no entities to retype", res)
        weights = np.array([rep.degree(e.id) for e in rep.entities], dtype=np.float64)
        total = weights.sum()
        p = weights / total if total > 0.0 else np.full(weights.size, 1.0 / weights.size)
        target = rep.entities[int(rng.choice(len(weights), p=p))]

        row = res.type_similarity.get(target.type) or {}
        ranked = sorted(
            (t for t in row if t != target.type), key=lambda t: (-row[t], t)
        )
        if not ranked:
            return EditResult.noop(f"no candidate types for {target.type!r}")
        start = rank_index(rho, len(ranked), res)
        pool = ranked[start:] or ranked[-1:]
        weights = np.array([max(row[t], 0.0) for t in pool], dtype=np.float64)
        total = weights.sum()
        p = weights / total if total > 0.0 else np.full(len(pool), 1.0 / len(pool))
        new_type = pool[int(rng.choice(len(pool), p=p))]

        detail = f"{target.id}: {target.type} -> {new_type}"
        new_sort = target.sort
        siblings = _sibling_sorts(target.sort, res)
        if unit_rho(rho, res) > 0.5 and siblings:
            new_sort = siblings[int(rng.integers(len(siblings)))]
            detail += (
                f"; sort {target.sort} -> {new_sort} "
                f"(both {res.supertype(target.sort)})"
            )

        entities = [
            replace(e, type=new_type, sort=new_sort) if e.id == target.id else e
            for e in rep.entities
        ]
        relations = [_retype(r, target.id, new_type) for r in rep.relations]
        record = EditRecord(
            operator=self.name,
            radicality=float(rho),
            detail=detail,
            parents=(rep.fingerprint(),),
        )
        return _settled(rep, _rebuild(rep, record, entities, relations), detail, res)


class FoundationalNegation:
    """Negate an axiom of the frame; larger rho targets a more load-bearing one."""

    name = "foundational_negation"
    kind = MUTATION
    arity = 1

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        spec = res.frame(rep.frame)
        ranked = spec.ranked_axioms()
        if not ranked:
            return EditResult.noop(f"frame {rep.frame!r} declares no axioms")
        axiom = ranked[rank_index(rho, len(ranked), res)]

        assumptions = list(rep.assumptions)
        hit = next(
            (i for i, a in enumerate(assumptions) if _matches(a.text, axiom)), None
        )
        if hit is None:
            assumptions.append(
                Assumption(text=axiom.text, load_bearing=True, negated=True)
            )
            detail = f"negated axiom {axiom.name} (added to A)"
        else:
            assumptions[hit] = replace(
                assumptions[hit], load_bearing=True, negated=True
            )
            detail = f"negated axiom {axiom.name} (assumption {hit})"

        changes: dict[str, Any] = {"assumptions": tuple(assumptions)}
        if axiom is ranked[-1]:
            nearest = [f for f in res.frame_ranking(rep.frame) if f != rep.frame]
            if nearest:
                changes["frame"] = nearest[0]
                detail += f"; frame {rep.frame} -> {nearest[0]}"

        record = EditRecord(
            operator=self.name,
            radicality=float(rho),
            detail=detail,
            parents=(rep.fingerprint(),),
        )
        new = _rebuild(rep, record, rep.entities, rep.relations, **changes)
        return _settled(rep, new, detail, res)


class Reification:
    """Promote a relation's predicate to an entity of its own."""

    name = "reification"
    kind = MUTATION
    arity = 1

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        pool = sorted(rep.relations, key=lambda r: (r.src, r.dst, r.rtype, r.aux))
        if not pool:
            return nothing_to_do(rep, "no relations to reify", res)
        rel = pool[int(rng.integers(len(pool)))]

        taken = set(rep.entity_ids)
        base = f"{rel.rtype}_{rel.src}_{rel.dst}"[:56]
        new_id = rename("p_", base, taken)
        predicate = Entity(
            id=new_id,
            type="parameter",
            sort=rel.rtype,
            label=f"reified {rel.rtype}",
        )
        added = (
            Relation(rel.src, new_id, "has"),
            Relation(rel.dst, new_id, "has"),
            Relation(new_id, rel.src, "relates", aux=rel.dst),
        )
        relations = [r for r in rep.relations if r != rel] + list(added)
        detail = f"reified {rel.rtype}({rel.src}, {rel.dst}) as {new_id}"
        record = EditRecord(
            operator=self.name,
            radicality=float(rho),
            detail=detail,
            parents=(rep.fingerprint(),),
        )
        new = _rebuild(rep, record, [*list(rep.entities), predicate], relations)
        return _settled(rep, new, detail, res)


def _sibling_sorts(sort: str, res: Resources) -> tuple[str, ...]:
    """Sorts sharing a supertype with `sort`, excluding it."""
    if sort not in res.sort_lattice:
        return ()
    parent = res.sort_lattice[sort]
    return tuple(
        sorted(s for s, sup in res.sort_lattice.items() if sup == parent and s != sort)
    )


def _retype(rel: Relation, eid: str, new_type: str) -> Relation:
    rtype = rel.rtype
    if rel.src == eid:
        rtype = _RETYPE_RULES.get(("src", new_type, rtype), rtype)
    if rel.dst == eid:
        rtype = _RETYPE_RULES.get(("dst", new_type, rtype), rtype)
    return rel if rtype == rel.rtype else replace(rel, rtype=rtype)


register(AssumptionViolation())
register(TypeShifting())
register(FoundationalNegation())
register(Reification())
