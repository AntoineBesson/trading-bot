
import pytest
import pandas as pd
import numpy as np
from src.labeling.barriers import get_triple_barrier_events, apply_pt_sl_on_t1

def test_apply_pt_sl_profit_take():
    # Setup data where price goes UP
    close = pd.Series([100, 101, 105, 100], index=pd.date_range('2020-01-01', periods=4))
    
    # Entry at t0 (index 0)
    # pt = 0.04 (4% target) -> Target Price 104
    # sl = 0.04
    # Event: t1 = NaT (indefinite or long horizon)
    # trgt = 1.0 (multiplier base)
    
    req = pd.Series({
        't1': pd.NaT,
        'trgt': 0.04
    })
    req.name = close.index[0]
    
    pt_sl = [1, 1] # 1x target for pt, 1x target for sl
    
    first_touch = apply_pt_sl_on_t1(req, close, None, pt_sl)
    
    # Should touch at index 2 (Price 105)
    assert first_touch == close.index[2]

def test_apply_pt_sl_stop_loss():
    # Setup data where price goes DOWN
    close = pd.Series([100, 99, 95, 100], index=pd.date_range('2020-01-01', periods=4))
    
    req = pd.Series({
        't1': pd.NaT,
        'trgt': 0.04
    })
    req.name = close.index[0]
    pt_sl = [1, 1]
    
    first_touch = apply_pt_sl_on_t1(req, close, None, pt_sl)
    
    # Should touch at index 2 (Price 95, -5% return <= -4%)
    assert first_touch == close.index[2]

def test_apply_pt_sl_time_exit():
    # Price stays flat
    close = pd.Series([100, 100, 100, 100], index=pd.date_range('2020-01-01', periods=4))
    
    t1_time = close.index[3]
    req = pd.Series({
        't1': t1_time,
        'trgt': 0.04
    })
    req.name = close.index[0]
    pt_sl = [1, 1]
    
    first_touch = apply_pt_sl_on_t1(req, close, None, pt_sl)
    
    # Should be t1
    assert first_touch == t1_time

def test_apply_pt_sl_no_touch_no_time():
    # Price flat, no t1
    close = pd.Series([100, 100, 100], index=pd.date_range('2020-01-01', periods=3))
    
    req = pd.Series({
        't1': pd.NaT,
        'trgt': 0.04
    })
    req.name = close.index[0]
    pt_sl = [1, 1]
    
    first_touch = apply_pt_sl_on_t1(req, close, None, pt_sl)
    
    assert pd.isna(first_touch)
