from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Dict, Iterable, Optional

import numpy as np
import pandas as pd

from .greeks import GreeksCalculator


ChainFetcher = Callable[[str, Optional[str]], Iterable[Dict[str, object]]]


@dataclass
class OptionSnapshot:
    symbol: str
    option_type: str
    strike: float
    expiration: str
    ttm: float
    spot: float
    implied_vol: float
    price: float
    delta: float
    vega: float
    gamma: float
    theta: float


class OptionDataHandler:
    """Utility wrapper that derives option analytics off underlying data."""

    def __init__(self, data_handler, rate: float = 0.01, option_chain_fetcher: Optional[ChainFetcher] = None):
        self.data_handler = data_handler
        self.rate = rate
        self.option_chain_fetcher = option_chain_fetcher
        self.greeks = GreeksCalculator(rate=rate)

    # ------------------------------------------------------------------
    # Option chain helpers
    # ------------------------------------------------------------------
    def fetch_option_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None,
        option_type: Optional[str] = None,
        min_delta: Optional[float] = None,
        max_delta: Optional[float] = None,
    ) -> pd.DataFrame:
        """Return a DataFrame representing the option chain.

        The handler delegates to ``option_chain_fetcher`` when provided.  The
        fetcher function can directly hit the broker API, a cache, or even
        return fixture data when running tests.
        """

        if self.option_chain_fetcher is None:
            return pd.DataFrame()

        rows = list(self.option_chain_fetcher(symbol, expiration))
        if not rows:
            return pd.DataFrame()

        frame = pd.DataFrame(rows)
        if option_type is not None:
            frame = frame[frame["option_type"].str.lower().str.startswith(option_type[0].lower())]
        if min_delta is not None:
            frame = frame[frame["delta"] >= min_delta]
        if max_delta is not None:
            frame = frame[frame["delta"] <= max_delta]
        return frame.reset_index(drop=True)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------
    def estimate_historical_vol(self, symbol: str, lookback_days: int = 30, timeframe: str = "1D") -> float:
        bars = self.data_handler.get_historical_bars([symbol], timeframe, self._iso_days_ago(lookback_days), self._iso_days_ago(0))
        if not bars or symbol not in bars or bars[symbol].empty:
            return 0.2
        closes = bars[symbol]["close"].astype(float)
        log_returns = np.log(closes / closes.shift(1)).dropna()
        if log_returns.empty:
            return 0.2
        return float(log_returns.std(ddof=0) * np.sqrt(252))

    def get_option_snapshot(
        self,
        symbol: str,
        option_type: str = "call",
        target_delta: float = 0.5,
        days_to_expiry: int = 30,
        implied_vol: Optional[float] = None,
    ) -> Optional[OptionSnapshot]:
        logger.info(f"[API] Requesting Option Chain for {symbol} (Exp: ~{days_to_expiry}d, Delta: {target_delta})")
        spot = self._latest_close(symbol)
        if spot is None:
            return None
        iv = implied_vol or self.estimate_historical_vol(symbol)
        ttm = max(days_to_expiry / 252, 1e-4)
        strike = self.greeks.find_strike_for_delta(target_delta, option_type, spot, ttm, max(iv, 1e-4), self.rate)
        metrics = self.greeks.metrics(option_type, spot, strike, ttm, max(iv, 1e-4), self.rate)
        expiration = (datetime.now(UTC) + timedelta(days=days_to_expiry)).date().isoformat()
        return OptionSnapshot(
            symbol=symbol,
            option_type=option_type,
            strike=float(strike),
            expiration=expiration,
            ttm=float(ttm),
            spot=float(spot),
            implied_vol=float(iv),
            price=metrics["price"],
            delta=metrics["delta"],
            vega=metrics["vega"],
            gamma=metrics["gamma"],
            theta=metrics["theta"],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _latest_close(self, symbol: str) -> Optional[float]:
        latest = self.data_handler.get_latest_bar(symbol)
        if latest is None:
            return None
        if isinstance(latest, dict):
            return float(latest.get("close") or latest.get("c") or 0.0)
        for attr in ("close", "c", "price"):
            if hasattr(latest, attr):
                return float(getattr(latest, attr))
        return None

    @staticmethod
    def _iso_days_ago(days: int) -> str:
        return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


__all__ = ["OptionDataHandler", "OptionSnapshot"]
