"""d_struct, Eq. (4): the feature map of `features` composed with the solver of `sinkhorn`."""

from __future__ import annotations

import functools
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, NamedTuple

import numpy as np

from trope.backends.base import Encoder, HashEncoder
from trope.features import FEATURE_VERSION, FeatureCloud, representation_features
from trope.sinkhorn import wasserstein2
from trope.types import Representation


@dataclass(frozen=True, slots=True)
class DistanceParams:
    """The `distance` block of the config, as the distance code reads it."""

    sinkhorn_iters: int = 50
    sinkhorn_eps: float = 0.01
    degree_scale: float = 1.0
    encoder_dim: int = 64

    @property
    def feature_version(self) -> int:
        return FEATURE_VERSION


class CacheInfo(NamedTuple):
    """Field order matches `functools.lru_cache` so it prints the same way."""

    hits: int
    misses: int
    maxsize: int
    currsize: int
    cloud_hits: int
    cloud_misses: int


def d_struct(
    r1: Representation,
    r2: Representation,
    cfg_or_params: Any = None,
    *,
    encoder: Encoder | None = None,
) -> float:
    """Structural distance between two representations."""
    params = as_params(cfg_or_params)
    enc = encoder if encoder is not None else _default_encoder(params.encoder_dim)
    if r1.fingerprint() > r2.fingerprint():
        r1, r2 = r2, r1
    return cloud_distance(_features(r1, enc, params), _features(r2, enc, params), params)


def cloud_distance(
    left: FeatureCloud, right: FeatureCloud, params: DistanceParams
) -> float:
    """W_2 between two typed feature clouds, in the order given."""
    if left.version != right.version:
        raise ValueError(
            f"feature maps disagree: version {left.version} against {right.version}"
        )
    if _same_measure(left.atoms, right.atoms):
        return 0.0
    return float(
        wasserstein2(left.atoms, right.atoms, params.sinkhorn_eps, params.sinkhorn_iters)
    )


def _same_measure(left: np.ndarray, right: np.ndarray) -> bool:
    """Whether two uniformly weighted clouds are the same multi-set of atoms."""
    if left.shape != right.shape:
        return False
    return bool(np.array_equal(_canonical(left), _canonical(right)))


def _canonical(atoms: np.ndarray) -> np.ndarray:
    return atoms[np.lexsort(atoms.T[::-1])]


def as_params(cfg_or_params: Any) -> DistanceParams:
    """Normalise whatever the caller passed into a `DistanceParams`."""
    if isinstance(cfg_or_params, DistanceParams):
        return cfg_or_params
    defaults = DistanceParams()
    block: Any = defaults
    if cfg_or_params is not None:
        block = getattr(cfg_or_params, "distance", cfg_or_params)
    return DistanceParams(
        sinkhorn_iters=int(getattr(block, "sinkhorn_iters", defaults.sinkhorn_iters)),
        sinkhorn_eps=float(getattr(block, "sinkhorn_eps", defaults.sinkhorn_eps)),
        degree_scale=float(getattr(block, "degree_scale", defaults.degree_scale)),
        encoder_dim=int(getattr(block, "encoder_dim", defaults.encoder_dim)),
    )


def _features(
    rep: Representation, encoder: Encoder, params: DistanceParams
) -> FeatureCloud:
    return representation_features(rep, encoder, degree_scale=params.degree_scale)


class StructuralDistance:
    """Callable d_struct with the encoder and solver settings bound to it."""

    __slots__ = (
        "_cloud_hits",
        "_cloud_misses",
        "_clouds",
        "_hits",
        "_misses",
        "_pairs",
        "encoder",
        "maxsize",
        "params",
    )

    def __init__(
        self,
        encoder: Encoder | None = None,
        cfg_or_params: Any = None,
        *,
        maxsize: int = 4096,
    ) -> None:
        self.params = as_params(cfg_or_params)
        self.encoder = (
            encoder if encoder is not None else _default_encoder(self.params.encoder_dim)
        )
        self.maxsize = int(maxsize)
        self._pairs: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._clouds: OrderedDict[str, FeatureCloud] = OrderedDict()
        self._hits = self._misses = self._cloud_hits = self._cloud_misses = 0

    def __call__(self, r1: Representation, r2: Representation) -> float:
        left, right = r1.fingerprint(), r2.fingerprint()
        if left > right:
            r1, r2, left, right = r2, r1, right, left
        key = (left, right)
        cached = self._pairs.get(key)
        if cached is not None:
            self._hits += 1
            self._pairs.move_to_end(key)
            return cached
        self._misses += 1
        value = cloud_distance(self.cloud(r1), self.cloud(r2), self.params)
        self._store(self._pairs, key, value)
        return value

    def cloud(self, rep: Representation) -> FeatureCloud:
        key = rep.fingerprint()
        cached = self._clouds.get(key)
        if cached is not None:
            self._cloud_hits += 1
            self._clouds.move_to_end(key)
            return cached
        self._cloud_misses += 1
        value = _features(rep, self.encoder, self.params)
        self._store(self._clouds, key, value)
        return value

    @property
    def feature_version(self) -> int:
        return self.params.feature_version

    def provenance(self) -> dict[str, Any]:
        """What produced these distances, for the run manifest."""
        return {
            "feature_version": self.params.feature_version,
            "encoder": type(self.encoder).__name__,
            "encoder_dim": int(self.encoder.dim),
            "sinkhorn_eps": self.params.sinkhorn_eps,
            "sinkhorn_iters": self.params.sinkhorn_iters,
        }

    def cache_info(self) -> CacheInfo:
        return CacheInfo(
            hits=self._hits,
            misses=self._misses,
            maxsize=self.maxsize,
            currsize=len(self._pairs),
            cloud_hits=self._cloud_hits,
            cloud_misses=self._cloud_misses,
        )

    def cache_clear(self) -> None:
        self._pairs.clear()
        self._clouds.clear()
        self._hits = self._misses = self._cloud_hits = self._cloud_misses = 0

    def _store(self, cache: OrderedDict, key: Any, value: Any) -> None:
        cache[key] = value
        while len(cache) > self.maxsize:
            cache.popitem(last=False)


@functools.lru_cache(maxsize=8)
def _default_encoder(dim: int) -> HashEncoder:
    return HashEncoder(dim=dim)
