"""Operator policy pi_theta, Eq. (7)."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.special import logsumexp

_STD_TOL = 1e-12


class OperatorPolicy:
    """Sliding-window exponential-weights policy over operator names."""

    __slots__ = ("_index", "_log_w", "_rewards", "eta", "names", "temperature", "window")

    def __init__(
        self,
        names: Sequence[str],
        eta: float = 0.1,
        window: int = 8,
        temperature: float = 1.0,
    ) -> None:
        names = tuple(names)
        if not names:
            raise ValueError("policy needs at least one operator")
        if len(set(names)) != len(names):
            raise ValueError("operator names must be unique")
        if window < 1:
            raise ValueError("advantage window must be at least one application")
        if temperature <= 0.0:
            raise ValueError("temperature must be positive")
        self.names = names
        self.eta = float(eta)
        self.window = int(window)
        self.temperature = float(temperature)
        self._index = {name: i for i, name in enumerate(names)}
        self._log_w = np.zeros(len(names), dtype=np.float64)
        self._rewards: dict[str, deque[float]] = {
            name: deque(maxlen=self.window) for name in names
        }

    def __len__(self) -> int:
        return len(self.names)

    def probabilities(self, allowed: Sequence[str] | None = None) -> np.ndarray:
        """Current pi_theta: the normalised exponential weights of Eq. (7)."""
        scaled = self._log_w / self.temperature
        p = np.exp(scaled - logsumexp(scaled))
        if allowed is None:
            return p
        keep = np.array([name in set(allowed) for name in self.names], dtype=bool)
        if not keep.any():
            raise ValueError("no operator left in the catalog")
        p = np.where(keep, p, 0.0)
        total = p.sum()
        return p / total if total > 0.0 else keep / keep.sum()

    def sample(
        self, rng: np.random.Generator, allowed: Sequence[str] | None = None
    ) -> str:
        """Draw one operator name from pi_theta over `allowed`, or all of it."""
        p = self.probabilities(allowed)
        return self.names[int(rng.choice(len(self.names), p=p))]

    def observe(self, name: str, reward: float) -> None:
        """Record the reward of one application of `name`."""
        self._rewards[self._checked(name)].append(float(reward))

    def update(self, name: str) -> float:
        """Apply Eq. (7) for `name` and return the advantage that was used."""
        rewards = self._rewards[self._checked(name)]
        if len(rewards) < 2:
            return 0.0
        window = np.fromiter(rewards, dtype=np.float64, count=len(rewards))
        std = float(window.std(ddof=1))
        if not std > _STD_TOL:
            return 0.0
        advantage = float((window.mean() - self.baseline()) / std)
        self._log_w[self._index[name]] += self.eta * advantage
        self._log_w -= logsumexp(self._log_w)
        return advantage

    def baseline(self) -> float:
        """Mean reward over every operator's window."""
        values = [r for window in self._rewards.values() for r in window]
        return float(np.mean(values)) if values else 0.0

    def counts(self) -> dict[str, int]:
        return {name: len(window) for name, window in self._rewards.items()}

    def state_dict(self) -> dict[str, Any]:
        return {
            "names": list(self.names),
            "eta": self.eta,
            "window": self.window,
            "temperature": self.temperature,
            "log_weights": self._log_w.tolist(),
            "rewards": {name: list(w) for name, w in self._rewards.items()},
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        names = tuple(state["names"])
        if names != self.names:
            raise ValueError(f"state is for operators {names}, policy holds {self.names}")
        self.eta = float(state["eta"])
        self.window = int(state["window"])
        self.temperature = float(state["temperature"])
        self._log_w = np.asarray(state["log_weights"], dtype=np.float64)
        self._rewards = {
            name: deque(state["rewards"].get(name, ()), maxlen=self.window)
            for name in self.names
        }

    def _checked(self, name: str) -> str:
        if name not in self._index:
            raise KeyError(f"unknown operator {name!r}")
        return name
