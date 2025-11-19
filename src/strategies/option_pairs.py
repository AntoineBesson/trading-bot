"""Option-based extension of the pairs trading strategy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from .base_strategy import BaseStrategy
from ..options.data_handler import OptionDataHandler, OptionSnapshot
from ..options.multileg import MultiLegExecutionHelper

Signal = Dict[str, object]


@dataclass
class OptionPairsStrategy(BaseStrategy):
    data_handler: object
    execution_handler: object
    symbol_a: str
    symbol_b: str
    option_type: str = "call"
    target_delta: float = 0.45
    days_to_expiry: int = 30
    lookback_days: int = 90
    entry_threshold: float = 1.0
    exit_threshold: float = 0.0
    contracts: int = 1
    timeframe: str = "1D"
    stat_refresh_days: int = 5
    auto_execute: bool = False
    benchmark_symbol: Optional[str] = None
    initial_capital: float = 10_000.0
    option_data_handler: Optional[OptionDataHandler] = None
    multi_leg_execution: Optional[MultiLegExecutionHelper] = None
    name: str = field(default="OptionPairsStrategy", init=False)

    def __post_init__(self) -> None:
        super().__init__(
            data_handler=self.data_handler,
            execution_handler=self.execution_handler,
            symbols=[self.symbol_a, self.symbol_b],
        )
        self.option_data = self.option_data_handler or OptionDataHandler(self.data_handler)
        self.multi_leg_exec = self.multi_leg_execution or MultiLegExecutionHelper(self.execution_handler)
        self.position = "flat"
        self.last_z_score: Optional[float] = None
        self.spread_mean: Optional[float] = None
        self.spread_std: Optional[float] = None
        self._last_stat_refresh: Optional[datetime] = None
        self._vega_ratio: float = 1.0
        self._init_reference_distribution()

    # ------------------------------------------------------------------
    def generate_signal(self) -> List[Signal]:
        self._maybe_refresh_spread_stats()
        snap_a = self.option_data.get_option_snapshot(
            symbol=self.symbol_a,
            option_type=self.option_type,
            target_delta=self.target_delta,
            days_to_expiry=self.days_to_expiry,
        )
        snap_b = self.option_data.get_option_snapshot(
            symbol=self.symbol_b,
            option_type=self.option_type,
            target_delta=self.target_delta,
            days_to_expiry=self.days_to_expiry,
        )
        if not snap_a or not snap_b:
            return []

        self._vega_ratio = self._compute_vega_ratio(snap_a, snap_b)
        spread = snap_a.price - self._vega_ratio * snap_b.price
        z_score = self._compute_z_score(spread)
        self.last_z_score = z_score
        signals = self._evaluate_rules(z_score, snap_a, snap_b)
        if self.auto_execute and signals:
            self.multi_leg_exec.execute(signals)
        return signals

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        timeframe: str,
    ) -> Dict[str, object]:
        option_prices = self._build_option_series(start_date, end_date, timeframe)
        if option_prices.empty:
            raise ValueError("No data for option backtest")

        trades: List[Dict[str, object]] = []
        position = "flat"
        active_trade: Optional[Dict[str, object]] = None
        capital = self.initial_capital
        equity = capital
        equity_curve: List[float] = []

        for timestamp, row in option_prices.iterrows():
            spread = row["spread"]
            z = row["z_score"]
            price_a = row["price_a"]
            price_b = row["price_b"]
            vega_ratio = row["vega_ratio"]

            if position == "flat":
                if z >= self.entry_threshold:
                    position = "short"
                    active_trade = {
                        "timestamp": str(timestamp),
                        "direction": "short",
                        "entry_a": price_a,
                        "entry_b": price_b,
                        "vega_ratio": vega_ratio,
                    }
                    trades.append(active_trade)
                elif z <= -self.entry_threshold:
                    position = "long"
                    active_trade = {
                        "timestamp": str(timestamp),
                        "direction": "long",
                        "entry_a": price_a,
                        "entry_b": price_b,
                        "vega_ratio": vega_ratio,
                    }
                    trades.append(active_trade)
            elif position == "short" and z <= self.exit_threshold and active_trade:
                pnl = (active_trade["entry_a"] - price_a) * self.contracts
                pnl += (price_b - active_trade["entry_b"]) * self.contracts * active_trade["vega_ratio"]
                equity += pnl
                active_trade["exit_a"] = price_a
                active_trade["exit_b"] = price_b
                active_trade["pnl"] = pnl
                position = "flat"
            elif position == "long" and z >= -self.exit_threshold and active_trade:
                pnl = (price_a - active_trade["entry_a"]) * self.contracts
                pnl += (active_trade["entry_b"] - price_b) * self.contracts * active_trade["vega_ratio"]
                equity += pnl
                active_trade["exit_a"] = price_a
                active_trade["exit_b"] = price_b
                active_trade["pnl"] = pnl
                position = "flat"

            equity_curve.append(equity)

        closed = [t for t in trades if "pnl" in t]
        win_rate = sum(1 for t in closed if t["pnl"] > 0) / len(closed) if closed else 0.0
        equity_series = pd.Series(equity_curve, index=option_prices.index[: len(equity_curve)])
        returns = equity_series.pct_change().fillna(0)
        sharpe = self._compute_sharpe(returns, timeframe)
        max_dd = self._compute_max_drawdown(equity_series)
        strategy_return = (equity_series.iloc[-1] / capital - 1) if not equity_series.empty else 0.0

        return {
            "num_trades": len(closed),
            "open_trades": len(trades) - len(closed),
            "total_pnl": equity - capital,
            "win_rate": win_rate,
            "strategy_return": strategy_return,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "equity_curve": equity_series,
            "trades": closed,
        }

    # ------------------------------------------------------------------
    def _evaluate_rules(self, z_score: float, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> List[Signal]:
        signals: List[Signal] = []
        if self.position == "flat":
            if z_score >= self.entry_threshold:
                signals = self._open_short_spread(snap_a, snap_b)
            elif z_score <= -self.entry_threshold:
                signals = self._open_long_spread(snap_a, snap_b)
        elif self.position == "short" and z_score <= self.exit_threshold:
            signals = self._close_short_spread(snap_a, snap_b)
        elif self.position == "long" and z_score >= -self.exit_threshold:
            signals = self._close_long_spread(snap_a, snap_b)
        return signals

    def _open_short_spread(self, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> List[Signal]:
        self.position = "short"
        return [
            self._build_leg(snap_a, "sell", self.contracts),
            self._build_leg(snap_b, "buy", self._hedge_contracts(snap_a, snap_b)),
        ]

    def _open_long_spread(self, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> List[Signal]:
        self.position = "long"
        return [
            self._build_leg(snap_a, "buy", self.contracts),
            self._build_leg(snap_b, "sell", self._hedge_contracts(snap_a, snap_b)),
        ]

    def _close_short_spread(self, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> List[Signal]:
        self.position = "flat"
        return [
            self._build_leg(snap_a, "buy", self.contracts),
            self._build_leg(snap_b, "sell", self._hedge_contracts(snap_a, snap_b)),
        ]

    def _close_long_spread(self, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> List[Signal]:
        self.position = "flat"
        return [
            self._build_leg(snap_a, "sell", self.contracts),
            self._build_leg(snap_b, "buy", self._hedge_contracts(snap_a, snap_b)),
        ]

    def _build_leg(self, snap: OptionSnapshot, action: str, qty: int) -> Signal:
        return {
            "asset_type": "option",
            "underlying": snap.symbol,
            "symbol": snap.symbol,
            "option_type": snap.option_type,
            "strike": snap.strike,
            "expiration": snap.expiration,
            "action": action,
            "qty": int(qty),
            "limit_price": snap.price,
            "type": "limit",
            "time_in_force": "day",
        }

    def _hedge_contracts(self, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> int:
        ratio = self._compute_vega_ratio(snap_a, snap_b)
        qty = max(1, int(round(self.contracts * ratio)))
        return qty

    def _compute_vega_ratio(self, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> float:
        if snap_b.vega == 0:
            return 1.0
        return max(0.1, snap_a.vega / abs(snap_b.vega))

    def _compute_z_score(self, spread: float) -> float:
        if self.spread_mean is None or self.spread_std in (None, 0):
            raise RuntimeError("Spread statistics are not initialised")
        return (spread - self.spread_mean) / self.spread_std

    def _maybe_refresh_spread_stats(self) -> None:
        if self._last_stat_refresh is None:
            self._init_reference_distribution()
            return
        elapsed = datetime.now(UTC) - self._last_stat_refresh
        if elapsed >= timedelta(days=self.stat_refresh_days):
            self._init_reference_distribution()

    def _init_reference_distribution(self) -> None:
        start = self._iso_days_ago(self.lookback_days)
        end = self._iso_days_ago(0)
        option_prices = self._build_option_series(start, end, self.timeframe)
        if option_prices.empty:
            raise RuntimeError("Unable to bootstrap option spread statistics")
        spread = option_prices["spread"]
        self.spread_mean = float(spread.mean())
        self.spread_std = float(spread.std(ddof=0)) or 1.0
        self._last_stat_refresh = datetime.now(UTC)

    def _build_option_series(self, start: str, end: str, timeframe: str) -> pd.DataFrame:
        prices = self._fetch_close_frame(start, end, timeframe)
        if prices.empty:
            return pd.DataFrame()

        iv_a = self.option_data.estimate_historical_vol(self.symbol_a)
        iv_b = self.option_data.estimate_historical_vol(self.symbol_b)
        ttm = max(self.days_to_expiry / 252, 1e-4)
        greeks = self.option_data.greeks
        strike_a = greeks.find_strike_for_delta(self.target_delta, self.option_type, float(prices[self.symbol_a].iloc[-1]), ttm, iv_a)
        strike_b = greeks.find_strike_for_delta(self.target_delta, self.option_type, float(prices[self.symbol_b].iloc[-1]), ttm, iv_b)

        opt_a = greeks.price_series(self.option_type, prices[self.symbol_a], strike_a, ttm, iv_a)
        opt_b = greeks.price_series(self.option_type, prices[self.symbol_b], strike_b, ttm, iv_b)
        df = pd.DataFrame(
            {
                "price_a": opt_a["price"],
                "price_b": opt_b["price"],
                "vega_a": opt_a["vega"],
                "vega_b": opt_b["vega"],
            }
        )
        df["vega_ratio"] = df.apply(lambda row: max(0.1, row.vega_a / max(row.vega_b, 1e-6)), axis=1)
        df["spread"] = df["price_a"] - df["vega_ratio"] * df["price_b"]
        window = max(10, int(len(df) * 0.2))
        df["spread_mean"] = df["spread"].rolling(window=window, min_periods=max(5, window // 2)).mean()
        df["spread_std"] = df["spread"].rolling(window=window, min_periods=max(5, window // 2)).std(ddof=0)
        df["z_score"] = (df["spread"] - df["spread_mean"]) / df["spread_std"]
        df = df.replace([pd.NA, pd.NaT, float("inf"), float("-inf")], pd.NA).dropna(subset=["z_score"])
        return df

    def _fetch_close_frame(self, start_date: str, end_date: str, timeframe: str) -> pd.DataFrame:
        data = self.data_handler.get_historical_bars([self.symbol_a, self.symbol_b], timeframe, start=start_date, end=end_date)
        if not data:
            return pd.DataFrame()
        frames = []
        for symbol in (self.symbol_a, self.symbol_b):
            df = data.get(symbol)
            if df is None or df.empty:
                continue
            tmp = df.copy()
            tmp.index = pd.to_datetime(tmp.index)
            if getattr(tmp.index, "tz", None) is not None:
                tmp.index = tmp.index.tz_convert("UTC").tz_localize(None)
            frames.append(tmp[["close"]].rename(columns={"close": symbol}))
        if len(frames) != 2:
            return pd.DataFrame()
        merged = pd.concat(frames, axis=1).dropna()
        return merged

    @staticmethod
    def _compute_sharpe(returns: pd.Series, timeframe: str) -> float:
        if returns.empty or returns.std() == 0:
            return 0.0
        periods = OptionPairsStrategy._periods_per_year(timeframe)
        return float((returns.mean() / returns.std()) * (periods ** 0.5))

    @staticmethod
    def _compute_max_drawdown(equity: pd.Series) -> float:
        if equity.empty:
            return 0.0
        running_max = equity.cummax()
        drawdown = (equity / running_max) - 1
        return float(abs(drawdown.min()))

    @staticmethod
    def _periods_per_year(timeframe: str) -> int:
        tf = timeframe.strip().upper()
        if tf.endswith("MIN"):
            minutes = int(tf[:-3])
        elif tf.endswith("H"):
            minutes = int(tf[:-1]) * 60
        elif tf.endswith("D"):
            minutes = int(tf[:-1]) * 1440
        else:
            mapping = {"1D": 1440, "1H": 60, "4H": 240, "15MIN": 15, "5MIN": 5, "1MIN": 1}
            minutes = mapping.get(tf, 1440)
        periods_per_day = max(1, int(1440 / minutes))
        return periods_per_day * 252

    @staticmethod
    def _iso_days_ago(days: int) -> str:
        return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


__all__ = ["OptionPairsStrategy"]
