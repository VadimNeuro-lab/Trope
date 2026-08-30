"""Representation -> point cloud, the support of the empirical measure mu_R."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from trope.backends.base import Encoder
from trope.types import Representation, prune_dangling

FEATURE_VERSION = 3

ISOLATED = "isolated"


def type_of(entity) -> str:
    """The textual label of ``T(e)``: the closed role and the domain sort."""
    return f"{entity.type} {entity.sort}".strip()


@dataclass(frozen=True, slots=True)
class FeatureCloud:
    """Uniformly weighted typed feature vectors of one representation."""

    atoms: np.ndarray
    version: int = FEATURE_VERSION

    @property
    def n_atoms(self) -> int:
        return int(self.atoms.shape[0])


def type_label(rep: Representation, eid: str) -> str:
    """Textual label of ``type(Rel(e))``: the relation types incident to `e`."""
    types = sorted({r.rtype for r in rep.incident(eid)})
    return " ".join(types) if types else ISOLATED


def representation_features(
    rep: Representation,
    encoder: Encoder,
    *,
    degree_scale: float = 0.25,
) -> FeatureCloud:
    """The typed feature cloud of `rep`, embedded through `encoder`."""
    entities = tuple(rep.entities)
    dim = int(encoder.dim)
    if not entities:
        return FeatureCloud(atoms=np.zeros((1, 2 * dim + 1), dtype=np.float64))

    clean = rep if len(rep.relations) == 0 else _pruned(rep)
    roles = np.asarray(encoder.encode([type_of(e) for e in entities]), dtype=np.float64)
    incident = np.asarray(
        encoder.encode([type_label(clean, e.id) for e in entities]), dtype=np.float64
    )
    degrees = degree_scale * np.array(
        [[clean.degree(e.id)] for e in entities], dtype=np.float64
    )
    return FeatureCloud(atoms=np.hstack([roles, degrees, incident]))


def _pruned(rep: Representation) -> Representation:
    """`rep` with relations that reference missing entities dropped."""
    kept = prune_dangling(rep.entities, rep.relations)
    return rep if len(kept) == len(rep.relations) else replace(rep, relations=kept)
