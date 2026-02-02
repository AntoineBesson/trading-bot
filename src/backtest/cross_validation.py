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
            
            # 2. Vectorized Purge
            
            # Get start/end times for the training candidate set
            t0_train = t0[train_indices]
            
            # We need the end times (t1) for these training samples.
            # Assuming self.t1 contains all indices in X.
            try:
                t1_train = self.t1.loc[t0_train]
            except KeyError:
                raise KeyError("t1 (event end times) missing for some training indices.")

            # Check overlap vectorially
            # Overlap condition:
            # (Start_Train <= End_Test) AND (End_Train >= Start_Test)
            # We want to KEEP samples that do NOT overlap.
            
            # Note: Using .values to ensure we work with numpy arrays for speed and avoid index alignment issues 
            # if t1_train has different index name or properties slightly.
            
            train_start_values = t0_train.values
            train_end_values = t1_train.values
            
            # Overlap mask
            is_overlap = (train_start_values <= max_test_end) & (train_end_values >= min_test_start)
            
            # Keep non-overlapping
            train_indices_kept = train_indices[~is_overlap]
                    
            # 3. Apply Embargo
            if self.pct_embargo > 0:
                embargo_dt = pd.Timedelta(seconds=0)
                # Approximate generic duration
                total_duration = t0[-1] - t0[0]
                embargo_ms = int(total_duration.total_seconds() * self.pct_embargo * 1000)
                embargo_dt = pd.Timedelta(milliseconds=embargo_ms)
                
                if embargo_dt > pd.Timedelta(0):
                    # Elements to check for embargo
                    # We need to re-fetch timestamps for kept indices
                    t0_kept = t0[train_indices_kept]
                    t0_kept_values = t0_kept.values
                    
                    # Logic:
                    # If sample is AFTER test set (Start > max_test_end), it must also be >= max_test_end + embargo
                    # If sample is BEFORE test set, we keep it (already purged overlaps).
                    
                    # Correct Logic:
                    # Keep if (NOT After_Test) OR (After_Test AND >= Embargo_Limit)
                    # Equivalent: (~After_Test) | (>= Embargo_Limit)
                    
                    after_test_mask = t0_kept_values > max_test_end
                    embargo_limit = max_test_end + embargo_dt
                    pass_embargo_mask = t0_kept_values >= embargo_limit
                    
                    final_mask = (~after_test_mask) | pass_embargo_mask
                    
                    final_train_indices = train_indices_kept[final_mask]
                else:
                    final_train_indices = train_indices_kept
            else:
                final_train_indices = train_indices_kept
            
            yield final_train_indices, test_indices

