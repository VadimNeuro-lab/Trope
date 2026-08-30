"""Structural isomorphism of typed representations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import permutations

from trope.types import Representation

MAX_COMPONENT_GROUP = 6

MAX_ASSIGNMENTS = 200_000


@dataclass(frozen=True, slots=True)
class Comparison:
    isomorphic: bool
    undecided: bool
    reason: str = ""


def structurally_isomorphic(a: Representation, b: Representation) -> bool:
    return compare(a, b).isomorphic


def compare(a: Representation, b: Representation) -> Comparison:
    """Whether a bijection of entity ids carries `a` onto `b`."""
    if not _coarse_match(a, b):
        return Comparison(False, False, "coarse invariants differ")

    colour_a, colour_b = _colours(a), _colours(b)
    if _colour_multiset(colour_a) != _colour_multiset(colour_b):
        return Comparison(False, False, "1-WL colours differ")

    budget = [MAX_ASSIGNMENTS]
    comps_a, comps_b = _components(a), _components(b)
    if len(comps_a) != len(comps_b):
        return Comparison(False, False, "different number of components")

    groups_a = _group_by_signature(a, comps_a, colour_a)
    groups_b = _group_by_signature(b, comps_b, colour_b)
    if set(groups_a) != set(groups_b):
        return Comparison(False, False, "component signatures differ")
    for sig, members in groups_a.items():
        if len(members) != len(groups_b[sig]):
            return Comparison(False, False, "component multiplicities differ")
        if len(members) > MAX_COMPONENT_GROUP:
            return Comparison(False, True, f"{len(members)} interchangeable components")

    for sig, members in groups_a.items():
        matched, undecided = _match_group(
            a, b, members, groups_b[sig], colour_a, colour_b, budget
        )
        if undecided:
            return Comparison(False, True, "too symmetric to decide within budget")
        if not matched:
            return Comparison(False, False, f"no bijection for component group {sig[0]}")
    return Comparison(True, False, "")


def _colour_multiset(colour: Mapping[str, tuple]) -> tuple[str, ...]:
    return tuple(sorted(str(value) for value in colour.values()))


def _coarse_match(a: Representation, b: Representation) -> bool:
    return (
        len(a.entities) == len(b.entities)
        and len(a.relations) == len(b.relations)
        and a.frame == b.frame
        and a.goal == b.goal
        and sorted(x.rendered() for x in a.assumptions)
        == sorted(x.rendered() for x in b.assumptions)
        and sorted((e.type, e.sort) for e in a.entities)
        == sorted((e.type, e.sort) for e in b.entities)
        and sorted(r.rtype for r in a.relations) == sorted(r.rtype for r in b.relations)
    )


def _components(rep: Representation) -> list[tuple[str, ...]]:
    parent = {e.id: e.id for e in rep.entities}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in rep.relations:
        ends = [x for x in r.endpoints if x in parent]
        for other in ends[1:]:
            ra, rb = find(ends[0]), find(other)
            if ra != rb:
                parent[ra] = rb
    buckets: dict[str, list[str]] = defaultdict(list)
    for e in rep.entities:
        buckets[find(e.id)].append(e.id)
    return [tuple(sorted(v)) for v in buckets.values()]


def _colours(rep: Representation) -> dict[str, tuple]:
    """1-WL refinement."""
    initial = {
        e.id: (e.type, e.sort, _degree_signature(rep, e.id)) for e in rep.entities
    }
    neighbours = {e.id: rep.neighbours(e.id) for e in rep.entities}
    colour = _compress(initial)
    for _ in range(len(rep.entities)):
        refined = _compress(
            {
                eid: (colour[eid], tuple(sorted(colour[n] for n in neighbours[eid])))
                for eid in colour
            }
        )
        if _partition(refined) == _partition(colour):
            break
        colour = refined
    return {eid: (initial[eid], colour[eid]) for eid in colour}


def _compress(colour: Mapping[str, object]) -> dict[str, int]:
    order = {key: i for i, key in enumerate(sorted(set(colour.values()), key=str))}
    return {eid: order[value] for eid, value in colour.items()}


def _partition(colour: Mapping[str, int]) -> frozenset[frozenset[str]]:
    buckets: dict[int, set[str]] = defaultdict(set)
    for eid, value in colour.items():
        buckets[value].add(eid)
    return frozenset(frozenset(v) for v in buckets.values())


def _degree_signature(rep: Representation, eid: str) -> tuple:
    """Per-position incidence counts, so a ternary relation is not flattened."""
    counts: dict[tuple[str, int], int] = defaultdict(int)
    for r in rep.relations:
        for position, endpoint in enumerate(r.endpoints):
            if endpoint == eid:
                counts[(r.rtype, position)] += 1
    return tuple(sorted(counts.items()))


def _signature(rep: Representation, comp: Sequence[str], colour: Mapping[str, tuple]) -> tuple:
    members = set(comp)
    edges = sorted(
        r.rtype for r in rep.relations if all(x in members for x in r.endpoints)
    )
    return (
        len(comp),
        tuple(sorted(str(colour[e]) for e in comp)),
        tuple(edges),
    )


def _group_by_signature(
    rep: Representation,
    comps: Sequence[Sequence[str]],
    colour: Mapping[str, tuple],
) -> dict[tuple, list[tuple[str, ...]]]:
    groups: dict[tuple, list[tuple[str, ...]]] = defaultdict(list)
    for comp in comps:
        groups[_signature(rep, comp, colour)].append(tuple(comp))
    return groups


def _match_group(
    a: Representation,
    b: Representation,
    left: Sequence[Sequence[str]],
    right: Sequence[Sequence[str]],
    colour_a: Mapping[str, tuple],
    colour_b: Mapping[str, tuple],
    budget: list[int],
) -> tuple[bool, bool]:
    """Match same-signature components pairwise; True only if all of them match."""
    undecided = False
    for order in permutations(range(len(right))):
        ok = True
        for i, j in enumerate(order):
            result = _component_isomorphic(
                a, b, left[i], right[j], colour_a, colour_b, budget
            )
            if result is None:
                undecided = True
                ok = False
                break
            if not result:
                ok = False
                break
        if ok:
            return True, False
    return False, undecided


def _component_isomorphic(
    a: Representation,
    b: Representation,
    comp_a: Sequence[str],
    comp_b: Sequence[str],
    colour_a: Mapping[str, tuple],
    colour_b: Mapping[str, tuple],
    budget: list[int],
) -> bool | None:
    """True, False, or None when the search exhausts `budget` first."""
    classes_a: dict[tuple, list[str]] = defaultdict(list)
    classes_b: dict[tuple, list[str]] = defaultdict(list)
    for eid in comp_a:
        classes_a[colour_a[eid]].append(eid)
    for eid in comp_b:
        classes_b[colour_b[eid]].append(eid)
    if set(classes_a) != set(classes_b):
        return False
    for key, members in classes_a.items():
        if len(members) != len(classes_b[key]):
            return False

    members_a, members_b = set(comp_a), set(comp_b)
    edges_a = _edge_index(a, members_a)
    edges_b = _edge_index(b, members_b)
    if _edge_shape(edges_a) != _edge_shape(edges_b):
        return False

    order = sorted(comp_a, key=lambda e: (len(classes_a[colour_a[e]]), e))
    candidates = {e: sorted(classes_b[colour_a[e]]) for e in order}
    mapping: dict[str, str] = {}
    used: set[str] = set()

    def consistent(source: str, image: str) -> bool:
        for edge in edges_a:
            if source not in edge[1:]:
                continue
            if any(x not in mapping and x != source for x in edge[1:]):
                continue
            mapped = (edge[0], *(image if x == source else mapping[x] for x in edge[1:]))
            if edges_a[edge] > edges_b.get(mapped, 0):
                return False
        return True

    def walk(i: int) -> bool | None:
        if i == len(order):
            return True
        source = order[i]
        exhausted = False
        for image in candidates[source]:
            if budget[0] <= 0:
                return None
            if image in used:
                continue
            budget[0] -= 1
            if not consistent(source, image):
                continue
            mapping[source] = image
            used.add(image)
            result = walk(i + 1)
            if result is True:
                return True
            if result is None:
                exhausted = True
            del mapping[source]
            used.discard(image)
        return None if exhausted else False

    outcome = walk(0)
    if outcome is True:
        return True
    return None if outcome is None or budget[0] <= 0 else False


def _edge_index(rep: Representation, members: set[str]) -> dict[tuple, int]:
    """Multiset of (rtype, *endpoints) over the relations inside `members`."""
    counts: dict[tuple, int] = defaultdict(int)
    for r in rep.relations:
        if all(x in members for x in r.endpoints):
            counts[(r.rtype, *r.endpoints)] += 1
    return counts


def _edge_shape(edges: Mapping[tuple, int]) -> tuple:
    """The part of an edge index that does not depend on entity names."""
    shape: dict[tuple, int] = defaultdict(int)
    for edge, count in edges.items():
        shape[(edge[0], len(edge) - 1)] += count
    return tuple(sorted(shape.items()))
