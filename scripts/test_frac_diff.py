
import sys
import os
import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from features.frac_diff import frac_diff_ffd, get_weights_ffd

def generate_trend_series(n=2000):
    np.random.seed(42)
    # Price = Cumsum of returns
    returns = np.random.normal(0, 1, n)
    price = 100 + np.cumsum(returns)
    # Add a strong trend
    timestamps = np.linspace(0, 10, n)
    price = price + (timestamps**2)
    
    dates = pd.date_range(start='2020-01-01', periods=n, freq='D')
    return pd.Series(price, index=dates, name='close')

def main():
    print("--- Testing Fractional Differentiation ---")
    
    # 1. Generate Non-Stationary Series
    series = generate_trend_series()
    # Use Log Prices as standard practice
    # (Actually Lopez de Prado often diffs log prices, 
    # but sometimes diffs raw prices if level matters. Stick to log prices for financial series.)
    log_prices = np.log(series)
    
    print(f"Series Length: {len(series)}")
    
    # Check ADF on original log prices
    adf_p_val = adfuller(log_prices.dropna())[1]
    print(f"Original Log Price ADF p-value: {adf_p_val:.4f} (Likely > 0.05, Non-Stationary)")
    
    # 2. Sweep d values
    d_values = [0.1, 0.3, 0.5, 0.7, 1.0]
    
    results = []
    
    print("\nSweeping d values...")
    for d in d_values:
        diffed = frac_diff_ffd(log_prices, d, thres=1e-4) # 1e-4 allows shorter windows for test speed
        
        if diffed.empty:
            print(f"d={d}: Result empty (window too large?)")
            continue
            
        # ADF Test
        # We need to drop NaNs
        clean_diff = diffed.dropna()
        p_val = adfuller(clean_diff)[1]
        
        # Correlation with original log prices
        # We need to align indices
        common_idx = log_prices.index.intersection(clean_diff.index)
        corr = np.corrcoef(log_prices.loc[common_idx], clean_diff.loc[common_idx])[0, 1]
        
        print(f"d={d}: p-value={p_val:.5f} | Corr={corr:.4f} | Size={len(clean_diff)}")
        
        results.append({
            'd': d,
            'p_value': p_val,
            'corr': corr
        })
        
    print("\n--- Summary ---")
    print("Goal: Find minimum 'd' where p-value < 0.05, while maximizing Correlation.")
    
    # Simple logic to find optimal d
    optimal_d = None
    for res in results:
        if res['p_value'] < 0.05:
            # First one to pass stationarity is our optimal (because we sorted d_values)
            optimal_d = res['d']
            print(f"Optimal d found: {optimal_d}")
            break
            
    if optimal_d:
        print("Success! Fractional Differentiation preserved memory better than d=1.0?")
        d1_res = [r for r in results if r['d'] == 1.0][0]
        opt_res = [r for r in results if r['d'] == optimal_d][0]
        
        print(f"d={optimal_d} Correlation: {opt_res['corr']:.4f}")
        print(f"d=1.0 Correlation: {d1_res['corr']:.4f}")
        
        if opt_res['corr'] > d1_res['corr']:
            print("Verified: Fractional Diff retains more memory than standard difference.")
        else:
            print("Note: In this specific noise case, d=1.0 retained similar memory (or trend was weak).")
            
    else:
        print("Warning: No d value made the series stationary. Try increasing d or check data.")

if __name__ == "__main__":
    main()
