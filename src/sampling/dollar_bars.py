
import pandas as pd
import numpy as np

def get_dollar_bars(trades_df, threshold=1_000_000):
    """
    Constructs Dollar Bars from a DataFrame of trades.
    
    Args:
        trades_df: pd.DataFrame with columns 'price' and 'size'. 
                   The index should be a DatetimeIndex (timestamps).
        threshold: Dollar volume threshold to sample a bar (e.g., 1,000,000).
        
    Returns:
        pd.DataFrame: Dollar Bars with standard OHLCV columns + 'dollar_volume'.
    """
    
    if trades_df is None or trades_df.empty:
        return pd.DataFrame()

    # Ensure we work with a copy and sorted by time
    df = trades_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        # unexpected, but let's try to fix or error
        if 'timestamp' in df.columns:
            df = df.set_index('timestamp')
            df.index = pd.to_datetime(df.index)
        else:
            raise ValueError("trades_df must have a DatetimeIndex or a 'timestamp' column.")

    df = df.sort_index()

    # Calculate dollar value of each trade
    df['dollar_value'] = df['price'] * df['size']
    
    # Calculate cumulative dollar value
    # We want to group trades such that sum(dollar_value) >= threshold
    
    # Fast vectorized approach using cumulative sum
    df['cum_dollar_value'] = df['dollar_value'].cumsum()
    
    # Determine group/bar IDs
    # Floor division by threshold gives us a 'bucket' ID
    # However, this aligns to fixed grid 0, 1M, 2M... 
    # Lopez de Prado suggests sampling *every time* we cross the threshold.
    # But strictly speaking, standard implementation often just resets.
    # A simple way: (cumsum // threshold) gives a group ID.
    
    # This creates buckets of size 'threshold'.
    # Note: This is an approximation. A more precise loop would cut exactly at the trade 
    # that crosses, possibly splitting a trade. But for high freq data, 
    # keeping trades atomic is usually fine.
    
    group_ids = df['cum_dollar_value'] // threshold
    
    # We want the first bar to be separate. 
    # If the first trade is huge, it might skip 0.
    
    # Group by this ID
    grouped = df.groupby(group_ids)
    
    # Aggregation logic
    ohlcv = grouped.agg({
        'price': ['first', 'max', 'min', 'last'], # Open, High, Low, Close
        'size': 'sum',                             # Volume
        'dollar_value': 'sum',                     # Total Dollar Volume
        # We can also capture the timestamp of the last trade in the bar
    })
    
    # Flatten MultiIndex columns
    ohlcv.columns = ['open', 'high', 'low', 'close', 'volume', 'dollar_volume']
    
    # The index currently is the 'group_id' (0, 1, 2...). 
    # We want the index to be the timestamp of the CLOSING trade of that bar.
    # Let's get the max timestamp for each group.
    
    # Note: df.index is the timestamp.
    close_timestamps = grouped.apply(lambda x: x.index[-1])
    
    ohlcv.index = close_timestamps
    ohlcv.index.name = 'timestamp'
    
    # Filter out any accidentally empty bars (shouldn't happen with this logic)
    ohlcv = ohlcv[ohlcv['dollar_volume'] > 0]
    
    return ohlcv
