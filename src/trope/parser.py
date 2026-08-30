"""Parser Phi: one LLM call per problem, JSON-constrained, with a retry budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trope.backends.base import DecodingParams, MeteredBackend
from trope.config import PROMPT_DIR
from trope.data.base import Problem
from trope.rng import RngTree
from trope.types import Representation, SchemaError
from trope.validation import parse_representation


@dataclass(slots=True)
class ParseOutcome:
    representation: Representation | None
    attempts: int
    errors: tuple[str, ...] = ()
    raw: tuple[str, ...] = ()

    @property
    def failed(self) -> bool:
        return self.representation is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "failed": self.failed,
            "attempts": self.attempts,
            "errors": list(self.errors),
            "representation": (
                self.representation.to_dict() if self.representation else None
            ),
        }


@dataclass(slots=True)
class Parser:
    backend: MeteredBackend
    template: str = ""
    retries: int = 3
    params: DecodingParams = field(
        default_factory=lambda: DecodingParams(temperature=0.0, max_tokens=1024)
    )
    stats: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.template:
            self.template = load_template()

    def build_prompt(self, problem: Problem, errors: tuple[str, ...] = ()) -> str:
        prompt = self.template.replace("{{PROBLEM}}", problem.text.strip())
        if errors:
            feedback = "\n".join(f"- {e}" for e in errors)
            prompt += (
                "\n\nThe previous attempt failed validation:\n"
                f"<validator_error>\n{feedback}\n</validator_error>\n"
                "Return corrected JSON only."
            )
        return prompt

    def parse(self, problem: Problem, rng: RngTree) -> ParseOutcome:
        errors: tuple[str, ...] = ()
        seen_errors: list[str] = []
        raw: list[str] = []
        for attempt in range(1, self.retries + 1):
            prompt = self.build_prompt(problem, errors)
            seed = rng.integer(f"parser/{problem.id}/{attempt}")
            gen = self.backend.generate(prompt, self.params, seed=seed, role="parser")
            raw.append(gen.text)
            try:
                rep = parse_representation(gen.text, source_text=problem.text)
            except SchemaError as exc:
                errors = (str(exc),)
                seen_errors.extend(errors)
                self._bump("retries")
                continue
            self._bump("ok")
            return ParseOutcome(rep, attempt, tuple(seen_errors), tuple(raw))
        self._bump("failures")
        return ParseOutcome(None, self.retries, tuple(seen_errors), tuple(raw))

    def _bump(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    @property
    def failure_rate(self) -> float:
        total = self.stats.get("ok", 0) + self.stats.get("failures", 0)
        return self.stats.get("failures", 0) / total if total else 0.0


def load_template(path: str | Path | None = None) -> str:
    path = Path(path) if path else PROMPT_DIR / "parser.txt"
    return path.read_text(encoding="utf-8")


def fallback_representation(problem: Problem) -> Representation:
    """What TROPE searches over when the parser fails three times."""
    from trope.types import Assumption, Entity, Goal

    return Representation(
        entities=(Entity(id="problem", type="input", sort="", label=problem.id),),
        relations=(),
        assumptions=(Assumption(text="the problem statement is exact as given", load_bearing=True),),
        goal=Goal(objective=problem.text.strip()[:400] or "solve the problem"),
        frame="unspecified",
        source_text=problem.text,
    )
