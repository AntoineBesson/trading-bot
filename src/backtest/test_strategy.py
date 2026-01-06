from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from src.backtest.permutation_tester import PermutationTester
from src.strategies.donchian_breakout import DonchianBreakoutStrategy


def load_spy_history(
    client: Optional[StockHistoricalDataClient] = None,
    lookback_days: int = 120,
) -> pd.DataFrame:
    """Fetch hourly SPY bars from Alpaca."""

    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")
    if client is None:
        if not api_key or not api_secret:
            raise RuntimeError("Set ALPACA_API_KEY and ALPACA_API_SECRET before running the backtest script.")
        client = StockHistoricalDataClient(api_key, api_secret)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    request = StockBarsRequest(
        symbol_or_symbols="SPY",
        timeframe=TimeFrame.Hour,
        start=start,
        end=end,
        limit=None,
    )
    bars = client.get_stock_bars(request)
    df = bars.df

    # Normalize to a simple price frame indexed by timestamp.
    if isinstance(df.index, pd.MultiIndex):
        level_names = [name or "" for name in df.index.names]
        if "symbol" in level_names:
            df = df.xs("SPY", level=level_names.index("symbol"))
        else:
            df = df.xs("SPY")
    if isinstance(df.columns, pd.MultiIndex):
        if "symbol" in df.columns.names:
            df = df.xs("SPY", axis=1, level="symbol")
        else:
            df = df.droplevel(0, axis=1)
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = df.sort_index()
    return df[[col for col in ("open", "high", "low", "close", "volume") if col in df.columns]]


def main() -> None:
    df = load_spy_history()
    tester = PermutationTester(df)
    p_value = tester.run_test(DonchianBreakoutStrategy, lookback_param=20, n_permutations=100)

    print(f"Final P-Value: {p_value}")
    if p_value < 0.05:
        print("PASS: The strategy found real patterns!")
    else:
        print("FAIL: The strategy is likely overfit or lucky.")


if __name__ == "__main__":
    main()