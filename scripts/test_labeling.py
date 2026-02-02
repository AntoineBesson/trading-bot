
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from labeling.barriers import get_triple_barrier_events, get_bins, get_volatility

def main():
    print("Testing Triple Barrier Method...")
    
    # 1. create dummy price data (Geometric Brownian Motion or just a sine wave with trend)
    dates = pd.date_range(start='2024-01-01', periods=500, freq='h') # 500 hours
    
    prices = [100.0]
    np.random.seed(42)
    for _ in range(499):
        # Random walk
        change = np.random.normal(0, 0.01) # 1% std dev
        prices.append(prices[-1] * (1 + change))
        
    close = pd.Series(prices, index=dates)
    
    print(f"Generated {len(close)} price points.")
    print(close.head())
    
    # 2. Compute Volatility (Target)
    vol = get_volatility(close, span=20)
    print("\nVolatility (last 5):")
    print(vol.tail())
    
    # 3. Define Events (Let's say we enter a trade every 10 bars)
    t_events = close.index[::10]
    print(f"\nDefining {len(t_events)} entry events.")
    
    # 4. Vertical Barrier (Time Limit) - Say 24 hours later
    vertical_barriers = t_events + timedelta(hours=24)
    # Ensure they don't exceed data bounds (handled by logic, but clean up is good)
    vertical_barriers = pd.Series(vertical_barriers, index=t_events)
    
    # 5. Run Triple Barrier
    print("\nRunning Triple Barrier (PT=2, SL=1)...")
    # Profit Take = 2 * Volatility
    # Stop Loss = 1 * Volatility
    events = get_triple_barrier_events(
        close=close,
        t_events=t_events,
        pt_sl=[2, 1], 
        target=vol,
        min_ret=0.001, # Ignroe if vol is super low
        vertical_barrier_times=vertical_barriers
    )
    
    print("\nEvents Found (Touched a barrier or expired):")
    print(events.head())
    print(f"Total events triggered: {len(events)}")
    
    # 6. Apply Labeling (Bins)
    print("\nApplying Labels...")
    labels = get_bins(events, close)
    
    print(labels.head())
    print("\nLabel Distribution:")
    print(labels['bin'].value_counts())
    
    # Sanity Check for Meta-Labeling (Side)
    print("\n--- Meta-Labeling Test ---")
    # Assume we always bet Long (Side = 1)
    side = pd.Series(1, index=t_events)
    
    # Re-run getting events (reuse technically, but just to be clean for the function call)
    events_meta = get_triple_barrier_events(
        close=close,
        t_events=t_events,
        pt_sl=[1, 1], # Symmetric
        target=vol,
        min_ret=0.001,
        vertical_barrier_times=vertical_barriers,
        side=side
    )
    
    labels_meta = get_bins(events_meta, close)
    print("\nMeta-Labels (1=Win, 0=Loss/Time):")
    print(labels_meta['bin'].value_counts())
    
if __name__ == "__main__":
    main()
