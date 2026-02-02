import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from strategies.primary_models import MovingAverageCrossover
from labeling.barriers import get_triple_barrier_events, get_bins, get_volatility
from ml.meta_labeler import MetaLabeler

def generate_synthetic_data(n=1000):
    """
    Generates a sine wave + trend + noise
    Returns a DataFrame with 1-min frequency
    """
    dates = pd.date_range(start='2024-01-01', periods=n, freq='min')
    x = np.linspace(0, 50, n)
    
    # Components
    trend = x * 0.5
    seasonality = 10 * np.sin(x)
    noise = np.random.normal(0, 2, n)
    
    prices = 100 + trend + seasonality + noise
    return pd.Series(prices, index=dates, name='close')

def main():
    print("--- Starting Pipeline Integration Test ---")
    
    # 1. Data Generation
    print("1. Generating Synthetic Data...")
    close = generate_synthetic_data(n=2000)
    
    # 2. Primary Model (Signal Generation)
    print("2. Running Primary Model (MA Crossover)...")
    pm = MovingAverageCrossover(fast_window=10, slow_window=50)
    primary_events = pm.generate_signals(close)
    
    print(f"   Found {len(primary_events)} primary signals.")
    if primary_events.empty:
        print("   No signals found. Exiting.")
        return

    # 3. Triple Barrier Labeling
    print("3. Applying Triple Barrier Method...")
    
    # Dynamic Volatility
    vol = get_volatility(close, span=20)
    
    # Vertical Barrier: 100 bars later
    # FIX: Initialize properly.
    t_vertical_values = primary_events.index + pd.Timedelta(minutes=50)
    vertical_barriers = pd.Series(t_vertical_values, index=primary_events.index)
    
    # Optional: Filter those that go beyond data end (set to NaT means no time limit, or just drop)
    # If we drop them from the Series, they will come back as NaT in the reidexing inside get_triple_barrier_events
    # which is treated as "no vertical barrier".
    # Let's keep it simple. The tool handles them.
    
    # Note: We pass 'side' to the labeling to perform Meta-Labeling correctly
    barrier_events = get_triple_barrier_events(
        close=close,
        t_events=primary_events.index,
        pt_sl=[1, 1], # 1x Vol Profit, 1x Vol Loss
        target=vol,
        min_ret=0.0001,
        vertical_barrier_times=vertical_barriers,
        side=primary_events['side']
    )
    
    # Generate Bins (y)
    labels = get_bins(barrier_events, close)
    print(f"   Generated {len(labels)} labels.")
    print("   Label Distribution (1=Success, 0=Fail/Time):")
    print(labels['bin'].value_counts())
    
    # 4. Feature Extraction (Simple for MVP)
    print("4. Extracting Features for ML...")
    # Features at the time of the trade (t0)
    # We want to predict 'bin' using info available at 't0'
    
    features = pd.DataFrame(index=labels.index)
    features['volatility'] = vol.loc[labels.index]
    features['side'] = primary_events.loc[labels.index, 'side']
    # Add simple momentum: 5-period return
    features['mom5'] = close.pct_change(5).loc[labels.index]
    features['mom20'] = close.pct_change(20).loc[labels.index]
    
    # Clean nans
    features = features.dropna()
    y = labels['bin'].loc[features.index]
    
    print(f"   Training Data Shape: {features.shape}")

    if len(y) < 10:
        print("   Not enough data to train ML. Need more signals.")
        return

    # 5. Train Meta-Model
    print("5. Training Meta-Labeler...")
    ml = MetaLabeler(n_estimators=50, max_depth=3)
    
    # Split Train/Test (Simple split without purging for MVP)
    split_idx = int(len(features) * 0.7)
    X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    ml.fit(X_train, y_train)
    
    # 6. Evaluate
    ml.evaluate(X_test, y_test)
    
    # 7. Example Prediction
    print("\n6. Example Prediction:")
    probs = ml.predict(X_test.head())
    print(probs)
    
    print("\n--- Pipeline Verified ---")

if __name__ == "__main__":
    main()
