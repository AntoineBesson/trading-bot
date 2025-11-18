import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.strategies.pairs_trade import PairsTradeStrategy


class FakeDataHandler:
    def __init__(self):
        idx = pd.date_range(end=pd.Timestamp.today(), periods=200, freq="D")
        base = pd.Series(range(200), index=idx)
        noise = pd.Series(np.sin(np.linspace(0, 6.28, len(idx))), index=idx)
        self.data = {
            "AAA": pd.DataFrame({"close": base + 2 + noise}),
            "BBB": pd.DataFrame({"close": base}),
            "SPY": pd.DataFrame({"close": base + 5}),
        }
        self.latest_prices = {symbol: float(df["close"].iloc[-1]) for symbol, df in self.data.items()}

    def get_historical_bars(self, symbols, timeframe, start, end=None):
        return {symbol: self.data[symbol] for symbol in symbols if symbol in self.data}

    def get_latest_bar(self, symbol):
        return {"close": self.latest_prices[symbol]}

    def set_latest(self, symbol, price):
        self.latest_prices[symbol] = price


class FakeExecutionHandler:
    def __init__(self):
        self.orders = []

    def execute_order(self, signal):
        self.orders.append(signal)
        return signal


def test_pairs_strategy_generates_entry_and_exit_signals():
    data = FakeDataHandler()
    execution = FakeExecutionHandler()
    strategy = PairsTradeStrategy(
        data_handler=data,
        execution_handler=execution,
        symbol_a="AAA",
        symbol_b="BBB",
        hedge_ratio=1.0,
        entry_threshold=1.0,
        exit_threshold=0.0,
        quantity=5,
        lookback_days=30,
        timeframe="1D",
        auto_execute=False,
        benchmark_symbol=None,
        initial_capital=1_000.0,
        stat_refresh_days=30,
    )

    # Force a large positive z-score -> open short spread
    data.set_latest("AAA", strategy.spread_mean + 3 * strategy.spread_std + data.latest_prices["BBB"])
    signals = strategy.generate_signal()
    assert len(signals) == 2
    assert signals[0]["action"] == "sell"
    assert strategy.position == "short"

    # Revert the spread -> close position
    data.set_latest("AAA", strategy.spread_mean + data.latest_prices["BBB"])
    signals = strategy.generate_signal()
    assert len(signals) == 2
    assert signals[0]["action"] == "buy"
    assert strategy.position == "flat"


def test_run_backtest_uses_cached_benchmark():
    data = FakeDataHandler()
    execution = FakeExecutionHandler()
    strategy = PairsTradeStrategy(
        data_handler=data,
        execution_handler=execution,
        symbol_a="AAA",
        symbol_b="BBB",
        hedge_ratio=1.0,
        entry_threshold=1.0,
        exit_threshold=0.0,
        quantity=5,
        lookback_days=30,
        timeframe="1D",
        auto_execute=False,
        benchmark_symbol="SPY",
        initial_capital=1_000.0,
        stat_refresh_days=30,
    )

    end_date = pd.Timestamp.today().date().isoformat()
    start_date = (pd.Timestamp.today() - pd.Timedelta(days=100)).date().isoformat()
    bench_index = pd.date_range(start=start_date, periods=50, freq="D")
    bench_series = pd.Series(np.linspace(100, 110, len(bench_index)), index=bench_index)

    summary = strategy.run_backtest(
        start_date=start_date,
        end_date=end_date,
        timeframe="1D",
        benchmark_series=bench_series,
    )

    expected_return = float(bench_series.iloc[-1] / bench_series.iloc[0] - 1)
    assert summary["benchmark_return"] == pytest.approx(expected_return)
    assert summary["excess_return"] is not None
