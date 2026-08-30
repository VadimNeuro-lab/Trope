"""Algorithm 1: multi-level quality-diversity search over structural representations."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from trope.archive import Archive
from trope.backends.base import BudgetExceeded, DecodingParams, MeteredBackend
from trope.buffer import Buffer
from trope.config import Config
from trope.control.divergence import estimate_divergence
from trope.control.pi import PIController
from trope.data.base import Problem
from trope.distance import StructuralDistance
from trope.operators.base import (
    CROSSOVER,
    MUTATION,
    TOKEN,
    Operator,
    Resources,
    well_formed,
)
from trope.parser import Parser, fallback_representation
from trope.rng import RngTree
from trope.runlog import RunLog
from trope.sampling.bandit import OperatorPolicy
from trope.sampling.rejection import RadicalitySampler
from trope.sampling.stable import sample_radicality
from trope.types import Candidate, Representation


@dataclass(slots=True)
class SearchDeps:
    backend: MeteredBackend
    parser: Parser
    operators: tuple[Operator, ...]
    policy: OperatorPolicy
    sampler: RadicalitySampler
    controller: PIController
    distance: StructuralDistance
    novelty: Any
    verifier: Callable[[Problem, str], Any]
    archive: Archive
    resources: Resources
    generator_template: str
    generator_params: DecodingParams = field(default_factory=DecodingParams)

    def by_name(self, name: str) -> Operator:
        for op in self.operators:
            if op.name == name:
                return op
        raise KeyError(name)


@dataclass(slots=True)
class SearchResult:
    problem_id: str
    archive: Archive
    candidates: list[Candidate]
    stats: dict[str, Any]
    parse: dict[str, Any]

    @property
    def best(self) -> Candidate | None:
        return max(self.candidates, key=lambda c: (c.verdict, c.novelty), default=None)

    @property
    def solved(self) -> bool:
        return any(c.meta.get("verified") for c in self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id,
            "solved": self.solved,
            "coverage": self.archive.coverage(),
            "stats": self.stats,
            "parse": self.parse,
            "archive": self.archive.to_dict(),
        }


def run_search(
    problem: Problem,
    deps: SearchDeps,
    cfg: Config,
    seed: int,
    log: RunLog | None = None,
) -> SearchResult:
    rng = RngTree(seed)
    started = time.perf_counter()

    outcome = deps.parser.parse(problem, rng)
    if outcome.failed:
        rep0 = fallback_representation(problem)
        available = tuple(op for op in deps.operators if op.kind == TOKEN)
    else:
        rep0 = outcome.representation
        available = deps.operators
    if not available:
        raise ValueError("no operators available; check operators.levels in the config")

    catalog = tuple(op.name for op in available)
    buffer = Buffer(rep0, capacity=cfg.operators.buffer_size)
    gamma = cfg.sampling.gamma_init
    deps.sampler.set_gamma(gamma)

    stats = _new_stats(len(available))
    stats["parser_failed"] = outcome.failed
    stats["parser_attempts"] = outcome.attempts
    candidates: list[Candidate] = []
    lambda_hat: float | None = None
    budget = cfg.run.budget
    max_attempts = max(4 * budget, budget + 32)

    t = 0
    attempts = 0
    while attempts < max_attempts and deps.backend.generator_calls < budget:
        attempts += 1
        t = deps.backend.generator_calls + 1
        record: dict[str, Any] = {
            "iteration": t,
            "problem_id": problem.id,
            "generator_calls": deps.backend.generator_calls,
        }

        op_name = deps.policy.sample(rng.stream(f"policy/{t}/{attempts}"), catalog)
        op = deps.by_name(op_name)
        record["operator"] = op.name
        record["level"] = op.kind

        parent = buffer.sample(rng.stream(f"seed/{t}/{attempts}"))
        other = (
            buffer.sample(rng.stream(f"pair/{t}/{attempts}"))
            if op.kind == CROSSOVER
            else None
        )

        proposal = _Proposal(deps, op, parent, other, rng, f"{t}/{attempts}")
        draw = deps.sampler.draw(rng.stream(f"radicality/{t}/{attempts}"), proposal)
        edit, rep = proposal.edit, proposal.rep
        record.update(
            z=draw.z,
            radicality=draw.rho,
            gamma=gamma,
            rejections=draw.rejections,
            rejection_vacuous=draw.vacuous,
        )
        stats["rejections"] += draw.rejections
        stats["rejection_vacuous"] += int(draw.vacuous)
        stats["proposals"] += draw.attempts

        record["changed"] = edit.changed
        record["detail"] = edit.detail
        if not edit.changed:
            stats["noops"] += 1
            stats["noop_by_operator"][op.name] = stats["noop_by_operator"].get(op.name, 0) + 1

        params = (
            _token_params(edit.decoding, deps.generator_params)
            if op.kind == TOKEN
            else deps.generator_params
        )
        ok, reason = well_formed(rep)
        record["well_formed"] = ok
        record["wf_reason"] = reason
        if not ok:
            stats["wf_failures"] += 1
            _emit(log, record)
            continue

        d_struct = draw.distance
        record["rep_fingerprint"] = rep.fingerprint()

        record["d_struct"] = d_struct
        record["rep_fingerprint"] = rep.fingerprint()

        prompt = build_generator_prompt(
            deps.generator_template, problem, rep, op.name, edit.detail
        )
        try:
            gen = deps.backend.generate(
                prompt, params, seed=rng.integer(f"gen/{t}"), role="generator"
            )
        except BudgetExceeded:
            break
        stats["generations"] += 1

        nov = deps.novelty.score(gen.text)
        verdict = deps.verifier(problem, gen.text)
        record["novelty"] = nov.value
        record["verdict"] = verdict.value
        record["verified"] = bool(verdict.verified)
        record["answer"] = _answer_excerpt(gen.text)

        candidate = Candidate(
            text=gen.text,
            representation=rep,
            operator=op.name,
            radicality=draw.rho,
            novelty=nov.value,
            verdict=verdict.value,
            iteration=t,
            meta={
                "verified": bool(verdict.verified),
                "detail": verdict.detail,
                "changed": edit.changed,
                "d_struct": d_struct,
                "level": op.kind,
                "prompt_tokens": gen.prompt_tokens,
                "completion_tokens": gen.completion_tokens,
            },
        )
        insert = deps.archive.insert(candidate)
        candidate.descriptor = insert.cell or ()
        record["accepted"] = insert.inserted
        record["descriptor"] = list(insert.cell) if insert.cell else None
        record["reject_reason"] = insert.reason
        candidates.append(candidate)

        if insert.inserted:
            stats["accepted"] += 1
        else:
            stats["rejected"][insert.reason] = stats["rejected"].get(insert.reason, 0) + 1
        if insert.reason not in ("novelty", "verified"):
            buffer.add(rep)

        reward = _reward(cfg, candidate, insert)
        deps.policy.observe(op.name, reward)
        advantage = deps.policy.update(op.name)
        record["reward"] = reward
        record["advantage"] = advantage
        stats["usage"][op.name] = stats["usage"].get(op.name, 0) + 1

        if t % cfg.controller.refresh_every == 0 and t != stats["last_refresh"]:
            stats["last_refresh"] = t
            lambda_hat = _refresh_controller(deps, cfg, rep0, rng, t)
            gamma = deps.controller.update(lambda_hat)
            deps.sampler.set_gamma(gamma)
            stats["controller_updates"] += 1
        record["lambda_struct"] = lambda_hat
        _emit(log, record)

    stats["iterations"] = t
    stats["attempts"] = attempts
    stats["generator_calls"] = deps.backend.generator_calls
    stats["coverage"] = deps.archive.coverage()
    stats["policy"] = deps.policy.state_dict()
    stats["probabilities"] = [float(v) for v in deps.policy.probabilities(catalog)]
    stats["sampler"] = deps.sampler.stats
    stats["band_occupancy"] = deps.controller.band_occupancy()
    stats["gamma_final"] = gamma
    stats["wall_seconds"] = time.perf_counter() - started
    stats["operator_applications"] = stats["proposals"]
    if stats["generations"] + stats["wf_failures"]:
        stats["wf_failure_rate"] = stats["wf_failures"] / (
            stats["generations"] + stats["wf_failures"]
        )
    return SearchResult(problem.id, deps.archive, candidates, stats, outcome.to_dict())


class _Proposal:
    """One operator applied at a radicality, and the displacement it realises."""

    __slots__ = ("deps", "edit", "op", "other", "parent", "rep", "rng", "tag", "tries")

    def __init__(
        self,
        deps: SearchDeps,
        op: Operator,
        parent: Representation,
        other: Representation | None,
        rng: RngTree,
        tag: str,
    ) -> None:
        self.deps = deps
        self.op = op
        self.parent = parent
        self.other = other
        self.rng = rng
        self.tag = tag
        self.tries = 0
        self.edit: Any = None
        self.rep: Representation = parent

    def __call__(self, rho: float) -> float:
        stream = self.rng.stream(f"op/{self.op.name}/{self.tag}/{self.tries}")
        self.tries += 1
        self.edit = self.op.apply(
            self.parent, rho, stream, self.deps.resources, other=self.other
        )
        self.rep = (
            self.parent
            if self.op.kind == TOKEN
            else (self.edit.representation or self.parent)
        )
        return self.deps.distance(self.parent, self.rep)


def build_generator_prompt(
    template: str,
    problem: Problem,
    rep: Representation,
    operator: str,
    detail: str,
) -> str:
    return (
        template.replace("{{PROBLEM}}", problem.text.strip())
        .replace("{{REPRESENTATION}}", rep.to_json())
        .replace("{{OPERATOR}}", operator)
        .replace("{{DETAIL}}", detail or "none")
    )


def _reward(cfg: Config, candidate: Candidate, insert: Any) -> float:
    """Advantage signal for the bandit."""
    coverage_gain = 1.0 if (insert.inserted and not insert.replaced) else 0.0
    return (
        cfg.objective.lambda_verifier * candidate.verdict
        + cfg.objective.lambda_compression * candidate.novelty
        + cfg.objective.lambda_coverage * coverage_gain
    )


def _refresh_controller(
    deps: SearchDeps, cfg: Config, rep0: Representation, rng: RngTree, t: int
) -> float:
    """Re-estimate the divergence rate."""
    structural = tuple(op for op in deps.operators if op.kind != TOKEN)
    if not structural:
        return cfg.controller.setpoint

    def step_fn(rep: Representation, r: np.random.Generator) -> Representation:
        op = structural[int(r.integers(len(structural)))]
        rho = float(sample_radicality(r, cfg.sampling.alpha, deps.sampler.gamma))
        other = rep if op.kind == CROSSOVER else None
        edit = op.apply(rep, rho, r, deps.resources, other=other)
        if not edit.changed or edit.representation is None:
            return rep
        ok, _ = well_formed(edit.representation)
        return edit.representation if ok else rep

    result = estimate_divergence(
        rep0,
        step_fn,
        deps.distance,
        rng.stream(f"probe/{t}"),
        steps=cfg.controller.probe_steps,
        epsilon=cfg.controller.epsilon_div,
    )
    return result.estimate


def _new_stats(n_operators: int) -> dict[str, Any]:
    return {
        "n_operators": n_operators,
        "iterations": 0,
        "generations": 0,
        "operator_applications": 0,
        "noops": 0,
        "noop_by_operator": {},
        "wf_failures": 0,
        "wf_failure_rate": 0.0,
        "accepted": 0,
        "rejected": {},
        "rejections": 0,
        "rejection_vacuous": 0,
        "proposals": 0,
        "last_refresh": -1,
        "controller_updates": 0,
        "usage": {},
    }


def _token_params(
    override: DecodingParams | None, base: DecodingParams
) -> DecodingParams:
    """Apply a token operator's decoding override on top of the generator block."""
    if override is None:
        return base
    return replace(override, max_tokens=base.max_tokens, stop=base.stop)


def _answer_excerpt(text: str, limit: int = 48) -> str:
    """What the candidate concluded, for the search-trace table."""
    from trope.verify.exact_match import extract_answer

    answer = extract_answer(text)
    if answer is None:
        tail = text.strip().splitlines()[-1] if text.strip() else ""
        answer = tail.strip()
    return answer[:limit]


def _emit(log: RunLog | None, record: Mapping[str, Any]) -> None:
    if log is not None:
        log.step(record)


def level_usage(stats: Mapping[str, Any], operators: Sequence[Operator]) -> dict[str, float]:
    """Per-level selection frequency, the quantity in the paper's usage table."""
    kinds = {op.name: op.kind for op in operators}
    counts = {TOKEN: 0, MUTATION: 0, CROSSOVER: 0}
    for name, n in (stats.get("usage") or {}).items():
        counts[kinds.get(name, TOKEN)] += n
    total = sum(counts.values())
    return {k: (100.0 * v / total if total else 0.0) for k, v in counts.items()}
