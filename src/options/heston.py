"""Heston Monte Carlo helpers for American option pricing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import numpy as np


Array = np.ndarray


@dataclass
class HestonParameters:
    kappa: float = 1.5
    theta: float = 0.04
    sigma: float = 0.3
    rho: float = -0.6
    v0: float = 0.04

    def clamp(self) -> "HestonParameters":
        return HestonParameters(
            kappa=max(self.kappa, 1e-6),
            theta=max(self.theta, 1e-8),
            sigma=max(self.sigma, 1e-6),
            rho=float(np.clip(self.rho, -0.999, 0.999)),
            v0=max(self.v0, 1e-8),
        )


@dataclass
class HestonAmericanPricer:
    paths: int = 1500
    steps: int = 64
    seed: Optional[int] = 1234
    antithetic: bool = True

    def price(
        self,
        option_type: str,
        spot: float,
        strike: float,
        ttm: float,
        rate: float,
        params: HestonParameters,
    ) -> float:
        opt_type = option_type.lower().strip()[0]
        if opt_type not in {"c", "p"}:
            raise ValueError("Unsupported option type")
        if spot <= 0 or strike <= 0 or ttm <= 0:
            return 0.0

        pricer_params = params.clamp()
        rng = np.random.default_rng(self.seed)
        paths = self.paths * (2 if self.antithetic else 1)
        spot_paths, var_paths = self._simulate_paths(spot, ttm, rate, pricer_params, paths, rng)
        return float(self._lsm(opt_type, strike, rate, ttm, spot_paths))

    def _simulate_paths(
        self,
        spot: float,
        ttm: float,
        rate: float,
        params: HestonParameters,
        paths: int,
        rng: np.random.Generator,
    ) -> Tuple[Array, Array]:
        steps = max(self.steps, 1)
        dt = ttm / steps
        sqrt_dt = np.sqrt(dt)

        s_paths = np.empty((paths, steps + 1))
        v_paths = np.empty((paths, steps + 1))
        s_paths[:, 0] = spot
        v_paths[:, 0] = params.v0

        rho = params.rho
        kappa = params.kappa
        theta = params.theta
        sigma = params.sigma
        drift = rate

        half = paths // 2 if self.antithetic else 0

        for step in range(steps):
            z1 = rng.standard_normal(paths)
            if self.antithetic:
                z1[:half] = -z1[half:]
            z2 = rng.standard_normal(paths)
            if self.antithetic:
                z2[:half] = -z2[half:]
            w1 = z1
            w2 = rho * z1 + np.sqrt(max(1.0 - rho * rho, 1e-8)) * z2

            v_prev = np.maximum(v_paths[:, step], 0.0)
            v_sqrt = np.sqrt(v_prev)
            v_next = v_prev + kappa * (theta - v_prev) * dt + sigma * v_sqrt * sqrt_dt * w2
            v_next = np.maximum(v_next, 0.0)
            log_increment = (drift - 0.5 * v_prev) * dt + v_sqrt * sqrt_dt * w1
            s_next = s_paths[:, step] * np.exp(log_increment)

            v_paths[:, step + 1] = v_next
            s_paths[:, step + 1] = s_next

        return s_paths, v_paths

    def _lsm(
        self,
        option_type: str,
        strike: float,
        rate: float,
        ttm: float,
        spot_paths: Array,
    ) -> float:
        dt = ttm / max(self.steps, 1)
        discount = np.exp(-rate * dt)
        payoff_fn = self._payoff(option_type, strike)
        steps = spot_paths.shape[1] - 1
        cashflows = payoff_fn(spot_paths[:, -1])

        for step in range(steps - 1, 0, -1):
            cashflows *= discount
            spot_slice = spot_paths[:, step]
            values = payoff_fn(spot_slice)
            itm = values > 0
            if not np.any(itm):
                continue

            x = spot_slice[itm]
            y = cashflows[itm]
            if x.size == 0:
                continue

            a = np.column_stack((np.ones_like(x), x, x * x))
            coeff, *_ = np.linalg.lstsq(a, y, rcond=None)
            continuation = a @ coeff
            exercise = values[itm]
            exercise_mask = exercise > continuation
            if np.any(exercise_mask):
                indices = np.flatnonzero(itm)
                cashflows[indices[exercise_mask]] = exercise[exercise_mask]

        continuation_value = np.mean(cashflows) * discount
        immediate = payoff_fn(spot_paths[:, 0])
        exercise_now = np.mean(immediate) if np.any(immediate > 0) else 0.0
        return max(continuation_value, exercise_now)

    @staticmethod
    def _payoff(option_type: str, strike: float) -> Callable[[Array], Array]:
        if option_type == "c":
            return lambda s: np.maximum(s - strike, 0.0)
        return lambda s: np.maximum(strike - s, 0.0)


__all__ = ["HestonParameters", "HestonAmericanPricer"]
