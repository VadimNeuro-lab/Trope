"""TROPE: typed representations and operators for problem editing in LLM reasoning."""

from trope.config import SEEDS, Config
from trope.types import (
    Assumption,
    Candidate,
    EditRecord,
    Entity,
    Goal,
    Relation,
    Representation,
)

__version__ = "1.0.0"

__all__ = [
    "SEEDS",
    "Assumption",
    "Candidate",
    "Config",
    "EditRecord",
    "Entity",
    "Goal",
    "Relation",
    "Representation",
    "__version__",
]


def __getattr__(name: str):
    if name == "Pipeline":
        from trope.pipeline import Pipeline

        return Pipeline
    if name == "run_search":
        from trope.search import run_search

        return run_search
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
