import pandas as pd
import numpy as np

def get_weights_ffd(d, thres, lim=2000):
    """
    Calculates weights for the fractional differentiation (FFD method).
    
    Args:
        d (float): The order of differentiation.
        thres (float): The threshold for weight cutoff. 
                       Weights smaller than this are dropped.
        lim (int): Max history limit.
        
    Returns:
        np.array: The weights (reversed, so w[0] is for the current item).
    """
    w, k = [1.], 1
    while True:
        w_k = -w[-1] / k * (d - k + 1)
        if abs(w_k) < thres:
            break
        w.append(w_k)
        k += 1
        if k >= lim:
            break
            
    # w is currently [w0, w1, w2...]
    # We want to apply it as a dot product with [x_t, x_{t-1}, x_{t-2}...]
    return np.array(w[::-1]).reshape(-1, 1)

def frac_diff_ffd(series, d, thres=1e-5):
    """
    Applies Fixed-Width Window Fractional Differentiation.
    
    Args:
        series (pd.Series): The time series to differentiate (e.g., log prices).
        d (float): The order of differentiation (e.g., 0.4).
        thres (float): Threshold for weight cutoff.
    
    Returns:
        pd.Series: The fractionally differentiated series.
    """
    # 1. Compute weights
    w = get_weights_ffd(d, thres)
    width = len(w) - 1
    
    # 2. Apply weights using rolling window
    # We need a window of size 'len(w)'. 
    # Because 'w' is reversed, we can just dot product.
    
    df = {}
    name = series.name if series.name else 'value'
    
    # Handling pandas series
    # We iterate? Or use rolling().apply()? 
    # rolling().apply() is slow for dot products usually, but cleaner code.
    # Let's use a standard pandas rolling approach.
    
    series_f = series.ffill().dropna()
    
    if len(series_f) < width:
        return pd.Series(index=series.index, dtype=float)
        
    # Vectorized Rolling would be:
    # return series_f.rolling(window=width+1).apply(lambda x: np.dot(x, w)[0], raw=True)
    
    # However, for huge datasets, loop might be clearer or strides.
    # Let's stick to pandas rolling for safety and readability.
    
    # Note: 'w' shape is (K, 1). 'x' will be (K,).
    # Since w is already reversed (w[-1] is w_0), we check order.
    # get_weights_ffd returns w[::-1]. 
    # So w[0] corresponds to the oldest lag in the window?
    # Wait, let's verify standard definition.
    # diff = sum(w_k * x_{t-k})
    # w = [1, -d, d(d-1)/2 ...] corresponds to k=0, 1, 2...
    # So w[0] is for x_t, w[1] is for x_{t-1}.
    
    # If using rolling window of size N.
    # The snippet passed to apply is [x_{t-N+1}... x_t].
    # So x_t is at index -1.
    # x_{t-1} is at index -2.
    
    # So we want w[0] * window[-1] + w[1] * window[-2]...
    # My get_weights returned w[::-1]. 
    # So w_out[0] is w_last (smallest weight).
    # w_out[-1] is w_0 (current, weight ~1).
    
    # So if we simply dot product 'window' (old->new) with 'w_out' (small->big/current), it matches.
    # window[0] (oldest) * w_out[0] (smallest weight for oldest lag) ...
    
    # Correct.
    
    w_flat = w.flatten()
    
    # Use pandas rolling
    # raw=True speeds it up
    res = series_f.rolling(window=width+1).apply(lambda x: np.dot(x, w_flat), raw=True)
    
    return res.dropna()

