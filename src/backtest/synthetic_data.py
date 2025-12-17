import pandas as pd
import numpy as np

def generate_synthetic_data(length=1000, start_price=100, volatility=0.02):
    """
    Generates synthetic OHLC data using a random walk.
    """
    dates = pd.date_range(start='2020-01-01', periods=length, freq='D')
    
    # Generate returns
    returns = np.random.normal(0, volatility, length)
    price_path = start_price * (1 + returns).cumprod()
    
    data = {
        'open': [],
        'high': [],
        'low': [],
        'close': [],
        'volume': []
    }
    
    for price in price_path:
        # Simulate intraday movement
        high = price * (1 + abs(np.random.normal(0, volatility/2)))
        low = price * (1 - abs(np.random.normal(0, volatility/2)))
        close = np.random.uniform(low, high)
        open_p = np.random.uniform(low, high)
        
        data['open'].append(open_p)
        data['high'].append(high)
        data['low'].append(low)
        data['close'].append(close)
        data['volume'].append(np.random.randint(1000, 100000))
        
    df = pd.DataFrame(data, index=dates)
    return df
