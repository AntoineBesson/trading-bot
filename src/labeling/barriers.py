import pandas as pd
import numpy as np

def get_triple_barrier_events(close, t_events, pt_sl, target, min_ret=0, num_threads=1, vertical_barrier_times=None, side=None):
    """
    Implements the Triple Barrier Method as described by Lopez de Prado.
    
    Args:
        close (pd.Series): A pandas Series of close prices. Use bars (e.g. Dollar Bars) if possible.
        t_events (pd.DatetimeIndex or array): The timestamps of the events we want to label (e.g. entry points).
                                              Typically these are the timestamps of the bars or specific signal triggers.
        pt_sl (list): A list of two non-negative floats:
                      pt_sl[0] -> The factor for the profit taking limit.
                      pt_sl[1] -> The factor for the stop loss limit.
                      e.g. [1, 1] means symmetric barriers relative to 'target'.
        target (pd.Series): The absolute width of the horizontal barriers (volatility).
                            Usually a rolling volatility estimate.
                            If barrier is at 2*volatility, then pt_sl=[2, 2] and target=volatility.
        min_ret (float): The minimum target return required for running a triple barrier search.
        num_threads (int): (Not implemented for simplicity, placeholder for optimization).
        vertical_barrier_times (pd.Series): A Series indexed by t_events, containing the timestamps 
                                            of the vertical barriers (time expiration).
        side (pd.Series): (Optional) Side of the bet (1 for long, -1 for short). 
                          Used to flip the meaning of profit/loss for the labeled result.
                          If None, we output the raw barrier touch (1=top, -1=bottom, 0=time).

    Returns:
        pd.DataFrame: Events with columns:
                      - t1: The timestamp of the first barrier touch.
                      - trgt: The target that was used.
                      - type: The type of barrier touched (tp, sl, t1).
                      - side: (Optional) The side provided.
    """
    
    # 1. Get target timestamps
    target = target.loc[t_events]
    target = target[target > min_ret] # Filter out targets smaller than min_ret
    
    if target.empty:
        return pd.DataFrame()

    # 2. Get Vertical Barrier (Time Limit)
    if vertical_barrier_times is None:
        vertical_barrier_times = pd.Series(pd.NaT, index=t_events)

    # 3. Form Events object
    events = pd.DataFrame(index=target.index)
    events['t1'] = vertical_barrier_times[target.index] # Initial vertical barrier
    events['trgt'] = target
    if side is not None:
        events['side'] = side.loc[target.index]

    # 4. Apply Horizontal Barriers (Stop Loss / Profit Take)
    # We will iterate (vectorized-ish) to find the first touch.
    # Note: A fully vectorized solution is complex because each event has a different start time and target.
    # We'll use a loop over events for clarity or a apply implementation.
    # Ideally, we verify against the *future* prices after the event.
    
    # Let's do a simple apply for now. For production on millions of bars, use multiprocessing or numba.
    
    out = events.apply(
        apply_pt_sl_on_t1, 
        axis=1, 
        args=(close, events.index, pt_sl)
    )
    
    events['t1'] = out.dropna()
    
    return events.dropna(subset=['t1']) # Only return events that touched a barrier or ran out of time

def apply_pt_sl_on_t1(req, close, events_index, pt_sl):
    """
    Internal function to find the first touch of the barriers.
    
    req: Row from the 'events' DataFrame. (contains t1 as vertical barrier, trgt)
    close: The price series.
    events_index: The index of all events (not used inside directly but useful for context if needed).
    pt_sl: [pt, sl] multipliers.
    """
    
    
    # req.name is the start time (t0)
    t0 = req.name
    t1 = req['t1'] # Vertical barrier (could be NaT)
    trgt = req['trgt']
    
    # Slice the price series from t0 to t1.
    if pd.isna(t1):
        # If no vertical barrier, check until the end of the series
        path_prices = close[t0:] 
    else:
        path_prices = close[t0:t1]
        
    # We exclude the first point because that's the entry point (return 0)
    path_prices = path_prices.iloc[1:]
    
    if path_prices.empty:
        return np.nan
        
    entry_price = close[t0]
    
    # Use numpy values for speed
    path_prices_values = path_prices.values
    path_index = path_prices.index
    
    # Calculate returns relative to t0 PRICE
    returns_values = (path_prices_values / entry_price) - 1
    
    # Initialize earliest touch as NaT or t1
    first_touch = t1
    
    # Check Profit Take (Upper)
    if pt_sl[0] > 0:
        thresh = trgt * pt_sl[0]
        # Find first index where return >= thresh
        # argmax returns the index of the first occurrence of maximum value (True > False)
        mask = returns_values >= thresh
        if mask.any():
            pt_time = path_index[mask.argmax()]
            if pd.isna(first_touch) or pt_time < first_touch:
                first_touch = pt_time
            
    # Check Stop Loss (Lower)
    if pt_sl[1] > 0:
        thresh = -trgt * pt_sl[1]
        mask = returns_values <= thresh
        if mask.any():
            sl_time = path_index[mask.argmax()]
            if pd.isna(first_touch) or sl_time < first_touch:
                first_touch = sl_time
    
    return first_touch


