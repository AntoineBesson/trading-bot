"""Utility helpers for pricing and risk metrics of vanilla options.

The :class:`GreeksCalculator` exposes a light-weight Black-Scholes
implementation that powers both the option data handler and the option
pairs strategy.  It intentionally supports scalar and small batch
calculations so it can be used in notebooks and unit tests without the
need for heavy infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, sqrt
from typing import Dict, Iterable, Optional, Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm

try:  # pragma: no cover - optional acceleration
    from py_vollib_vectorized import (  # type: ignore
        delta as vollib_delta,
        gamma as vollib_gamma,
        price as vollib_price,
        rho as vollib_rho,
        theta as vollib_theta,
        vega as vollib_vega,
    )

    HAS_VOLLIB = True
except Exception:  # pragma: no cover - fallback path
    HAS_VOLLIB = False


OptionMetrics = Dict[str, float]


@dataclass
class GreeksCalculator:
    """Black-Scholes greeks with a friendly Python interface."""

    rate: float = 0.01

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

        rate = self.rate if rate is None else rate
        option_type = self._normalize_type(option_type)
        if spot <= 0 or strike <= 0 or vol <= 0 or ttm <= 0:
            return {"price": 0.0, "delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}

        d1, d2 = self._d1_d2(spot, strike, ttm, vol, rate)
        if option_type == "c":
            price = spot * norm.cdf(d1) - strike * exp(-rate * ttm) * norm.cdf(d2)
            delta = norm.cdf(d1)
            rho = strike * ttm * exp(-rate * ttm) * norm.cdf(d2)
        else:
            price = strike * exp(-rate * ttm) * norm.cdf(-d2) - spot * norm.cdf(-d1)
            delta = norm.cdf(d1) - 1
            rho = -strike * ttm * exp(-rate * ttm) * norm.cdf(-d2)

        gamma = norm.pdf(d1) / (spot * vol * sqrt(ttm))
        vega = spot * norm.pdf(d1) * sqrt(ttm)
        theta = (
            -spot * norm.pdf(d1) * vol / (2 * sqrt(ttm))
            - rate * strike * exp(-rate * ttm) * (norm.cdf(d2) if option_type == "c" else norm.cdf(-d2))
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
        return self.metrics(option_type, spot, strike, ttm, vol, rate)["price"]

    def delta(self, option_type: str, spot: float, strike: float, ttm: float, vol: float, rate: Optional[float] = None) -> float:
        return self.metrics(option_type, spot, strike, ttm, vol, rate)["delta"]

    def vega(self, option_type: str, spot: float, strike: float, ttm: float, vol: float, rate: Optional[float] = None) -> float:
        return self.metrics(option_type, spot, strike, ttm, vol, rate)["vega"]

    def vectorized_metrics(self, options: pd.DataFrame) -> pd.DataFrame:
        """Compute metrics for many options at once.

        The input DataFrame must contain ``option_type``, ``spot``, ``strike``,
        ``ttm`` and ``vol`` columns.  ``py_vollib_vectorized`` is used when
        installed, otherwise the method falls back to a slower but dependency
        free loop, which is still manageable for notebook scale datasets.
        """

        required = {"option_type", "spot", "strike", "ttm", "vol"}
        missing = required - set(options.columns)
        if missing:
            raise ValueError(f"Options frame is missing columns: {sorted(missing)}")

        df = options.copy().reset_index(drop=True)
        opt_types = df["option_type"].astype(str).str.lower().str[0]
        if HAS_VOLLIB:
            df["price"] = vollib_price(opt_types, df["spot"], df["strike"], df["ttm"], df["vol"], self.rate)
            df["delta"] = vollib_delta(opt_types, df["spot"], df["strike"], df["ttm"], df["vol"], self.rate)
            df["gamma"] = vollib_gamma(opt_types, df["spot"], df["strike"], df["ttm"], df["vol"], self.rate)
            df["theta"] = vollib_theta(opt_types, df["spot"], df["strike"], df["ttm"], df["vol"], self.rate)
            df["vega"] = vollib_vega(opt_types, df["spot"], df["strike"], df["ttm"], df["vol"], self.rate)
            df["rho"] = vollib_rho(opt_types, df["spot"], df["strike"], df["ttm"], df["vol"], self.rate)
        else:  # pragma: no cover - exercised indirectly
            metrics: Sequence[OptionMetrics] = [
                self.metrics(row.option_type, row.spot, row.strike, row.ttm, row.vol)
                for row in df.itertuples(index=False)
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
    ) -> pd.DataFrame:
        """Return price, delta and vega for a full series of underlying prices."""

        values = [
            self.metrics(option_type, float(spot), strike, ttm, vol, rate)
            for spot in spots.astype(float)
        ]
        return pd.DataFrame(values, index=spots.index)

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

    def _d1_d2(self, spot: float, strike: float, ttm: float, vol: float, rate: float) -> Sequence[float]:
        denom = vol * sqrt(ttm)
        d1 = (log(spot / strike) + (rate + 0.5 * vol ** 2) * ttm) / denom
        d2 = d1 - denom
        return d1, d2

    @staticmethod
    def _normalize_type(option_type: str) -> str:
        if not option_type:
            raise ValueError("option_type is required")
        return option_type.lower().strip()[0]


__all__ = ["GreeksCalculator"]
