import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import types

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.options.data_handler import OptionDataHandler
from src.options.greeks import GreeksCalculator
from src.options.multileg import MultiLegExecutionHelper
from src.strategies.option_pairs import OptionPairsStrategy


class FakeDataHandler:
    def __init__(self):
        idx = pd.date_range(end=pd.Timestamp.today(tz=UTC), periods=180, freq="D").tz_localize(None)
        base = pd.Series(np.linspace(90, 110, len(idx)), index=idx)
        drift = pd.Series(np.linspace(0, 5, len(idx)), index=idx)
        self.frames = {
            "AAA": pd.DataFrame({"close": base + drift}),
            "BBB": pd.DataFrame({"close": base}),
        }
        self.latest_prices = {symbol: float(df["close"].iloc[-1]) for symbol, df in self.frames.items()}

    def get_historical_bars(self, symbols, timeframe, start, end=None):
        # ignore timeframe/start/end for deterministic tests
        return {symbol: self.frames[symbol] for symbol in symbols if symbol in self.frames}

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


def test_greeks_calculator_strike_search():
    calc = GreeksCalculator(rate=0.01)
    strike = calc.find_strike_for_delta(0.4, "call", spot=100, ttm=30 / 252, vol=0.2)
    metrics = calc.metrics("call", 100, strike, 30 / 252, 0.2)
    assert 0.35 < metrics["delta"] < 0.45
    assert metrics["price"] > 0


def test_option_data_handler_snapshot_has_fields():
    handler = OptionDataHandler(FakeDataHandler())
    snapshot = handler.get_option_snapshot("AAA", option_type="call", target_delta=0.5, days_to_expiry=30)
    assert snapshot is not None
    assert snapshot.price > 0
    assert 0 < snapshot.delta < 1


def test_multileg_helper_executes_fallback():
    execution = FakeExecutionHandler()
    helper = MultiLegExecutionHelper(execution)
    legs = [
        {
            "action": "buy",
            "qty": 1,
            "asset_type": "option",
            "underlying": "AAA",
            "option_type": "call",
            "strike": 100,
            "expiration": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            "limit_price": 3.5,
        },
        {
            "action": "sell",
            "qty": 1,
            "asset_type": "option",
            "underlying": "BBB",
            "option_type": "call",
            "strike": 100,
            "expiration": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            "limit_price": 3.0,
        },
    ]
    result = helper.execute(legs, net_price_type="debit", net_price=0.5)
    assert "payload" in result and len(result["payload"]["legs"]) == 2
    assert len(execution.orders) == 2


def test_option_pairs_strategy_generates_signals():
    data = FakeDataHandler()
    execution = FakeExecutionHandler()
    strategy = OptionPairsStrategy(
        data_handler=data,
        execution_handler=execution,
        symbol_a="AAA",
        symbol_b="BBB",
        option_type="call",
        target_delta=0.45,
        entry_threshold=0.2,
        exit_threshold=0.0,
        contracts=1,
        lookback_days=60,
        timeframe="1D",
        auto_execute=False,
    )
    strategy.stat_refresh_days = 10 ** 6
    strategy.spread_mean = 0.0
    strategy.spread_std = 0.01
    strategy._compute_z_score = types.MethodType(lambda self, spread: 1.0, strategy)
    signals = strategy.generate_signal()
    assert len(signals) == 2
    assert signals[0]["action"] == "sell"
    assert strategy.position == "short"

    strategy._compute_z_score = types.MethodType(lambda self, spread: -0.5, strategy)
    signals = strategy.generate_signal()
    assert len(signals) == 2
    assert signals[0]["action"] == "buy"
    assert strategy.position == "flat"
