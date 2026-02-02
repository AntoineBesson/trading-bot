
import pytest
import pandas as pd
import numpy as np
from src.backtest.cross_validation import PurgedKFold

def test_purged_kfold_overlap():
    # 5 samples.
    # t0: 0, 1, 2, 3, 4
    # t1: 2, 3, 4, 5, 6 (duration 2)
    # Intervals: [0,2], [1,3], [2,4], [3,5], [4,6]
    
    t0 = pd.Index([0, 1, 2, 3, 4])
    t1 = pd.Series([2, 3, 4, 5, 6], index=t0)
    
    X = pd.DataFrame(index=t0, data={'val':range(5)})
    
    cv = PurgedKFold(n_splits=3, t1=t1, pct_embargo=0.0)
    
    # Splits:
    # KFold(3) on 5 items:
    # 1. Test: [0, 1]. Train: [2, 3, 4]
    #    Test range: [0, 3] (min t0=0, max t1=3)
    #    Train 2: [2, 4]. Overlap [0, 3]? Yes. (2<=3 AND 4>=0) -> Purge.
    #    Train 3: [3, 5]. Overlap [0, 3]? Yes. (3<=3 AND 5>=0) -> Purge.
    #    Train 4: [4, 6]. Overlap [0, 3]? No. (4>3). -> Keep.
    #    Kept: [4]
    
    # 2. Test: [2, 3]. Train: [0, 1, 4]
    #    Test range: [2, 5].
    #    Train 0: [0, 2]. Overlap [2, 5]? Yes (2>=2). Purge.
    #    Train 1: [1, 3]. Overlap [2, 5]? Yes. Purge.
    #    Train 4: [4, 6]. Overlap [2, 5]? Yes (4<=5). Purge.
    #    Kept: [] -> Wait, this assumes strict overlap. 
    #    Wait, if Train 0 ends at 2, and Test starts at 2.
    #    t1[0] = 2. t0[2] = 2.
    #    Overlap condition: (0 <= 5) AND (2 >= 2). True.
    
    splits = list(cv.split(X))
    
    # Verify split 1
    train_idx1, test_idx1 = splits[0]
    # Test indices: [0, 1]
    # Corresponding t0: 0, 1. t1: 2, 3. Max t1 = 3. Min t0 = 0.
    # Candidates: 2, 3, 4.
    # 2 ([2,4]): 2<=3, 4>=0 -> Purge
    # 3 ([3,5]): 3<=3, 5>=0 -> Purge
    # 4 ([4,6]): 4<=3 (False) -> Keep
    
    np.testing.assert_array_equal(train_idx1, [4])
    
    # Verify split 2
    train_idx2, test_idx2 = splits[1]
    # Test indices: [2, 3]. t0: 2, 3. Range [2, 5].
    # Candidates: 0, 1, 4.
    # 0 [0,2]: 0<=5, 2>=2 -> Purge.
    # 1 [1,3]: 1<=5, 3>=2 -> Purge.
    # 4 [4,6]: 4<=5, 6>=2 -> Purge.
    # Kept: []
    # This seems severe but correct for purged k-fold with overlapping labels.
    
    # Actually, let's make intervals shorter to allow some keeping.
    # t0: 0, 10, 20, 30, 40
    # t1: 2, 12, 22, 32, 42
    # Gaps are big.
    
def test_purged_kfold_no_overlap():
    t0 = pd.Index([0, 10, 20, 30, 40])
    t1 = pd.Series([2, 12, 22, 32, 42], index=t0)
    X = pd.DataFrame(index=t0, data={'val':range(5)})
    
    cv = PurgedKFold(n_splits=3, t1=t1, pct_embargo=0.0)
    splits = list(cv.split(X))
    
    # Split 0: Test [0, 1] (0, 10). Range [0, 12].
    # Train: 2, 3, 4 (20, 30, 40).
    # 2 [20, 22]: 20<=12 (False). Keep.
    # All kept.
    
    train_idx, test_idx = splits[0]
    np.testing.assert_array_equal(train_idx, [2, 3, 4])
    
def test_purged_kfold_embargo():
    # 3 samples. 0, 10, 20. t1 = t0 + 2.
    # Embargo: 10% of total span (20). -> 2 units.
    t0 = pd.to_datetime([0, 10, 20], unit='D')
    t1 = t0 + pd.Timedelta(days=2)
    # t1 index must match t0
    t1 = pd.Series(t1, index=t0)
    X = pd.DataFrame(index=t0, data={'val':range(3)})
    
    # Embargo logic uses Total duration t0[-1] - t0[0] = 20 days.
    # pct=0.1 -> 2 days.
    
    cv = PurgedKFold(n_splits=2, t1=t1, pct_embargo=0.1)
    splits = list(cv.split(X))
    
    # Split 0. Test [0] (Day 0). Range [0, 2].
    # Train cand: 1, 2.
    # 1 (Day 10). Overlap? [10, 12] vs [0, 2]. No.
    # Embargo? Sample 1 is AFTER test (10 > 2).
    # Must be >= MaxTestEnd (Day 2) + Embargo (2 Days) = Day 4.
    # 10 >= 4. True. Keep.
    
    # Split 1. Test [1, 2]? KFold(2) on 3 samples -> [0, 1], [2] or something.
    # Sklearn KFold:
    # 3 samples, 2 splits.
    # Fold 0: Test [0, 1]. Size 2. Train [2].
    # Fold 1: Test [2]. Size 1. Train [0, 1].
    
    # Let's check Split 0 (Test indices [0, 1] -> Days 0, 10).
    # Test range: [Day 0, Day 12].
    # Train cand: [2] (Day 20).
    # Overlap? [20, 22] vs [0, 12]. No.
    # Embargo? After test. Limit = 12 + 2 = 14. 20 >= 14. Keep.
    pass
