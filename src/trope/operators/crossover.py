"""Conceptual-crossover operators: recombination of two representations."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

import numpy as np

from trope.operators.base import (
    CROSSOVER,
    EditResult,
    Resources,
    canonical_parts,
    nothing_to_do,
    rank_index,
    register,
    rename,
    settled,
    unit_rho,
)
from trope.types import (
    EditRecord,
    Entity,
    Goal,
    Relation,
    Representation,
)

TRANSPLANT_PREFIX = "t_"
IMPORT_PREFIX = "imported_"

_WORDS = re.compile(r"[a-z0-9_]+")
_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "for", "to", "and", "or", "in", "on", "with",
     "minimise", "minimize", "maximise", "maximize", "find", "compute", "is"}
)


def _rebuild(
    rep: Representation,
    record: EditRecord,
    entities: Iterable[Entity],
    relations: Iterable[Relation],
    **changes: Any,
) -> Representation:
    ents, rels = canonical_parts(entities, relations)
    return rep.with_edit(record, entities=ents, relations=rels, **changes)


def _parents(rep: Representation, other: Representation) -> tuple[str, ...]:
    return (rep.fingerprint(), other.fingerprint())


class StructuralTransplant:
    """Graft a connected subgraph of R2 onto a compatible site in R1."""

    name = "structural_transplant"
    kind = CROSSOVER
    arity = 2

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        if other is None or not other.entities or not rep.entities:
            return nothing_to_do(rep, "nothing to transplant", res)

        donors = sorted(other.entities, key=lambda e: e.id)
        seed = donors[int(rng.integers(len(donors)))].id
        size = rank_index(rho, len(donors), res) + 1
        graft = _bfs(other, seed, size)

        taken = set(rep.entity_ids)
        mapping: dict[str, str] = {}
        for eid in graft:
            fresh = rename(TRANSPLANT_PREFIX, eid, taken)
            taken.add(fresh)
            mapping[eid] = fresh

        entities = list(rep.entities) + [
            replace(other.entity(eid), id=mapping[eid]) for eid in graft
        ]
        relations = list(rep.relations) + [
            Relation(
                mapping[r.src],
                mapping[r.dst],
                r.rtype,
                aux=mapping[r.aux] if r.aux else "",
            )
            for r in other.relations
            if all(x in mapping for x in r.endpoints)
        ]
        site = _graft_site(rep, other.entity(seed).type)
        relations.append(Relation(site.id, mapping[seed], "relates"))

        detail = (
            f"grafted {len(graft)} entities from {seed} onto {site.id} "
            f"({site.type})"
        )
        record = EditRecord(
            operator=self.name,
            radicality=float(rho),
            detail=detail,
            parents=_parents(rep, other),
        )
        return settled(rep, _rebuild(rep, record, entities, relations), detail, res)


class CategoricalImport:
    """Re-sort R1's entities into the vocabulary of a more distant frame."""

    name = "categorical_import"
    kind = CROSSOVER
    arity = 2

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        if other is None or not rep.entities:
            return nothing_to_do(rep, "nothing to import into", res)
        ranking = [f for f in res.frame_ranking(rep.frame) if f != rep.frame]
        if not ranking:
            return nothing_to_do(rep, f"no frame to import from {rep.frame!r}", res)
        target_frame = ranking[rank_index(rho, len(ranking), res)]
        targets = tuple(res.frame(target_frame).sorts)

        sources = tuple(sorted({e.sort for e in rep.entities}))
        mu = _compatibility_map(sources, targets, res)
        mandated = [t for t in targets if t not in set(mu.values())]
        if not mu and not mandated:
            return nothing_to_do(rep, f"no sort matches above tau_mu={res.tau_mu}", res)

        kept = [
            replace(e, sort=mu[e.sort]) for e in rep.entities if e.sort in mu
        ]
        dropped = len(rep.entities) - len(kept)
        detail = (
            f"frame {rep.frame} -> {target_frame}; mu={_render(mu)}; "
            f"dropped {dropped}; placeholders {len(mandated)}"
        )
        if not kept and not mandated:
            anchor = _most_connected(rep)
            kept = [anchor]
            detail += f"; kept {anchor.id} to avoid an empty E"

        taken = {e.id for e in kept}
        placeholders = []
        for sort in mandated:
            eid = rename(IMPORT_PREFIX, sort, taken)
            taken.add(eid)
            placeholders.append(
                Entity(id=eid, type="parameter", sort=sort, label=f"imported {sort}")
            )

        record = EditRecord(
            operator=self.name,
            radicality=float(rho),
            detail=detail,
            parents=_parents(rep, other),
        )
        new = _rebuild(
            rep,
            record,
            kept + placeholders,
            rep.relations,
            frame=target_frame,
        )
        return settled(rep, new, detail, res)

