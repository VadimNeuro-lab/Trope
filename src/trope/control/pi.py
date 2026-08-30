"""PI controller on the radicality scale gamma, Eq. (9)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import NamedTuple


@dataclass(frozen=True, slots=True)
class ControlStep:
    """One controller update, kept so the band statistics can be recomputed."""

    lambda_hat: float
    error: float
    integral: float
    gamma: float
    saturated: bool
    in_band: bool


class BandOccupancy(NamedTuple):
    """Fraction of observed lambda_hat inside the band, as the paper reports it."""

    overall: float
    steady: float
    n: int
    n_steady: int


class PIController:
    def __init__(
        self,
        kp: float = 0.50,
        ki: float = 0.10,
        window: int = 8,
        setpoint: float = 0.22,
        *,
        gamma_init: float = 0.3,
        gamma_min: float = 0.02,
        gamma_max: float = 3.0,
        lambda_min: float = 0.05,
        lambda_max: float = 0.40,
    ) -> None:
        if window < 1:
            raise ValueError("integral window must be at least one step")
        if not gamma_min > 0.0:
            raise ValueError(
                "gamma_min must be positive; the stable scale cannot be zero"
            )
        if gamma_max < gamma_min:
            raise ValueError("gamma_max must not be below gamma_min")
        if lambda_max < lambda_min:
            raise ValueError("lambda_max must not be below lambda_min")
        self.kp = float(kp)
        self.ki = float(ki)
        self.window = int(window)
        self.setpoint = float(setpoint)
        self.gamma_min = float(gamma_min)
        self.gamma_max = float(gamma_max)
        self.lambda_min = float(lambda_min)
        self.lambda_max = float(lambda_max)
        self.gamma = self._settle(float(gamma_init))
        self.errors: deque[float] = deque(maxlen=self.window)
        self.history: list[ControlStep] = []

    def update(self, lambda_hat: float) -> float:
        """Feed one divergence estimate, return the scale for the next draws."""
        estimate = float(lambda_hat)
        error = self.setpoint - estimate
        self.errors.append(error)
        integral = sum(self.errors)
        proposed = self.gamma + self.kp * error + self.ki * integral
        self.gamma = min(max(proposed, self.gamma_min), self.gamma_max)
        self.history.append(
            ControlStep(
                lambda_hat=estimate,
                error=error,
                integral=integral,
                gamma=self.gamma,
                saturated=proposed != self.gamma,
                in_band=self.lambda_min <= estimate <= self.lambda_max,
            )
        )
        return self.gamma

    def band_occupancy(self) -> BandOccupancy:
        """Occupancy over all steps and over the steady state (t > W)."""
        flags = [step.in_band for step in self.history]
        steady = flags[self.window :]
        return BandOccupancy(
            overall=_fraction(flags),
            steady=_fraction(steady),
            n=len(flags),
            n_steady=len(steady),
        )

    def reset(self, gamma: float | None = None) -> None:
        self.gamma = self._settle(self.gamma if gamma is None else float(gamma))
        self.errors.clear()
        self.history.clear()

    def _settle(self, gamma: float) -> float:
        return min(max(gamma, self.gamma_min), self.gamma_max)


def _fraction(flags: list[bool]) -> float:
    return sum(flags) / len(flags) if flags else 0.0