def get_bins(events, close):
    """
    Generates the labels (1, -1, 0) based on the events and the identified barrier touches (t1).
    
    Args:
        events (pd.DataFrame): Output from get_triple_barrier_events. 
                               Must contain 't1' column.
                               May contain 'side' column.
        close (pd.Series): Price series.
        
    Returns:
        pd.DataFrame: Labeled metadata with 'ret' and 'bin'.
    """
    
    # 1. Prices at t0 (index) and t1
    events = events.dropna(subset=['t1'])
    
    prices_t0 = close.loc[events.index]
    prices_t1 = close.loc[events['t1']]
    
    # Align indices for vectorized op (events.index vs events['t1'].values)
    # returns = (price_t1 / price_t0) - 1
    
    # Careful: prices_t1 uses events['t1'] timestamps, but we need to subtract based on the events index order
    returns = (prices_t1.values / prices_t0.values) - 1
    
    out = pd.DataFrame(index=events.index)
    out['ret'] = returns
    out['t1'] = events['t1']
    
    # 2. Meta-Labeling Logic vs Primary Labeling Logic
    
    if 'side' in events.columns:
        # If 'side' is present, we are doing Meta-Labeling (or validating a strategy).
        # Where 1 = Profit, 0 = Loss.
        # But wait, standard triple barrier usually gives:
        # Return sign? No.
        # If side=1 (Long):
        #   If ret > 0 (Hit PT): Label 1
        #   If ret < 0 (Hit SL): Label 0 (or -1 depending on preference)
        
        # Lopez de Prado (Meta-Labeling):
        # "If the primary model signal was correct => 1, else 0"
        
        # We need to know if the return matches the side.
        
        # If side=1 (Long) and ret > 0 => Correct (1)
        # If side=1 (Long) and ret < 0 => Incorrect (0)
        # If side=-1 (Short) and ret < 0 => Correct (1)
        # If side=-1 (Short) and ret > 0 => Incorrect (0)
        
        # Simple formula: sign(ret) == sign(side) ? 1 : 0
        
        out['bin'] = np.sign(out['ret']) * np.sign(events['side'])
        
        # Map to 0/1 for Meta-Labeling (Binary Classification)
        # If the result is positive, it's a 1. If negative, it's 0. (Ignoring small drift).
        # Actually usually:
        # 1 if ret * side > 0
        # 0 if ret * side <= 0
        out['bin'] = np.where(out['bin'] > 0, 1, 0)
        
    else:
        # Standard Labeling (No side provided)
        # Just tell me which barrier was hit?
        # Or usually: +1 for Top, -1 for Bottom, 0 for Vertical?
        
        # We can deduce based on the return and the initial target width?
        # Or simpler:
        # If ret > 0: 1
        # If ret < 0: -1
        # If ret ~ 0: 0
        
        # Let's stick to simple sign for now.
        out['bin'] = np.sign(out['ret'])
    
    return out

def get_volatility(close, span=100):
    """
    Simple exponentially weighted moving standard deviation of returns.
    Used for dynamic barrier sizing.
    """
    # 1. Compute returns
    # prev_close = close.shift(1)
    # returns = (close / prev_close) - 1
    # returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    
    returns = close.pct_change()
    
    # 2. EWM Std Dev
    vol = returns.ewm(span=span).std()
    
    return vol
