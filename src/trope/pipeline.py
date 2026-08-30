"""Wiring: a Config plus a dataset become a runnable search."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trope.archive import Archive
from trope.backends.base import CallCounter, DecodingParams, MeteredBackend
from trope.backends.registry import make_backend, make_encoder
from trope.config import PROMPT_DIR, Config
from trope.control.pi import PIController
from trope.corpus import BM25Index, build_corpus, fallback_index
from trope.data.base import Dataset, Problem
from trope.descriptors import LLMTagger, get_descriptor
from trope.distance import StructuralDistance
from trope.novelty import CompressionNovelty
from trope.operators.base import catalog, load_resources
from trope.parser import Parser
from trope.runlog import RunLog
from trope.sampling.bandit import OperatorPolicy
from trope.sampling.rejection import RadicalitySampler
from trope.search import SearchDeps, SearchResult, run_search
from trope.verify.base import get_verifier


@dataclass(slots=True)
class Pipeline:
    cfg: Config
    raw_backend: Any
    raw_reference: Any
    operators: tuple
    resources: Any
    distance: StructuralDistance
    index: BM25Index
    generator_template: str
    totals: CallCounter = field(default_factory=CallCounter)

    @classmethod
    def build(cls, cfg: Config, problems: Iterable[Problem] | None = None) -> Pipeline:
        problems = tuple(problems or ())
        raw = make_backend(
            cfg.run.backend, model=cfg.run.backend_model, problems=problems
        )
        if cfg.run.backend == "mock" or not cfg.run.reference_model:
            raw_ref = raw
        else:
            raw_ref = make_backend(
                cfg.run.backend, model=cfg.run.reference_model, problems=problems
            )
        encoder = make_encoder(
            cfg.distance.encoder,
            dim=cfg.distance.encoder_dim,
            model=cfg.distance.encoder_model,
        )
        return cls(
            cfg=cfg,
            raw_backend=raw,
            raw_reference=raw_ref,
            operators=catalog(
                levels=cfg.operators.levels, enabled=cfg.operators.enabled or None
            ),
            resources=load_resources(
                encoder=encoder,
                tau_mu=cfg.operators.tau_mu,
                rho_max=cfg.sampling.rho_max,
                token_params=(cfg.decoding or {}).get("token_operators", {}),
            ),
            distance=StructuralDistance(encoder, cfg.distance),
            index=fallback_index(),
            generator_template=(PROMPT_DIR / "generator.txt").read_text(encoding="utf-8"),
        )

    def deps_for(self, problem: Problem) -> tuple[SearchDeps, CallCounter]:
        cfg = self.cfg
        counter = CallCounter()
        backend = MeteredBackend(self.raw_backend, counter, budget=cfg.run.budget)
        reference = MeteredBackend(
            self.raw_reference, counter, budget=None, role="reference"
        )
        decoding = cfg.decoding or {}

        corpus = build_corpus(
            problem,
            self.index,
            top_k=cfg.novelty.corpus_passages,
        )
        verifier = get_verifier(problem, backend=backend.for_role("judge"))
        return (
            SearchDeps(
                backend=backend,
                parser=Parser(
                    backend,
                    retries=cfg.run.parser_retries,
                    params=_params(decoding.get("parser"), temperature=0.0),
                ),
                operators=self.operators,
                policy=OperatorPolicy(
                    [op.name for op in self.operators],
                    eta=cfg.bandit.eta,
                    window=cfg.bandit.window,
                    temperature=cfg.bandit.temperature,
                ),
                sampler=RadicalitySampler(
                    alpha=cfg.sampling.alpha,
                    gamma_init=cfg.sampling.gamma_init,
                    ks_alpha=cfg.sampling.ks_alpha,
                    window=cfg.sampling.ks_window,
                    rho_max=cfg.sampling.rho_max,
                    gamma_min=cfg.sampling.gamma_min,
                    gamma_max=cfg.sampling.gamma_max,
                ),
                controller=PIController(
                    kp=cfg.controller.kp,
                    ki=cfg.controller.ki,
                    window=cfg.controller.window,
                    setpoint=cfg.controller.setpoint,
                    gamma_init=cfg.sampling.gamma_init,
                    gamma_min=cfg.sampling.gamma_min,
                    gamma_max=cfg.sampling.gamma_max,
                    lambda_min=cfg.controller.lambda_min,
                    lambda_max=cfg.controller.lambda_max,
                ),
                distance=self.distance,
                novelty=CompressionNovelty(
                    reference,
                    corpus,
                    normalise=cfg.novelty.normalise,
                    window_tokens=int(
                        (decoding.get("reference_lm") or {}).get("window_tokens", 512)
                    ),
                ),
                verifier=verifier,
                archive=Archive(
                    get_descriptor(
                        cfg.run.benchmark,
                        tagger=LLMTagger(backend.for_role("tagger"), seed=cfg.run.seed),
                        encoder=self.distance.encoder,
                    ),
                    novelty_threshold=cfg.novelty_threshold(problem.family),
                ),
                resources=self.resources,
                generator_template=self.generator_template,
                generator_params=_params(decoding.get("generator"), temperature=0.7),
            ),
            counter,
        )

    def run(
        self,
        dataset: Dataset,
        *,
        seed: int | None = None,
        out_dir: str | Path | None = None,
    ) -> list[SearchResult]:
        cfg = self.cfg
        seed = cfg.run.seed if seed is None else seed
        root = Path(
            out_dir or Path(cfg.run.out_dir) / f"{cfg.run.benchmark}-seed{seed}"
        )
        results: list[SearchResult] = []
        with RunLog.open(
            root,
            config=cfg.resolved(),
            backend=cfg.run.backend,
            models={
                "backbone": cfg.run.backend_model,
                "reference": cfg.run.reference_model,
            },
            extra={
                "seed": seed,
                "dataset": dataset.name,
                "n_problems": len(dataset),
                "distance": self.distance.provenance(),
            },
        ) as log:
            for problem in dataset:
                deps, counter = self.deps_for(problem)
                results.append(run_search(problem, deps, cfg, seed=seed, log=log))
                self._accumulate(counter)
            log.write_json("results.json", [r.to_dict() for r in results])
            log.write_json("summary.json", summarise(results, len(dataset)))
            log.ledger(self.totals)
        return results

    def _accumulate(self, counter: CallCounter) -> None:
        for role, n in counter.counts.items():
            self.totals.counts[role] = self.totals.counts.get(role, 0) + n
        for role, n in counter.tokens.items():
            self.totals.tokens[role] = self.totals.tokens.get(role, 0) + n


def summarise(results: list[SearchResult], n_problems: int) -> dict[str, Any]:
    if not results:
        return {"n_problems": 0}
    solved = sum(1 for r in results if r.solved)
    coverage = [r.archive.coverage() for r in results]
    novelty = [c.novelty for r in results for c in r.candidates]
    return {
        "n_problems": n_problems,
        "solved": solved,
        "solve_rate": solved / len(results),
        "mean_coverage": sum(coverage) / len(coverage),
        "mean_novelty": (sum(novelty) / len(novelty)) if novelty else 0.0,
        "generator_calls": sum(r.stats["generator_calls"] for r in results),
        "parser_failures": sum(1 for r in results if r.stats.get("parser_failed")),
        "wf_failure_rate": _ratio(
            sum(r.stats["wf_failures"] for r in results),
            sum(r.stats["operator_applications"] for r in results),
        ),
        "noop_rate": _ratio(
            sum(r.stats["noops"] for r in results),
            sum(r.stats["iterations"] for r in results),
        ),
    }


def _ratio(num: int, den: int) -> float:
    return num / den if den else 0.0


def _params(block: dict | None, *, temperature: float) -> DecodingParams:
    block = block or {}
    fields = DecodingParams.__dataclass_fields__
    kwargs = {k: v for k, v in block.items() if k in fields and v is not None}
    kwargs.setdefault("temperature", temperature)
    if isinstance(kwargs.get("stop"), list):
        kwargs["stop"] = tuple(kwargs["stop"])
    return DecodingParams(**kwargs)
