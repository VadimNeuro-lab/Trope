"""The rejection loop of Algorithm 1."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from trope.sampling.stable import folded_stable_cdf, sample_stable


class RejectionLoopStalled(RuntimeError):
    """The unbounded repeat-until drew `attempt_ceiling` times without accepting."""


@dataclass(frozen=True, slots=True)
class Draw:
    z: float
    rho: float
    rejections: int
    attempts: int
    vacuous: bool
    ks_stat: float
    distance: float = 0.0
    reason: str = ""


class RadicalitySampler:
    """Draws rho = |Z| under Algorithm 1's acceptance test on the recent window."""

    def __init__(
        self,
        alpha: float,
        gamma_init: float = 0.3,
        ks_alpha: float = 0.05,
        window: int = 64,
        rho_max: float = 8.0,
        gamma_min: float = 0.02,
        gamma_max: float = 3.0,
        *,
        attempt_ceiling: int = 10_000,
        stall_window: int = 16,
    ) -> None:
        if window < 1:
            raise ValueError(f"window must be positive, got {window}")
        if not 0.0 < ks_alpha < 1.0:
            raise ValueError(f"ks_alpha must lie in (0, 1), got {ks_alpha}")
        if not 0.0 < gamma_min <= gamma_max:
            raise ValueError("need 0 < gamma_min <= gamma_max")
        if attempt_ceiling < 1:
            raise ValueError(f"attempt_ceiling must be positive, got {attempt_ceiling}")

        self.alpha = float(alpha)
        self.ks_alpha = float(ks_alpha)
        self.rho_max = float(rho_max)
        self.gamma_min = float(gamma_min)
        self.gamma_max = float(gamma_max)
        self.gamma = float(min(max(gamma_init, gamma_min), gamma_max))
        self.attempt_ceiling = int(attempt_ceiling)
        self.stall_window = int(stall_window)

        self._window: deque[float] = deque(maxlen=int(window))
        self._raw: deque[float] = deque(maxlen=int(window))
        self._provisional = False
        self._draws = 0
        self._attempts = 0
        self._vacuous = 0
        self._tested = 0
        self._zero = 0
        self._saturated = 0

    def set_gamma(self, gamma: float) -> float:
        """Install the controller's new scale, clamped to the stable law's domain."""
        self.gamma = float(min(max(gamma, self.gamma_min), self.gamma_max))
        return self.gamma

    def observe_distance(self, d_struct: float) -> None:
        """Record a realised d_struct in the rolling window Algorithm 1 tests."""
        value = self._checked(d_struct, "d_struct")
        if value <= 0.0:
            self._zero += 1
            if self._provisional and self._window:
                self._window.pop()
                self._raw.pop()
                self._provisional = False
            return
        if self._provisional and self._window:
            self._window[-1] = self._transform(value)
            self._raw[-1] = value
            self._provisional = False
            return
        self._raw.append(value)
        self._window.append(self._transform(value))

    def observe(self, rho: float) -> None:
        """Record a magnitude in the window without drawing."""
        self.observe_distance(rho)

    def draw(
        self,
        rng: np.random.Generator,
        propose: Callable[[float], float] | None = None,
    ) -> Draw:
        """One accepted proposal."""
        history = np.array(self._window, dtype=float)
        critical = self._critical(history.size + 1)
        vacuous = _min_statistic(history) > critical
        rejections = 0
        seen: set[float] = set()
        since_new = 0

        for attempts in range(1, self.attempt_ceiling + 1):
            z = float(sample_stable(rng, self.alpha, 0.0, self.gamma, 0.0))
            self._attempts += 1
            rho = abs(z)
            value = rho if propose is None else self._checked(propose(rho), "d_struct")
            if value <= 0.0:
                return self._record(
                    z,
                    value,
                    0.0,
                    rejections,
                    attempts,
                    reason="no-displacement",
                    provisional=False,
                )
            stat = _statistic(history, self._transform(value))
            if vacuous or stat <= critical:
                return self._record(
                    z,
                    value,
                    stat,
                    rejections,
                    attempts,
                    reason="window" if vacuous else "",
                    provisional=propose is None,
                )
            key = round(value, 12)
            since_new = 0 if key not in seen else since_new + 1
            seen.add(key)
            if since_new >= self.stall_window:
                return self._record(
                    z,
                    value,
                    stat,
                    rejections,
                    attempts,
                    reason="exhausted",
                    provisional=propose is None,
                )
            rejections = attempts

        raise RejectionLoopStalled(self._stall_message(history, critical))

    def _record(
        self,
        z: float,
        value: float,
        stat: float,
        rejections: int,
        attempts: int,
        *,
        reason: str,
        provisional: bool,
    ) -> Draw:
        rho = abs(z)
        self.observe_distance(value)
        self._provisional = provisional and value > 0.0
        self._draws += 1
        self._vacuous += int(bool(reason))
        if rho > self.rho_max:
            self._saturated += 1
        if not reason:
            self._tested += 1
        return Draw(
            z=z,
            rho=rho,
            rejections=rejections,
            attempts=attempts,
            vacuous=bool(reason),
            ks_stat=stat,
            distance=value,
            reason=reason,
        )

    def _transform(self, value: float) -> float:
        """Probability-integral transform at the scale in force."""
        return float(folded_stable_cdf(value, self.alpha, self.gamma))

    @staticmethod
    def _checked(value: float, name: str) -> float:
        out = float(value)
        if out < 0.0 or not math.isfinite(out):
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
        return out

    def _critical(self, n: int) -> float:
        """Asymptotic Kolmogorov critical value at level ks_alpha."""
        return math.sqrt(-0.5 * math.log(self.ks_alpha / 2.0)) / math.sqrt(n)

    def _stall_message(self, history: np.ndarray, critical: float) -> str:
        return (
            f"Algorithm 1's repeat-until drew {self.attempt_ceiling} times without "
            f"accepting on a window of {history.size} d_struct values; the smallest "
            f"statistic any draw could reach is {_min_statistic(history):.4f} against "
            f"a critical value of {critical:.4f} at tau_KS = {self.ks_alpha}. That is "
            f"below the critical value, so the loop was not vacuous and should have "
            f"terminated; the accepting set is small enough that it did not. Report "
            f"this with the window: gamma = {self.gamma:.4f}, alpha = {self.alpha}."
        )

    @property
    def window(self) -> np.ndarray:
        """The rolling window, mapped through the folded CDF."""
        return np.array(self._window, dtype=float)

    @property
    def distance_window(self) -> np.ndarray:
        """Raw d_struct values, in the order they were observed."""
        return np.array(self._raw, dtype=float)

    @property
    def stats(self) -> dict[str, float]:
        """Draw counts."""
        draws = max(self._draws, 1)
        attempts = max(self._attempts, 1)
        tested_attempts = max(self._attempts - (self._draws - self._tested), 1)
        return {
            "draws": float(self._draws),
            "tested": float(self._tested),
            "attempts": float(self._attempts),
            "acceptance_rate": self._tested / tested_attempts if self._tested else 0.0,
            "rejection_rate": 1.0 - self._draws / attempts,
            "mean_rejections": (self._attempts - self._draws) / draws,
            "vacuous": float(self._vacuous),
            "zero_displacement": float(self._zero),
            "saturated": float(self._saturated),
            "window_size": float(len(self._window)),
            "gamma": self.gamma,
        }


def _statistic(history: np.ndarray, u: float) -> float:
    """KS statistic against the uniform of `history` with `u` appended."""
    sample = np.empty(history.size + 1, dtype=float)
    sample[:-1] = history
    sample[-1] = u
    sample.sort()
    n = sample.size
    upper = np.arange(1, n + 1, dtype=float) / n - sample
    lower = sample - np.arange(0, n, dtype=float) / n
    return float(max(upper.max(), lower.max()))


def _min_statistic(history: np.ndarray) -> float:
    """The smallest statistic any single free point can produce."""
    w = np.sort(history)
    n = w.size + 1
    candidates = [0.0, 1.0]
    edges = np.concatenate(([0.0], w, [1.0]))
    for k in range(1, n + 1):
        lo, hi = edges[k - 1], edges[k]
        candidates.append(min(max((2 * k - 1) / (2 * n), lo), hi))
    return min(_statistic(history, float(u)) for u in candidates)
