"""Sentence-encoder implementation of the `Encoder` protocol."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from typing import Any

import numpy as np

from trope.backends.registry import MissingDependency

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class SentenceEncoder:
    """Frozen sentence encoder producing unit-norm rows."""

    name = "sentence"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        revision: str | None = None,
        device: str | None = None,
        batch_size: int = 64,
        cache_size: int = 8192,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise MissingDependency("sentence", "encoder", exc) from exc

        self.model_id = str(model)
        self.revision = revision
        self.batch_size = int(batch_size)
        self.cache_size = int(cache_size)
        self._model = SentenceTransformer(self.model_id, device=device, revision=revision)
        self._model.eval()
        self.dim = int(self._model.get_sentence_embedding_dimension())
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        items = [str(t) for t in texts]
        if not items:
            return np.zeros((0, self.dim), dtype=np.float64)
        vectors: dict[str, np.ndarray | None] = {
            text: self._lookup(text) for text in dict.fromkeys(items)
        }
        missing = [t for t, vec in vectors.items() if vec is None]
        if missing:
            encoded = np.asarray(
                self._model.encode(
                    missing,
                    batch_size=self.batch_size,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ),
                dtype=np.float64,
            ).reshape(len(missing), self.dim)
            for text, vec in zip(missing, encoded, strict=False):
                vectors[text] = vec
                self._store(text, vec)
        return np.vstack([vectors[t] for t in items])

    def _lookup(self, text: str) -> np.ndarray | None:
        vec = self._cache.get(text)
        if vec is not None:
            self._cache.move_to_end(text)
        return vec

    def _store(self, text: str, vec: np.ndarray) -> None:
        if self.cache_size <= 0:
            return
        self._cache[text] = vec
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def info(self) -> dict[str, Any]:
        return {
            "encoder": self.name,
            "model": self.model_id,
            "revision": self.revision,
            "dim": self.dim,
            "device": str(getattr(self._model, "device", "")),
        }
