"""Run configuration."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"
ASSET_DIR = REPO_ROOT / "assets"
PROMPT_DIR = REPO_ROOT / "prompts"
SCHEMA_DIR = REPO_ROOT / "schemas"

SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)


@dataclass(slots=True)
class SamplingConfig:
    alpha: float = 1.6
    beta: float = 0.0
    gamma_init: float = 0.3
    delta: float = 0.0
    gamma_min: float = 0.02
    gamma_max: float = 3.0
    rho_max: float = 8.0
    ks_alpha: float = 0.05
    ks_window: int = 64
    hill_exponent: float = 2.0 / 3.0
    ks_bootstrap: int = 10_000


@dataclass(slots=True)
class ControllerConfig:
    kp: float = 0.50
    ki: float = 0.10
    window: int = 8
    setpoint: float = 0.22
    lambda_min: float = 0.05
    lambda_max: float = 0.40
    probe_steps: int = 16
    refresh_every: int = 8
    epsilon_div: float = 1e-6


@dataclass(slots=True)
class BanditConfig:
    eta: float = 0.1
    window: int = 8
    temperature: float = 1.0


@dataclass(slots=True)
class DistanceConfig:
    sinkhorn_iters: int = 50
    sinkhorn_eps: float = 0.01
    encoder: str = "sentence"
    encoder_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    encoder_dim: int = 64
    degree_scale: float = 1.0


@dataclass(slots=True)
class NoveltyConfig:
    corpus_passages: int = 200
    threshold: float = 0.50
    normalise: str = "per_token"
    thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "math_answer": 0.50,
            "math_proof": 0.60,
            "code": 0.50,
            "creativity": 0.30,
            "discovery": 0.30,
        }
    )


@dataclass(slots=True)
class ObjectiveConfig:
    lambda_coverage: float = 1.0
    lambda_compression: float = 0.5
    lambda_verifier: float = 1.0


@dataclass(slots=True)
class OperatorConfig:
    tau_mu: float = 0.6
    levels: tuple[str, ...] = ("token", "mutation", "crossover")
    enabled: tuple[str, ...] = ()
    buffer_size: int = 64


@dataclass(slots=True)
class RunConfig:
    budget: int = 64
    seed: int = 1
    benchmark: str = "math500"
    backend: str = "mock"
    backend_model: str = "Qwen/Qwen2.5-7B-Instruct"
    reference_model: str = "Qwen/Qwen2.5-3B-Instruct"
    parser_retries: int = 3
    max_problems: int | None = None
    out_dir: str = "runs"
    save_traces: bool = True


@dataclass(slots=True)
class Config:
    run: RunConfig = field(default_factory=RunConfig)
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)
    bandit: BanditConfig = field(default_factory=BanditConfig)
    distance: DistanceConfig = field(default_factory=DistanceConfig)
    novelty: NoveltyConfig = field(default_factory=NoveltyConfig)
    objective: ObjectiveConfig = field(default_factory=ObjectiveConfig)
    operators: OperatorConfig = field(default_factory=OperatorConfig)
    decoding: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(
        cls, path: str | Path | None = None, overrides: Mapping[str, Any] | None = None
    ) -> Config:
        data: dict[str, Any] = {}
        if path is not None:
            data = _read_yaml(Path(path))
            merged: dict[str, Any] = {}
            for parent in reversed(list(_inherit_chain(Path(path), data))):
                merged = _deep_merge(merged, parent)
            data = _deep_merge(merged, data)
        cfg = cls.from_dict(data)
        if cfg.decoding == {}:
            cfg.decoding = _read_yaml(CONFIG_DIR / "decoding.yaml")
        if overrides:
            cfg.apply(overrides)
        return cfg

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Config:
        cfg = cls()
        blocks = {
            "run": cfg.run,
            "sampling": cfg.sampling,
            "controller": cfg.controller,
            "bandit": cfg.bandit,
            "distance": cfg.distance,
            "novelty": cfg.novelty,
            "objective": cfg.objective,
            "operators": cfg.operators,
        }
        for name, block in blocks.items():
            for key, value in (data.get(name) or {}).items():
                if not hasattr(block, key):
                    raise KeyError(f"unknown config key {name}.{key}")
                if isinstance(getattr(block, key), tuple) and isinstance(value, list):
                    value = tuple(value)
                setattr(block, key, value)
        cfg.decoding = copy.deepcopy(dict(data.get("decoding") or {}))
        cfg.extra = {
            k: copy.deepcopy(v)
            for k, v in data.items()
            if k not in blocks and k != "decoding" and k != "inherit"
        }
        return cfg

    def apply(self, overrides: Mapping[str, Any]) -> Config:
        """Apply dotted overrides, e.g. {"sampling.alpha": 1.4, "run.seed": 3}."""
        for dotted, value in overrides.items():
            head, _, tail = dotted.partition(".")
            if not tail:
                self.extra[head] = value
                continue
            block = getattr(self, head, None)
            if block is None:
                raise KeyError(f"unknown config block {head!r}")
            if isinstance(block, dict):
                _set_dotted(block, tail, value)
                continue
            if not hasattr(block, tail):
                raise KeyError(f"unknown config key {dotted!r}")
            current = getattr(block, tail)
            if isinstance(current, tuple) and isinstance(value, list):
                value = tuple(value)
            setattr(block, tail, value)
        return self

    def resolved(self) -> dict[str, Any]:
        out = {
            name: asdict(getattr(self, name))
            for name in (
                "run",
                "sampling",
                "controller",
                "bandit",
                "distance",
                "novelty",
                "objective",
                "operators",
            )
        }
        out["decoding"] = copy.deepcopy(self.decoding)
        out.update(copy.deepcopy(self.extra))
        return out

    def dump(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.resolved(), sort_keys=True), encoding="utf-8"
        )

    def novelty_threshold(self, family: str) -> float:
        return self.novelty.thresholds.get(family, self.novelty.threshold)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded or {}


def _inherit_chain(path: Path, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Follow `inherit:` links, nearest ancestor last."""
    chain: list[dict[str, Any]] = []
    seen = {path.resolve()}
    parent_ref = data.get("inherit")
    while parent_ref:
        parent_path = (path.parent / str(parent_ref)).resolve()
        if parent_path in seen:
            raise ValueError(f"circular config inheritance at {parent_path}")
        seen.add(parent_path)
        parent = _read_yaml(parent_path)
        chain.append(parent)
        path, parent_ref = parent_path, parent.get("inherit")
    return chain


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _set_dotted(target: dict[str, Any], dotted: str, value: Any) -> None:
    head, _, tail = dotted.partition(".")
    if tail:
        target.setdefault(head, {})
        _set_dotted(target[head], tail, value)
    else:
        target[head] = value
