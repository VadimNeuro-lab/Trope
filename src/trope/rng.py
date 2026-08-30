"""Named RNG streams."""

from __future__ import annotations

import numpy as np

from trope.backends.base import _stable_hash


class RngTree:
    __slots__ = ("_cache", "seed")

    def __init__(self, seed: int) -> None:
        self.seed = int(seed)
        self._cache: dict[str, np.random.Generator] = {}

    def stream(self, name: str) -> np.random.Generator:
        gen = self._cache.get(name)
        if gen is None:
            key = _stable_hash(name) % (2**63)
            seq = np.random.SeedSequence(entropy=self.seed, spawn_key=(key,))
            gen = np.random.default_rng(seq)
            self._cache[name] = gen
        return gen

    def fresh(self, name: str) -> np.random.Generator:
        """A stream reset to its initial state, for repeatable sub-experiments."""
        self._cache.pop(name, None)
        return self.stream(name)

    def derive(self, name: str) -> RngTree:
        key = _stable_hash(name) % (2**63)
        seq = np.random.SeedSequence(entropy=self.seed, spawn_key=(key,))
        return RngTree(int(seq.generate_state(1, dtype=np.uint64)[0] % (2**63)))

    def integer(self, name: str) -> int:
        """A reproducible integer seed to hand to a backend that wants one."""
        return int(self.stream(name).integers(0, 2**31 - 1))
