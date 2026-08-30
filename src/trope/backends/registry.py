"""Backend and encoder construction by name."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from trope.backends.base import Backend, Encoder, HashEncoder

BACKENDS = ("mock", "hf", "vllm")
ENCODERS = ("hash", "sentence")


class MissingDependency(ImportError):
    """An optional backend was requested without its extra installed."""

    def __init__(self, name: str, extra: str, cause: Exception) -> None:
        super().__init__(
            f"the {name!r} backend needs the {extra!r} extra: "
            f'pip install "trope[{extra}]"  ({cause})'
        )
        self.extra = extra


def make_backend(name: str, **kwargs: Any) -> Backend:
    factory = _BACKENDS.get(name)
    if factory is None:
        raise KeyError(f"unknown backend {name!r}; available: {', '.join(BACKENDS)}")
    return factory(**kwargs)


def make_encoder(name: str, **kwargs: Any) -> Encoder:
    factory = _ENCODERS.get(name)
    if factory is None:
        raise KeyError(f"unknown encoder {name!r}; available: {', '.join(ENCODERS)}")
    return factory(**kwargs)


def _mock(**kwargs: Any) -> Backend:
    from trope.backends.mock import MockBackend

    kwargs.pop("model", None)
    return MockBackend(**kwargs)


def _hf(**kwargs: Any) -> Backend:
    kwargs.pop("problems", None)
    try:
        from trope.backends.hf import HFBackend
    except ImportError as exc:
        raise MissingDependency("hf", "hf", exc) from exc
    return HFBackend(**kwargs)


def _vllm(**kwargs: Any) -> Backend:
    kwargs.pop("problems", None)
    try:
        from trope.backends.vllm import VLLMBackend
    except ImportError as exc:
        raise MissingDependency("vllm", "vllm", exc) from exc
    return VLLMBackend(**kwargs)


def _hash_encoder(**kwargs: Any) -> Encoder:
    kwargs.pop("model", None)
    return HashEncoder(**kwargs)


def _sentence_encoder(**kwargs: Any) -> Encoder:
    kwargs.pop("dim", None)
    try:
        from trope.backends.sentence import SentenceEncoder
    except ImportError as exc:
        raise MissingDependency("sentence", "encoder", exc) from exc
    return SentenceEncoder(**kwargs)


_BACKENDS: dict[str, Callable[..., Backend]] = {
    "mock": _mock,
    "hf": _hf,
    "vllm": _vllm,
}

_ENCODERS: dict[str, Callable[..., Encoder]] = {
    "hash": _hash_encoder,
    "sentence": _sentence_encoder,
}
