"""Buffer B of representations reachable by the search."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator

import numpy as np

from trope.types import Representation


class Buffer:
    __slots__ = ("_items", "_pinned", "_seen", "capacity")

    def __init__(self, seed: Representation | None = None, capacity: int = 64) -> None:
        self.capacity = int(capacity)
        self._items: deque[Representation] = deque()
        self._seen: set[str] = set()
        self._pinned: str | None = None
        if seed is not None:
            self.add(seed, pin=True)

    def add(self, rep: Representation, *, pin: bool = False) -> bool:
        key = rep.fingerprint()
        if key in self._seen:
            return False
        self._items.append(rep)
        self._seen.add(key)
        if pin and self._pinned is None:
            self._pinned = key
        self._evict()
        return True

    def _evict(self) -> None:
        while len(self._items) > self.capacity:
            oldest = self._items.popleft()
            key = oldest.fingerprint()
            if key == self._pinned:
                self._items.append(oldest)
                nxt = self._items.popleft()
                self._seen.discard(nxt.fingerprint())
            else:
                self._seen.discard(key)

    def sample(self, rng: np.random.Generator) -> Representation:
        if not self._items:
            raise IndexError("buffer is empty")
        return self._items[int(rng.integers(len(self._items)))]

    def sample_pair(
        self, rng: np.random.Generator
    ) -> tuple[Representation, Representation] | None:
        """Two distinct entries, or None when crossover is not yet available."""
        if len(self._items) < 2:
            return None
        i, j = rng.choice(len(self._items), size=2, replace=False)
        return self._items[int(i)], self._items[int(j)]

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Representation]:
        return iter(self._items)

    def __contains__(self, rep: object) -> bool:
        return isinstance(rep, Representation) and rep.fingerprint() in self._seen
