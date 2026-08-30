"""The baseline registry: name -> arm, and where an arm does not apply."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from trope.baselines.common import BaselineResult
from trope.baselines.decoding import DECODING_BASELINES, self_consistency
from trope.baselines.evolutionary import (
    eureka,
    evoprompt,
    funsearch,
    promptbreeder,
    universe_of_thoughts,
)
from trope.baselines.search import tree_of_thoughts, verbalized_sampling

Baseline = Callable[..., BaselineResult]

_BASELINES: dict[str, Baseline] = {
    **DECODING_BASELINES,
    "self_consistency": self_consistency,
    "tot": tree_of_thoughts,
    "verbalized_sampling": verbalized_sampling,
    "funsearch": funsearch,
    "promptbreeder": promptbreeder,
    "evoprompt": evoprompt,
    "eureka": eureka,
    "uot": universe_of_thoughts,
}

BASELINE_NAMES: tuple[str, ...] = tuple(_BASELINES)

BASELINE_COUNT_PAPER = 15

TASK_COMPATIBILITY: Mapping[str, frozenset[str]] = {
    "funsearch": frozenset(
        {"math500", "aime", "livecodebench", "humaneval_plus", "llmsrbench"}
    ),
    "eureka": frozenset({"livecodebench", "humaneval_plus"}),
}


def get_baseline(name: str) -> Baseline:
    """The arm registered under `name`."""
    try:
        return _BASELINES[name]
    except KeyError:
        raise KeyError(
            f"unknown baseline {name!r}; have {', '.join(BASELINE_NAMES)}"
        ) from None


def compatible(name: str, benchmark: str) -> bool:
    """Whether `name` is run on `benchmark`, or the paper prints "--" there."""
    allowed = TASK_COMPATIBILITY.get(name)
    return allowed is None or benchmark in allowed
