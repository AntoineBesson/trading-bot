
import sys
import os
import pandas as pd
import numpy as np

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from backtest.cross_validation import PurgedKFold

def main():
    print("--- Testing Purged K-Fold CV ---")
    
    # 1. Generate Synthetic Data
    n_samples = 20
    dates = pd.date_range(start='2024-01-01', periods=n_samples, freq='D')
    
    # Feature matrix X (index is t0)
    X = pd.DataFrame(np.random.rand(n_samples, 2), index=dates, columns=['f1', 'f2'])
    
    # 2. Define t1 (Labels overlap)
    # Let's say each label looks 3 days into the future
    t1 = dates + pd.Timedelta(days=3)
    t1 = pd.Series(t1, index=dates)
    
    print("Data Setup:")
    print(f"Total Samples: {n_samples}")
    print("Label duration: 3 days (Overlaps!)")
    
    # 3. Setup CV
    n_splits = 3
    pkf = PurgedKFold(n_splits=n_splits, t1=t1, pct_embargo=0.01) # 1% embargo
    
    print(f"\nRunning {n_splits}-Split PurgedKFold with Embargo...")
    
    for i, (train_idx, test_idx) in enumerate(pkf.split(X)):
        print(f"\n--- Split {i+1} ---")
        
        train_dates = X.index[train_idx]
        test_dates = X.index[test_idx]
        
        print(f"Train Size: {len(train_idx)} | Test Size: {len(test_idx)}")
        print(f"Test Interval: {test_dates[0].date()} to {test_dates[-1].date()}")
        
        # Verify Purging
        # Check overlaps
        test_start = test_dates[0]
        # Max t1 in test set
        test_t1_max = t1.loc[test_dates].max()
        
        print(f"Test Label Span: {test_start.date()} -> {test_t1_max.date()}")
        
        # Check if any train sample overlaps
        overlaps = 0
        for t_idx in train_idx:
            t0_train = X.index[t_idx]
            t1_train = t1.loc[t0_train]
            
            # Intersection logic
            if (t0_train <= test_t1_max) and (t1_train >= test_start):
                overlaps += 1
                print(f"  [FAIL] Leakage! Train {t0_train.date()} overlaps with Test.")
                
        if overlaps == 0:
            print("  [PASS] No leakage detected.")
        else:
            print(f"  [FAIL] {overlaps} leaking samples found.")
            
        # Visual Gap Check
        # Check gaps between train and test blocks
        sorted_dates = sorted(list(train_dates) + list(test_dates))
        # Just print the indices to see gaps
        print(f"Train Indices: {train_idx}")
        print(f"Test Indices:  {test_idx}")

if __name__ == "__main__":
    main()
