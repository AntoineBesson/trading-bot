
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
    df['cum_dollar_value'] = df['dollar_value'].cumsum()
    
    # Determine group/bar IDs
    # Temporarily reset index to keep timestamp available for aggregation
    df_reset = df.reset_index()
    timestamp_col = df_reset.columns[0] # Usually 'index' or 'timestamp'
    
    # Determine group/bar IDs (AFTER reset_index so indices align)
    group_ids = df_reset['cum_dollar_value'] // threshold
    
    # Group by this ID
    grouped = df_reset.groupby(group_ids)
    
    # Aggregation logic
    ohlcv = grouped.agg({
        'price': ['first', 'max', 'min', 'last'], # Open, High, Low, Close
        'size': 'sum',                             # Volume
        'dollar_value': 'sum',                     # Total Dollar Volume
        timestamp_col: 'last'                      # Close Timestamp
    })
    
    # Flatten MultiIndex columns
    ohlcv.columns = ['open', 'high', 'low', 'close', 'volume', 'dollar_volume', 'timestamp']
    
    # Set the timestamp as index
    ohlcv = ohlcv.set_index('timestamp')
    ohlcv.sort_index(inplace=True)
    
    # Filter out any accidentally empty bars
    ohlcv = ohlcv[ohlcv['dollar_volume'] > 0]
    
    return ohlcv
