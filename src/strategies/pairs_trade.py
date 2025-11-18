"""Pairs trading strategy implementation.

This module provides the `PairsTradeStrategy`, an implementation of the
`BaseStrategy` contract dedicated to monitoring a single cointegrated pair
and producing market-neutral signals based on spread z-scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import sqrt
from typing import Dict, List, Optional

import pandas as pd

from .base_strategy import BaseStrategy

Signal = Dict[str, object]


def _iso_date(days_ago: int) -> str:
    """Return an ISO-8601 string for *days_ago* days before today."""

    return (datetime.now(UTC) - timedelta(days=days_ago)).date().isoformat()


@dataclass
class BacktestTrade:
    """Container used by `run_backtest` for reporting trades."""

    timestamp: str
    direction: str
    entry_price_a: float
    entry_price_b: float
    exit_price_a: Optional[float] = None
    exit_price_b: Optional[float] = None
    pnl: Optional[float] = None


@dataclass
class PairsTradeStrategy(BaseStrategy):
    """Monitors a single cointegrated pair and emits two-legged signals.

    Parameters
    ----------
    data_handler
        Source of historical and latest market data ("senses").
    execution_handler
        Component responsible for order routing ("hands").
    symbol_a / symbol_b
        Members of the cointegrated pair (e.g., "V" and "MA").
    hedge_ratio
        Slope returned by the notebook regression. The spread is computed as
        `price_a - hedge_ratio * price_b`.
    lookback_days
        Number of calendar days of history to use when estimating the spread
        mean / standard deviation.
    entry_threshold
        Z-score at which the strategy enters positions (default 2.0).
    exit_threshold
        Z-score at which active positions are flattened (default 0.0, i.e.,
        close positions once the spread reverts through the mean).
    quantity
        Number of shares of `symbol_a` to trade per leg. The `symbol_b`
        quantity is scaled by the hedge ratio.
    timeframe
        Candlestick timeframe requested from the data handler (default "1D").
    auto_execute
        When True, `generate_signal` forwards every produced signal directly to
        the `ExecutionHandler`. Otherwise, the method simply returns the list
        of signals for the caller to handle.
    """

    data_handler: object
    execution_handler: object
    symbol_a: str
    symbol_b: str
    hedge_ratio: float
    lookback_days: int = 60
    entry_threshold: float = 1.25
    exit_threshold: float = 0.25
    quantity: int = 10
    timeframe: str = "1H"
    auto_execute: bool = False
    stat_refresh_days: int = 7
    benchmark_symbol: Optional[str] = "SPY"
    initial_capital: float = 10_000.0
    name: str = field(default="PairsTradeStrategy", init=False)

    def __post_init__(self) -> None:
        super().__init__(
            data_handler=self.data_handler,
            execution_handler=self.execution_handler,
            symbols=[self.symbol_a, self.symbol_b],
        )
        self.name = "PairsTradeStrategy"
        self.position: str = "flat"  # "flat", "long", "short"
        self.last_z_score: Optional[float] = None
        self.spread_mean = None
        self.spread_std = None
        self._last_stat_refresh = None
        self._init_reference_distribution()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def generate_signal(self) -> List[Signal]:
        """Evaluate the latest spread and emit signals if thresholds trigger."""

        self._maybe_refresh_spread_stats()
        price_a = self._latest_close(self.symbol_a)
        price_b = self._latest_close(self.symbol_b)
        if price_a is None or price_b is None:
            print("PairsTradeStrategy: Missing latest data, skipping signal.")
            return []

        z_score = self._compute_z_score(price_a, price_b)
        self.last_z_score = z_score

        signals = self._evaluate_rules(z_score)
        if self.auto_execute:
            self._execute_signals(signals)
        return signals

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        timeframe: str,
        benchmark_series: Optional[pd.Series] = None,
        benchmark_return: Optional[float] = None,
    ) -> Dict[str, object]:
        """Simulate the strategy over historical data and print basic stats."""

        prices = self._fetch_close_frame(start_date=start_date, end_date=end_date, timeframe=timeframe)
        if prices.empty:
            raise ValueError("No historical data returned for backtest.")

        prices["spread"] = prices[self.symbol_a] - self.hedge_ratio * prices[self.symbol_b]
        window = self._rolling_window_bars(timeframe)
        prices["spread_mean"] = prices["spread"].rolling(window=window, min_periods=max(10, window // 2)).mean()
        prices["spread_std"] = prices["spread"].rolling(window=window, min_periods=max(10, window // 2)).std(ddof=0)
        prices["z_score"] = (prices["spread"] - prices["spread_mean"]) / prices["spread_std"]
        prices = prices.replace([pd.NA, pd.NaT, float("inf"), float("-inf")], pd.NA)
        prices = prices.dropna(subset=["z_score"])
        if prices.empty:
            raise ValueError("Not enough data to compute rolling z-scores.")

        trades: List[BacktestTrade] = []
        equity = 0.0
        active_trade: Optional[BacktestTrade] = None
        position = "flat"
        capital_base = self.initial_capital
        equity_curve: List[float] = []

        qty_a = self.quantity
        qty_b = self._hedge_quantity()

        for timestamp, row in prices.iterrows():
            z = row["z_score"]
            price_a = row[self.symbol_a]
            price_b = row[self.symbol_b]

            if position == "flat":
                if z >= self.entry_threshold:
                    position = "short"
                    active_trade = BacktestTrade(
                        timestamp=str(timestamp),
                        direction="short",
                        entry_price_a=price_a,
                        entry_price_b=price_b,
                    )
                    trades.append(active_trade)
                elif z <= -self.entry_threshold:
                    position = "long"
                    active_trade = BacktestTrade(
                        timestamp=str(timestamp),
                        direction="long",
                        entry_price_a=price_a,
                        entry_price_b=price_b,
                    )
                    trades.append(active_trade)
            elif position == "short" and z <= self.exit_threshold and active_trade:
                pnl = (active_trade.entry_price_a - price_a) * qty_a
                pnl += (price_b - active_trade.entry_price_b) * qty_b
                equity += pnl
                active_trade.exit_price_a = price_a
                active_trade.exit_price_b = price_b
                active_trade.pnl = pnl
                position = "flat"
            elif position == "long" and z >= -self.exit_threshold and active_trade:
                pnl = (price_a - active_trade.entry_price_a) * qty_a
                pnl += (active_trade.entry_price_b - price_b) * qty_b
                equity += pnl
                active_trade.exit_price_a = price_a
                active_trade.exit_price_b = price_b
                active_trade.pnl = pnl
                position = "flat"

            equity_curve.append(capital_base + equity)

        closed_trades = [t for t in trades if t.pnl is not None]
        wins = sum(1 for t in closed_trades if t.pnl > 0)
        win_rate = wins / len(closed_trades) if closed_trades else 0.0

        equity_series = pd.Series(equity_curve, index=prices.index[: len(equity_curve)])
        returns = equity_series.pct_change().fillna(0)
        sharpe = self._compute_sharpe(returns, timeframe)
        max_drawdown = self._compute_max_drawdown(equity_series)

        strategy_return = (equity_series.iloc[-1] / capital_base - 1) if not equity_series.empty else 0.0
        benchmark_curve = None
        benchmark_ret_value = benchmark_return

        if benchmark_series is not None and not benchmark_series.empty:
            bench = benchmark_series.copy()
            if not isinstance(bench.index, pd.DatetimeIndex):
                bench.index = pd.to_datetime(bench.index)
            if getattr(bench.index, "tz", None) is not None:
                bench.index = bench.index.tz_convert("UTC").tz_localize(None)
            bench = bench.loc[
                (bench.index >= pd.to_datetime(start_date))
                & (bench.index <= pd.to_datetime(end_date))
            ]
            if not bench.empty:
                benchmark_curve = bench
                benchmark_ret_value = float(bench.iloc[-1] / bench.iloc[0] - 1)
        elif benchmark_ret_value is None and self.benchmark_symbol:
            benchmark_curve = self._fetch_close_series(
                symbol=self.benchmark_symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
            )
            if not benchmark_curve.empty:
                benchmark_ret_value = float(benchmark_curve.iloc[-1] / benchmark_curve.iloc[0] - 1)

        outperformance = (
            strategy_return - benchmark_ret_value if benchmark_ret_value is not None else None
        )

        summary = {
            "num_trades": len(closed_trades),
            "open_trades": len(trades) - len(closed_trades),
            "total_pnl": equity,
            "win_rate": win_rate,
            "strategy_return": strategy_return,
            "benchmark_return": benchmark_ret_value,
            "excess_return": outperformance,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "equity_curve": equity_series,
            "trades": closed_trades,
        }

        print("--- PairsTradeStrategy Backtest Summary ---")
        print(f"Period: {start_date} -> {end_date} | timeframe={timeframe}")
        print(f"Trades closed: {summary['num_trades']} | open: {summary['open_trades']}")
        print(
            f"Total PnL: {summary['total_pnl']:.2f} | Win rate: {summary['win_rate']:.1%} | "
            f"Sharpe: {summary['sharpe']:.2f} | Max DD: {summary['max_drawdown']:.2%}"
        )
        if benchmark_ret_value is not None:
            print(
                f"Strategy return: {strategy_return:.2%} vs {self.benchmark_symbol} {benchmark_ret_value:.2%} "
                f"(excess {outperformance:.2%})"
            )
        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _init_reference_distribution(self) -> None:
        """Bootstrap mean and std for the spread using historical data."""

        start = _iso_date(self.lookback_days)
        end = _iso_date(0)
        prices = self._fetch_close_frame(start, end, self.timeframe)
        if prices.empty:
            raise RuntimeError("Unable to initialise spread statistics; no data returned.")

        spread = prices[self.symbol_a] - self.hedge_ratio * prices[self.symbol_b]
        mean = spread.mean()
        std = spread.std(ddof=0)
        if std == 0 or pd.isna(std):
            raise RuntimeError("Historical spread has zero standard deviation; can't trade this pair.")

        self.spread_mean = mean
        self.spread_std = std
        self._last_stat_refresh = datetime.now(UTC)
        print(
            f"PairsTradeStrategy stats initialised: mean={self.spread_mean:.4f}, "
            f"std={self.spread_std:.4f} (window ~{len(spread)} bars)"
        )

    def _fetch_close_frame(
        self,
        start_date: str,
        end_date: Optional[str],
        timeframe: str,
        symbols: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Return a DataFrame with aligned close prices for both symbols."""

        symbols = symbols or [self.symbol_a, self.symbol_b]
        data = self.data_handler.get_historical_bars(symbols, timeframe, start=start_date, end=end_date)
        if not data:
            return pd.DataFrame()

        frames = []
        for symbol in symbols:
            df = data.get(symbol)
            if df is None or df.empty:
                continue
            df = df.copy()
            df.index = pd.to_datetime(df.index)
            if getattr(df.index, "tz", None) is not None:
                df.index = df.index.tz_convert("UTC").tz_localize(None)
            frames.append(df[["close"]].rename(columns={"close": symbol}))

        if len(frames) != len(symbols):
            return pd.DataFrame()

        merged = pd.concat(frames, axis=1).dropna()
        return merged

    def _fetch_close_series(
        self, symbol: str, start_date: str, end_date: str, timeframe: str
    ) -> pd.Series:
        data = self.data_handler.get_historical_bars([symbol], timeframe, start=start_date, end=end_date)
        if not data:
            return pd.Series(dtype=float)
        df = data.get(symbol)
        if df is None or df.empty:
            return pd.Series(dtype=float)
        series = df.copy()
        series.index = pd.to_datetime(series.index)
        if getattr(series.index, "tz", None) is not None:
            series.index = series.index.tz_convert("UTC").tz_localize(None)
        return series["close"].dropna()

    def _latest_close(self, symbol: str) -> Optional[float]:
        """Fetch the latest bar and return its closing price."""

        latest_bar = self.data_handler.get_latest_bar(symbol)
        if latest_bar is None:
            return None
        if isinstance(latest_bar, dict):
            return latest_bar.get("close") or latest_bar.get("c")
        for attr in ("close", "c", "price"):
            if hasattr(latest_bar, attr):
                return getattr(latest_bar, attr)
        return None

    def _compute_z_score(self, price_a: float, price_b: float) -> float:
        if self.spread_mean is None or self.spread_std is None:
            raise RuntimeError("Spread statistics are not initialised.")
        spread = price_a - self.hedge_ratio * price_b
        return (spread - self.spread_mean) / self.spread_std

    def _evaluate_rules(self, z_score: float) -> List[Signal]:
        """Translate z-score into a set of two-legged signals."""

        signals: List[Signal] = []
        if self.position == "flat":
            if z_score >= self.entry_threshold:
                signals = self._open_short_spread()
            elif z_score <= -self.entry_threshold:
                signals = self._open_long_spread()
        elif self.position == "short" and z_score <= self.exit_threshold:
            signals = self._close_short_spread()
        elif self.position == "long" and z_score >= -self.exit_threshold:
            signals = self._close_long_spread()
        return signals

    def _open_short_spread(self) -> List[Signal]:
        self.position = "short"
        return [
            self._build_signal(self.symbol_a, "sell", self.quantity),
            self._build_signal(self.symbol_b, "buy", self._hedge_quantity()),
        ]

    def _open_long_spread(self) -> List[Signal]:
        self.position = "long"
        return [
            self._build_signal(self.symbol_a, "buy", self.quantity),
            self._build_signal(self.symbol_b, "sell", self._hedge_quantity()),
        ]

    def _close_short_spread(self) -> List[Signal]:
        self.position = "flat"
        return [
            self._build_signal(self.symbol_a, "buy", self.quantity),
            self._build_signal(self.symbol_b, "sell", self._hedge_quantity()),
        ]

    def _close_long_spread(self) -> List[Signal]:
        self.position = "flat"
        return [
            self._build_signal(self.symbol_a, "sell", self.quantity),
            self._build_signal(self.symbol_b, "buy", self._hedge_quantity()),
        ]

    def _build_signal(self, symbol: str, action: str, qty: int) -> Signal:
        return {
            "symbol": symbol,
            "action": action,
            "qty": int(qty),
            "type": "market",
            "time_in_force": "day",
        }

    def _hedge_quantity(self) -> int:
        scaled = abs(self.hedge_ratio) * self.quantity
        return max(1, int(round(scaled)))

    def _execute_signals(self, signals: List[Signal]) -> None:
        for signal in signals:
            self.execution_handler.execute_order(signal)

    # ------------------------------------------------------------------
    # Stat / risk helpers
    # ------------------------------------------------------------------
    def _maybe_refresh_spread_stats(self, force: bool = False) -> None:
        if force or self._last_stat_refresh is None:
            self._init_reference_distribution()
            return

        refresh_delta = timedelta(days=max(1, self.stat_refresh_days))
        elapsed = datetime.now(UTC) - self._last_stat_refresh
        if elapsed >= refresh_delta:
            self._init_reference_distribution()

    def _rolling_window_bars(self, timeframe: str) -> int:
        minutes = self._timeframe_to_minutes(timeframe)
        if minutes == 0:
            return max(10, self.lookback_days)
        bars = int(self.lookback_days * 1440 / minutes)
        return max(10, bars)

    @staticmethod
    def _timeframe_to_minutes(timeframe: str) -> int:
        timeframe = timeframe.strip().upper()
        if timeframe.endswith("MIN"):
            return int(timeframe[:-3])
        if timeframe.endswith("H"):
            return int(timeframe[:-1]) * 60
        if timeframe.endswith("D"):
            return int(timeframe[:-1]) * 1440
        mapping = {"1D": 1440, "1H": 60, "4H": 240, "15MIN": 15, "5MIN": 5, "1MIN": 1}
        return mapping.get(timeframe, 0)

    def _compute_sharpe(self, returns: pd.Series, timeframe: str) -> float:
        if returns.empty or returns.std() == 0:
            return 0.0
        periods = self._periods_per_year(timeframe)
        return float((returns.mean() / returns.std()) * sqrt(periods))

    def _compute_max_drawdown(self, equity: pd.Series) -> float:
        if equity.empty:
            return 0.0
        running_max = equity.cummax()
        drawdown = (equity / running_max) - 1.0
        if drawdown.empty:
            return 0.0
        return float(abs(drawdown.min()))

    def _periods_per_year(self, timeframe: str) -> int:
        minutes = self._timeframe_to_minutes(timeframe)
        if minutes == 0:
            return 252
        periods_per_day = max(1, int(1440 / minutes))
        return periods_per_day * 252
