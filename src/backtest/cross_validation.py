from sklearn.model_selection import KFold
import pandas as pd
import numpy as np

class PurgedKFold(KFold):
    """
    Extend KFold class to work with labels that span intervals.
    The train is purged of observations overlapping test-label intervals.
    Test set is contiguous (standard KFold), but Training set is purged.
    """
    
    def __init__(self, n_splits=3, t1=None, pct_embargo=0.0):
        """
        Args:
            n_splits (int): The number of splits.
            t1 (pd.Series): Index: Time when the observation started. 
                            Value: Time when the observation ended (e.g. vertical barrier).
            pct_embargo (float): Percent of total bar duration to embargo after Test split.
        """
        if t1 is None:
            raise ValueError("t1 (event end times) must be provided.")
        super(PurgedKFold, self).__init__(n_splits=n_splits, shuffle=False, random_state=None)
        self.t1 = t1
        self.pct_embargo = pct_embargo
        
    def split(self, X, y=None, groups=None):
        """
        The main split generator.
        X (pd.DataFrame): The index is what matters (t0).
        """
        if isinstance(X, pd.DataFrame) or isinstance(X, pd.Series):
            indices = np.arange(X.shape[0])
            # Ensure t1 aligns
            # Note: X index must match t1 index.
            # We assume X is sorted by time.
        else:
            # If numpy array, assume user provided a range
            indices = np.arange(len(X))
            
        # Get standard KFold indices
        # indices are integers [0, 1, 2, ... N]
        for train_indices, test_indices in super(PurgedKFold, self).split(X):
            
            # 1. Identify Test Times
            # We assume X has a DatetimeIndex
            if hasattr(X, 'index'):
                t0 = X.index
            else:
                 raise ValueError("X must have a DatetimeIndex for PurgedKFold")
                 
            # Time range of the test set
            test_start_idx = test_indices[0]
            test_end_idx = test_indices[-1]
            
            t_test_start = t0[test_start_idx]
            
            # For the end time of the test set, we look at the MAXIMUM label end time (t1) in the test set
            # because any training sample that starts *before* this max t1 would overlap with this test set.
            # Wait, purging logic:
            # Drop from Train set any sample 'i' where:
            #  (start_i < end_test) AND (end_i > start_test)
            # i.e. the interval [start_i, end_i] overlaps with [start_test, end_test]
            
            # Test Interval: [min(t0_test), max(t1_test)]
            t0_test = t0[test_indices]
            t1_test = self.t1.loc[t0_test]
            max_test_end = t1_test.max()
            min_test_start = t0_test.min()
            
            # 2. Iterate train indices and purge
            train_indices_kept = []
            
            for i in train_indices:
                t0_i = t0[i]
                t1_i = self.t1.loc[t0_i]
                
                # Check overlap
                # Overlap if: t0_i < max_test_end AND t1_i > min_test_start
                # NOTE: This assumes closed intervals.
                
                is_overlap = (t0_i <= max_test_end) and (t1_i >= min_test_start)
                
                if not is_overlap:
                    train_indices_kept.append(i)
                    
            # 3. Apply Embargo
            # Drop samples immediately after the test set to avoid correlation leakage.
            # If Test is before Train -> Embargo the start of Train.
            # If Test is after Train -> No problem? (Actually test is usually the future)
            # Standard KFold moves the test block.
            
            # If Train is *after* Test, we need to embargo the start of that train block.
            # Since we iterate i in train_indices, we can check.
            
            # Embargo duration
            embargo_dt = pd.Timedelta(seconds=0)
            if self.pct_embargo > 0:
                # Approximate generic duration
                total_duration = t0[-1] - t0[0]
                embargo_ms = int(total_duration.total_seconds() * self.pct_embargo * 1000)
                embargo_dt = pd.Timedelta(milliseconds=embargo_ms)
                
            # If i is in the "future" relative to test set, it must start after max_test_end + embargo
            final_train_indices = []
            for i in train_indices_kept:
                t0_i = t0[i]
                
                # If this sample is after the test set
                if t0_i > max_test_end:
                    # Apply embargo
                    if t0_i >= (max_test_end + embargo_dt):
                        final_train_indices.append(i)
                else:
                    # If this sample is before the test set, we already purged overlaps.
                    final_train_indices.append(i)
                    
            yield np.array(final_train_indices), test_indices

