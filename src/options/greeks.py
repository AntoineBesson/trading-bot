"""Utility helpers for pricing and risk metrics of vanilla options.

The :class:`GreeksCalculator` now evaluates American-style contracts using
an LSM Monte Carlo solver under the Heston stochastic volatility model.
It exposes the same surface area as the legacy Black-Scholes helper so
existing call sites can rely on the richer analytics without changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .heston import HestonAmericanPricer, HestonParameters


OptionMetrics = Dict[str, float]


@dataclass
class _PreparedInputs:
    option_type: str
    spot: float
    strike: float
    ttm: float
    vol: float
    rate: float
    params: HestonParameters
    seed: Optional[int]


@dataclass
class GreeksCalculator:
    """Heston-based American option metrics with a friendly interface."""

    rate: float = 0.01
    heston_params: Optional[Dict[str, float]] = None
    paths: int = 1200
    steps: int = 64
    seed: Optional[int] = 1234
    antithetic: bool = True
    greek_bumps: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        base = HestonParameters()
        overrides = self.heston_params or {}
        self._lock_theta = "theta" in overrides
        self._lock_v0 = "v0" in overrides
        self._base_params = HestonParameters(
            kappa=overrides.get("kappa", base.kappa),
            theta=overrides.get("theta", base.theta),
            sigma=overrides.get("sigma", base.sigma),
            rho=overrides.get("rho", base.rho),
            v0=overrides.get("v0", base.v0),
        )
        self._base_params = self._base_params.clamp()

    def metrics(
        self,
        option_type: str,
        spot: float,
        strike: float,
        ttm: float,
        vol: float,
        rate: Optional[float] = None,
    ) -> OptionMetrics:
        """Return price and greeks for a single option contract."""

        prepared = self._prepare_inputs(option_type, spot, strike, ttm, vol, rate)
        if prepared is None:
            return {"price": 0.0, "delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}

        path_factors = self._generate_path_factors(prepared.ttm, prepared.rate, prepared.params, prepared.seed)
        price = self._price(
            prepared.option_type,
            prepared.spot,
            prepared.strike,
            prepared.ttm,
            prepared.rate,
            prepared.params,
            prepared.seed,
            path_factors,
        )
        delta, gamma = self._delta_gamma(
            prepared.option_type,
            prepared.spot,
            prepared.strike,
            prepared.ttm,
            prepared.rate,
            prepared.params,
            prepared.seed,
            price,
            path_factors,
        )
        vega = self._vega(
            prepared.option_type,
            prepared.spot,
            prepared.strike,
            prepared.ttm,
            prepared.rate,
            prepared.vol,
            prepared.seed,
            price,
        )
        theta = self._theta(
            prepared.option_type,
            prepared.spot,
            prepared.strike,
            prepared.ttm,
            prepared.rate,
            prepared.params,
            prepared.seed,
            price,
        )
        rho = self._rho(
            prepared.option_type,
            prepared.spot,
            prepared.strike,
            prepared.ttm,
            prepared.rate,
            prepared.params,
            prepared.seed,
        )

        return {
            "price": float(price),
            "delta": float(delta),
            "gamma": float(gamma),
            "vega": float(vega),
            "theta": float(theta),
            "rho": float(rho),
        }

    def price(self, option_type: str, spot: float, strike: float, ttm: float, vol: float, rate: Optional[float] = None) -> float:
        prepared = self._prepare_inputs(option_type, spot, strike, ttm, vol, rate)
        if prepared is None:
            return 0.0
        path_factors = self._generate_path_factors(prepared.ttm, prepared.rate, prepared.params, prepared.seed)
        return self._price(
            prepared.option_type,
            prepared.spot,
            prepared.strike,
            prepared.ttm,
            prepared.rate,
            prepared.params,
            prepared.seed,
            path_factors,
        )

    def delta(self, option_type: str, spot: float, strike: float, ttm: float, vol: float, rate: Optional[float] = None) -> float:
        prepared = self._prepare_inputs(option_type, spot, strike, ttm, vol, rate)
        if prepared is None:
            return 0.0
        bump_pct = self.greek_bumps.get("spot", 0.01)
        bump = max(bump_pct * prepared.spot, 1e-4)
        if prepared.spot - bump <= 0:
            bump = min(prepared.spot * 0.5, bump)
        path_factors = self._generate_path_factors(prepared.ttm, prepared.rate, prepared.params, prepared.seed)
        up = self._price(
            prepared.option_type,
            prepared.spot + bump,
            prepared.strike,
            prepared.ttm,
            prepared.rate,
            prepared.params,
            prepared.seed,
            path_factors,
        )
        down = self._price(
            prepared.option_type,
            max(prepared.spot - bump, 1e-4),
            prepared.strike,
            prepared.ttm,
            prepared.rate,
            prepared.params,
            prepared.seed,
            path_factors,
        )
        return (up - down) / (2 * bump)

    def vega(self, option_type: str, spot: float, strike: float, ttm: float, vol: float, rate: Optional[float] = None) -> float:
        return self.metrics(option_type, spot, strike, ttm, vol, rate)["vega"]

    def vectorized_metrics(self, options: pd.DataFrame) -> pd.DataFrame:
        """Compute metrics for many options at once.

        The input DataFrame must contain ``option_type``, ``spot``, ``strike``,
        ``ttm`` and ``vol`` columns.  The method runs a Monte Carlo solve per
        row, so deliberate batching is recommended.
        """

        required = {"option_type", "spot", "strike", "ttm", "vol"}
        missing = required - set(options.columns)
        if missing:
            raise ValueError(f"Options frame is missing columns: {sorted(missing)}")

        df = options.copy().reset_index(drop=True)
        opt_types = df["option_type"].astype(str).str.lower().str[0]
        metrics = [
            self.metrics(opt_types.iloc[idx], float(row.spot), float(row.strike), float(row.ttm), float(row.vol))
            for idx, row in enumerate(df.itertuples(index=False))
        ]
        metric_frame = pd.DataFrame(metrics)
        df[["price", "delta", "gamma", "theta", "vega", "rho"]] = metric_frame[["price", "delta", "gamma", "theta", "vega", "rho"]]

        return df

    def price_series(
        self,
        option_type: str,
        spots: pd.Series,
        strike: float,
        ttm: float,
        vol: float,
        rate: Optional[float] = None,
        *,
        fast: bool = False,
        max_points: Optional[int] = None,
    ) -> pd.DataFrame:
        """Return price and greeks across a price path.

        When ``fast`` is enabled the method throttles Monte Carlo work by
        down-sampling long series (``max_points``) and evaluating a reduced set
        of finite-difference bumps.  This keeps bootstrap workflows responsive
        while still providing accurate price/vega estimates for spread stats.
        """

        series = spots.astype(float)
        if fast and max_points is not None and len(series) > max_points:
            step = max(1, len(series) // max_points)
            series = series.iloc[::step]

        opt_type = self._normalize_type(option_type)
        local_rate = self.rate if rate is None else rate
        vol = max(vol, 1e-6)
        params = self._resolve_params(vol)
        base_seed = self.seed if self.seed is not None else np.random.SeedSequence().generate_state(1)[0]

        records = []
        if fast:
            path_factors = self._generate_path_factors(ttm, local_rate, params, base_seed)
            vol_bump = self.greek_bumps.get("vol", 0.05)
            vol_step = max(vol * vol_bump, 1e-5)
            up_vol = vol + vol_step
            down_vol = max(vol - vol_step, 1e-6)
            up_params = self._resolve_params(up_vol)
            down_params = self._resolve_params(down_vol)
            up_path = self._generate_path_factors(ttm, local_rate, up_params, base_seed)
            down_path = self._generate_path_factors(ttm, local_rate, down_params, base_seed)
            for spot in series:
                price = self._price(opt_type, float(spot), strike, ttm, local_rate, params, base_seed, path_factors)

                bump_pct = self.greek_bumps.get("spot", 0.01)
                bump = max(bump_pct * float(spot), 1e-4)
                up_price = self._price(opt_type, float(spot) + bump, strike, ttm, local_rate, params, base_seed, path_factors)
                down_price = self._price(opt_type, max(float(spot) - bump, 1e-4), strike, ttm, local_rate, params, base_seed, path_factors)
                delta = (up_price - down_price) / (2 * bump)
                gamma = (up_price - 2 * price + down_price) / (bump ** 2)

                up_vol_price = self._price(opt_type, float(spot), strike, ttm, local_rate, up_params, base_seed, up_path)
                down_vol_price = self._price(opt_type, float(spot), strike, ttm, local_rate, down_params, base_seed, down_path)
                vega = (up_vol_price - down_vol_price) / (up_vol - down_vol)

                records.append(
                    {
                        "price": float(price),
                        "delta": float(delta),
                        "gamma": float(gamma),
                        "vega": float(vega),
                        "theta": 0.0,
                        "rho": 0.0,
                    }
                )
            return pd.DataFrame(records, index=series.index)

        values = [
            self.metrics(opt_type, float(spot), strike, ttm, vol, local_rate)
            for spot in series
        ]
        return pd.DataFrame(values, index=series.index)

    def find_strike_for_delta(
        self,
        target_delta: float,
        option_type: str,
        spot: float,
        ttm: float,
        vol: float,
        rate: Optional[float] = None,
        tolerance: float = 1e-4,
        max_iter: int = 50,
    ) -> float:
        """Solve for the strike that matches ``target_delta``.

        A simple bisection search is sufficient for monotonic delta/strike
        relationships of vanilla options.
        """

        if not 0 < abs(target_delta) < 1:
            raise ValueError("target_delta must be in (0, 1)")

        rate = self.rate if rate is None else rate
        option_type = self._normalize_type(option_type)
        low, high = 0.1 * spot, 3 * spot
        target = target_delta if option_type == "c" else -abs(target_delta)

        f_low = self.delta(option_type, spot, low, ttm, vol, rate) - target
        f_high = self.delta(option_type, spot, high, ttm, vol, rate) - target

        if f_low * f_high > 0:
            strikes = np.linspace(0.25 * spot, 1.75 * spot, 200)
            deltas = [self.delta(option_type, spot, float(strike), ttm, vol, rate) for strike in strikes]
            idx = int(np.argmin(np.abs(np.array(deltas) - target)))
            return float(strikes[idx])

        for _ in range(max_iter):
            mid = 0.5 * (low + high)
            f_mid = self.delta(option_type, spot, mid, ttm, vol, rate) - target
            if abs(f_mid) < tolerance:
                return mid
            if f_low * f_mid < 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid
        return 0.5 * (low + high)

    def _price(
        self,
        option_type: str,
        spot: float,
        strike: float,
        ttm: float,
        rate: float,
        params: HestonParameters,
        seed: Optional[int],
        path_factors: Optional[np.ndarray] = None,
    ) -> float:
        pricer = HestonAmericanPricer(paths=self.paths, steps=self.steps, seed=seed, antithetic=self.antithetic)
        return pricer.price(option_type, spot, strike, ttm, rate, params, path_factors=path_factors)

    def _delta_gamma(
        self,
        option_type: str,
        spot: float,
        strike: float,
        ttm: float,
        rate: float,
        params: HestonParameters,
        seed: Optional[int],
        base_price: float,
        path_factors: Optional[np.ndarray] = None,
    ) -> tuple[float, float]:
        bump_pct = self.greek_bumps.get("spot", 0.01)
        bump = max(bump_pct * spot, 1e-4)
        if spot - bump <= 0:
            bump = min(spot * 0.5, bump)
        up = self._price(option_type, spot + bump, strike, ttm, rate, params, seed, path_factors)
        down = self._price(option_type, max(spot - bump, 1e-4), strike, ttm, rate, params, seed, path_factors)
        delta = (up - down) / (2 * bump)
        gamma = (up - 2 * base_price + down) / (bump ** 2)
        return delta, gamma

    def _vega(
        self,
        option_type: str,
        spot: float,
        strike: float,
        ttm: float,
        rate: float,
        vol: float,
        seed: Optional[int],
        base_price: float,
    ) -> float:
        bump_pct = self.greek_bumps.get("vol", 0.05)
        bump = max(bump_pct * vol, 1e-5)
        up_vol = vol + bump
        down_vol = max(vol - bump, 1e-6)
        up_params = self._resolve_params(up_vol)
        down_params = self._resolve_params(down_vol)
        up_path = self._generate_path_factors(ttm, rate, up_params, seed)
        down_path = self._generate_path_factors(ttm, rate, down_params, seed)
        up = self._price(option_type, spot, strike, ttm, rate, up_params, seed, up_path)
        down = self._price(option_type, spot, strike, ttm, rate, down_params, seed, down_path)
        return (up - down) / (up_vol - down_vol)

    def _theta(
        self,
        option_type: str,
        spot: float,
        strike: float,
        ttm: float,
        rate: float,
        params: HestonParameters,
        seed: Optional[int],
        base_price: float,
    ) -> float:
        bump = self.greek_bumps.get("time", 1.0 / 365)
        bump = min(bump, 0.25 * ttm)
        if bump <= 0:
            return 0.0
        up = self._price(option_type, spot, strike, ttm + bump, rate, params, seed)
        if ttm - bump <= 1e-6:
            return (up - base_price) / bump
        else:
            down_path = self._generate_path_factors(ttm - bump, rate, params, seed)
            down_price = self._price(option_type, spot, strike, ttm - bump, rate, params, seed, down_path)
        return (up - down_price) / (2 * bump)

    def _rho(
        self,
        option_type: str,
        spot: float,
        strike: float,
        ttm: float,
        rate: float,
        params: HestonParameters,
        seed: Optional[int],
    ) -> float:
        bump = self.greek_bumps.get("rate", 1e-4)
        up_params = params
        down_params = params
        up_path = self._generate_path_factors(ttm, rate + bump, up_params, seed)
        down_path = self._generate_path_factors(ttm, rate - bump, down_params, seed)
        up = self._price(option_type, spot, strike, ttm, rate + bump, up_params, seed, up_path)
        down = self._price(option_type, spot, strike, ttm, rate - bump, down_params, seed, down_path)
        return (up - down) / (2 * bump)

    def _resolve_params(self, vol: float) -> HestonParameters:
        base = HestonParameters(
            kappa=self._base_params.kappa,
            theta=self._base_params.theta,
            sigma=self._base_params.sigma,
            rho=self._base_params.rho,
            v0=self._base_params.v0,
        )
        if not self._lock_theta:
            implied = max(vol ** 2, 1e-8)
            base.theta = implied
        if not self._lock_v0:
            base.v0 = max(vol ** 2, 1e-8)
        return base.clamp()

    def _prepare_inputs(
        self,
        option_type: str,
        spot: float,
        strike: float,
        ttm: float,
        vol: float,
        rate: Optional[float],
    ) -> Optional[_PreparedInputs]:
        local_rate = self.rate if rate is None else rate
        opt_type = self._normalize_type(option_type)
        if spot <= 0 or strike <= 0 or vol <= 0 or ttm <= 0:
            return None
        vol = max(vol, 1e-6)
        params = self._resolve_params(vol)
        seed = self.seed if self.seed is not None else np.random.SeedSequence().generate_state(1)[0]
        return _PreparedInputs(opt_type, float(spot), float(strike), float(ttm), vol, float(local_rate), params, seed)

    def _generate_path_factors(
        self,
        ttm: float,
        rate: float,
        params: HestonParameters,
        seed: Optional[int],
    ) -> np.ndarray:
        pricer = HestonAmericanPricer(paths=self.paths, steps=self.steps, seed=seed, antithetic=self.antithetic)
        return pricer.generate_path_factors(ttm, rate, params, seed)

    @staticmethod
    def _normalize_type(option_type: str) -> str:
        if not option_type:
            raise ValueError("option_type is required")
        return option_type.lower().strip()[0]


__all__ = ["GreeksCalculator"]