class RoleSwap:
    """Give R1's entities the meanings their R2 counterparts carry."""

    name = "role_swap"
    kind = CROSSOVER
    arity = 2

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        if other is None or not rep.entities or not other.entities:
            return nothing_to_do(rep, "nothing to swap with", res)

        phi = _correspondence(rep, other)
        pairs = [
            (mine, theirs)
            for mine, theirs in phi
            if rep.degree(mine.id) == other.degree(theirs.id)
            and (mine.label, mine.sort) != (theirs.label, theirs.sort)
        ]
        if not pairs:
            return nothing_to_do(rep, "no structurally equivalent pair to swap", res)

        k = rank_index(rho, len(pairs), res) + 1
        swapped = {mine.id: theirs for mine, theirs in pairs[:k]}
        entities = [
            replace(e, label=swapped[e.id].label, sort=swapped[e.id].sort)
            if e.id in swapped
            else e
            for e in rep.entities
        ]
        detail = "swapped " + ", ".join(
            f"{mine.id}<-{theirs.id}" for mine, theirs in pairs[:k]
        )
        record = EditRecord(
            operator=self.name,
            radicality=float(rho),
            detail=detail,
            parents=_parents(rep, other),
        )
        new = _rebuild(rep, record, entities, rep.relations)
        return settled(rep, new, detail, res)


class GoalParetoInversion:
    """Adopt R2's objective, an axis R1's own goal does not dominate."""

    name = "goal_pareto_inversion"
    kind = CROSSOVER
    arity = 2

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        if other is None or not other.goal.objective.strip():
            return nothing_to_do(rep, "no donor objective", res)
        if other.goal.objective == rep.goal.objective:
            return nothing_to_do(rep, "objectives already agree", res)
        if _dominated(rep.goal.objective, other.goal.objective):
            return nothing_to_do(rep, "donor objective is dominated by G_1", res)

        whole = unit_rho(rho, res) > 0.5
        goal = Goal(
            objective=other.goal.objective,
            constraint=other.goal.constraint if whole else rep.goal.constraint,
        )
        detail = "objective and constraint" if whole else "objective only"
        record = EditRecord(
            operator=self.name,
            radicality=float(rho),
            detail=detail,
            parents=_parents(rep, other),
        )
        new = _rebuild(rep, record, rep.entities, rep.relations, goal=goal)
        return settled(rep, new, detail, res)


def _bfs(rep: Representation, seed: str, size: int) -> tuple[str, ...]:
    """Up to `size` entity ids, breadth-first from `seed` in sorted order."""
    known = set(rep.entity_ids)
    order = [seed]
    seen = {seed}
    head = 0
    while head < len(order) and len(order) < size:
        for nb in sorted(rep.neighbours(order[head])):
            if nb in seen or nb not in known:
                continue
            seen.add(nb)
            order.append(nb)
            if len(order) >= size:
                break
        head += 1
    return tuple(order)


def _graft_site(rep: Representation, root_type: str) -> Entity:
    """The R1 entity to attach a graft to: same type as the root, else hub."""
    candidates = [e for e in rep.entities if e.type == root_type] or list(rep.entities)
    return min(candidates, key=lambda e: (-rep.degree(e.id), e.id))


def _dominated(existing: str, candidate: str) -> bool:
    """Whether `candidate` adds no axis `existing` does not already optimise."""
    words = set(_WORDS.findall(candidate.lower())) - _STOPWORDS
    if not words:
        return True
    return words <= (set(_WORDS.findall(existing.lower())) - _STOPWORDS)


def _most_connected(rep: Representation) -> Entity:
    return min(rep.entities, key=lambda e: (-rep.degree(e.id), e.id))


def _compatibility_map(
    sources: Sequence[str], targets: Sequence[str], res: Resources
) -> dict[str, str]:
    """Greedy maximum-similarity matching of source sorts onto target sorts."""
    if not sources or not targets:
        return {}
    sim = _name_similarity(sources, targets, res)
    for i, s in enumerate(sources):
        for j, t in enumerate(targets):
            if (
                s in res.sort_lattice
                and t in res.sort_lattice
                and res.sort_lattice[s] == res.sort_lattice[t]
            ):
                sim[i, j] = 1.0
    ranked = sorted(
        (
            (-float(sim[i, j]), s, t)
            for i, s in enumerate(sources)
            for j, t in enumerate(targets)
            if sim[i, j] > res.tau_mu
        )
    )
    mu: dict[str, str] = {}
    used: set[str] = set()
    for _, s, t in ranked:
        if s in mu or t in used:
            continue
        mu[s] = t
        used.add(t)
    return mu


def _name_similarity(
    sources: Sequence[str], targets: Sequence[str], res: Resources
) -> np.ndarray:
    vecs = np.asarray(res.encoder.encode(list(sources) + list(targets)), dtype=float)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit = vecs / norms
    return unit[: len(sources)] @ unit[len(sources) :].T


def _correspondence(
    rep: Representation, other: Representation
) -> list[tuple[Entity, Entity]]:
    """phi: E1 -> E2, matching within a role type, most connected first."""
    mine = _by_type(rep)
    theirs = _by_type(other)
    pairs: list[tuple[Entity, Entity]] = []
    for etype in sorted(mine):
        pairs.extend(zip(mine[etype], theirs.get(etype, ()), strict=False))
    return sorted(pairs, key=lambda p: p[0].id)


def _by_type(rep: Representation) -> dict[str, list[Entity]]:
    out: dict[str, list[Entity]] = {}
    for e in sorted(rep.entities, key=lambda e: (-rep.degree(e.id), e.id)):
        out.setdefault(e.type, []).append(e)
    return out


def _render(mu: dict[str, str]) -> str:
    return "{" + ", ".join(f"{k}->{v}" for k, v in sorted(mu.items())) + "}"


register(StructuralTransplant())
register(CategoricalImport())
register(RoleSwap())
register(GoalParetoInversion())
