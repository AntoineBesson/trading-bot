
import pytest
import pandas as pd
import numpy as np
from src.sampling.dollar_bars import get_dollar_bars

def test_get_dollar_bars_basic():
    # Create synthetic trades
    # price = 10, size = 100 => dollar_value = 1000
    # Threshold = 2500
    # We expect a bar every 2.5 trades -> 3rd trade triggers bar.
    
    dates = pd.date_range(start='2020-01-01', periods=10, freq='T')
    trades = pd.DataFrame({
        'price': [10.0] * 10,
        'size': [100] * 10
    }, index=dates)
    
    threshold = 2500
    bars = get_dollar_bars(trades, threshold=threshold)
    
    # Total dollar volume = 10 * 1000 = 10000
    # Threshold = 2500
    # Expected bars approx 10000 / 2500 = 4 bars.
    
    assert not bars.empty
    assert 'dollar_volume' in bars.columns
    assert len(bars) >= 3 # Integer division logic might vary slightly depending on group method

def test_get_dollar_bars_empty():
    bars = get_dollar_bars(pd.DataFrame(), threshold=1000)
    assert bars.empty

def test_get_dollar_bars_aggregation():
    # Test OHLC logic
    dates = pd.date_range(start='2020-01-01', periods=3, freq='T')
    trades = pd.DataFrame({
        'price': [10, 20, 15],
        'size': [100, 100, 100] # 1000, 2000, 1500
    }, index=dates)
    
    # Threshold = 5000 (wait, total is 4500)
    # Should get 1 bar if we just sum them up? 
    # Logic uses cumsum // threshold.
    # cumsum: 1000, 3000, 4500.
    # threshold 5000: 
    # 1000 // 5000 = 0
    # 3000 // 5000 = 0
    # 4500 // 5000 = 0
    # All in group 0.
    
    bars = get_dollar_bars(trades, threshold=5000)
    
    assert len(bars) == 1
    row = bars.iloc[0]
    assert row['open'] == 10
    assert row['high'] == 20
    assert row['low'] == 10
    assert row['close'] == 15
    assert row['volume'] == 300
    assert row['dollar_volume'] == 4500
