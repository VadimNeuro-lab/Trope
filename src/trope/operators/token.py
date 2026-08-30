"""Token-level operators."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from trope.backends.base import DecodingParams
from trope.operators.base import (
    TOKEN,
    EditResult,
    Resources,
    clamp_rho,
    register,
    unit_rho,
)
from trope.types import Representation


def _params(res: Resources, name: str) -> Mapping[str, float]:
    return res.token_params.get(name, {})


class TemperatureScaling:
    """T = T_0 + unit(rho) * (T_max - T_0)."""

    name = "temperature_scaling"
    kind = TOKEN
    arity = 1

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        cfg = _params(res, self.name)
        t_0 = float(cfg.get("T0", 0.5))
        t_max = float(cfg.get("T_max", 1.5))
        temperature = t_0 + unit_rho(rho, res) * (t_max - t_0)
        return EditResult(
            decoding=DecodingParams(temperature=temperature),
            detail=f"temperature={temperature:.4f}",
        )


class NucleusTruncation:
    """p = clip(1 - clamp(rho) / R_max, p_min, 1)."""

    name = "nucleus_truncation"
    kind = TOKEN
    arity = 1

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        cfg = _params(res, self.name)
        r_max = float(cfg.get("R_max", res.rho_max))
        p_min = float(cfg.get("p_min", 0.05))
        raw = 1.0 - clamp_rho(rho, res) / r_max if r_max > 0 else p_min
        top_p = float(min(max(raw, p_min), 1.0))
        return EditResult(
            decoding=DecodingParams(top_p=top_p),
            detail=f"top_p={top_p:.4f}",
        )


class EntropyBounded:
    """top-H sampling with an entropy budget in bits proportional to rho."""

    name = "entropy_bounded"
    kind = TOKEN
    arity = 1

    def apply(
        self,
        rep: Representation,
        rho: float,
        rng: np.random.Generator,
        res: Resources,
        *,
        other: Representation | None = None,
    ) -> EditResult:
        cfg = _params(res, self.name)
        per_rho = float(cfg.get("bits_per_rho", 1.0))
        min_bits = float(cfg.get("min_bits", 0.15))
        max_bits = float(cfg.get("max_bits", 6.0))
        bits = float(min(max(per_rho * float(rho), min_bits), max_bits))
        return EditResult(
            decoding=DecodingParams(entropy_budget=bits),
            detail=f"entropy_budget={bits:.4f} bits",
        )


register(TemperatureScaling())
register(NucleusTruncation())
register(EntropyBounded())
