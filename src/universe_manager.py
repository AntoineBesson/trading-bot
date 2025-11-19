import logging
import itertools
import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class UniverseManager:
    """
    Manages the universe of assets, scans for cointegrated pairs,
    and maintains a watchlist of tradable relationships.
    """
    def __init__(
        self,
        data_handler,
        universe: List[str],
        lookback_days: int = 180,
        p_value_threshold: float = 0.05,
        z_score_threshold: float = 1, # Threshold for "near 0" filter (e.g. < 1.5 means not currently in extreme breakout)
        min_history_days: int = 100
    ):
        self.dh = data_handler
        self.universe = universe
        self.lookback_days = lookback_days
        self.p_value_threshold = p_value_threshold
        self.z_score_threshold = z_score_threshold
        self.min_history_days = min_history_days
        self.watchlist: List[Dict] = []
        self.last_scan_time = None

    def scan(self) -> List[Dict]:
        """
        Scans the universe for cointegrated pairs.
        Returns a list of dictionaries containing pair details.
        """
        logger.info(f"Starting universe scan for {len(self.universe)} symbols...")
        
        # 1. Fetch Data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days)
        
        # Convert to string format expected by DataHandler
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        hist_data = self.dh.get_historical_bars(
            self.universe, 
            timeframe_str='1D', 
            start=start_str, 
            end=end_str
        )
        
        if not hist_data:
            logger.warning("No data returned for universe scan.")
            return []

        # 2. Prepare DataFrame
        prices_df = pd.DataFrame()
        for symbol, df in hist_data.items():
            if df is not None and not df.empty:
                # Ensure we have enough data points
                if len(df) >= self.min_history_days:
                    # Handle multi-index or single index
                    if isinstance(df.index, pd.MultiIndex):
                         # If it's a multi-index (symbol, timestamp), reset or xs
                         # But DataHandler usually returns dict of {symbol: df_with_datetime_index}
                         pass
                    
                    # Normalize column names (close vs c)
                    col = 'close' if 'close' in df.columns else 'c'
                    if col in df.columns:
                        prices_df[symbol] = df[col]
        
        # Drop rows with NaNs to ensure alignment
        prices_df.dropna(inplace=True)
        
        if prices_df.empty or prices_df.shape[1] < 2:
            logger.warning("Not enough aligned data to form pairs.")
            return []

        valid_symbols = prices_df.columns.tolist()
        pairs = list(itertools.combinations(valid_symbols, 2))
        logger.info(f"Testing {len(pairs)} pairs from {len(valid_symbols)} valid symbols.")

        new_watchlist = []

        # 3. Test Pairs
        for sym_a, sym_b in pairs:
            try:
                series_a = prices_df[sym_a]
                series_b = prices_df[sym_b]
                
                # Run Cointegration Test
                hedge_ratio, p_value, spread, z_score = self._test_cointegration(series_a, series_b)
                
                # Filter Logic
                # 1. Statistically significant cointegration
                if p_value < self.p_value_threshold:
                    # 2. Current spread is not already blown out (optional, but requested "near 0")
                    # We use a loose threshold (e.g. < 2.0) to ensure we don't enter late, 
                    # but user specifically asked for "near 0". Let's use the configured threshold.
                    if abs(z_score) < self.z_score_threshold:
                        logger.info(f"Found Pair: {sym_a}/{sym_b} (p={p_value:.4f}, z={z_score:.2f})")
                        new_watchlist.append({
                            'symbol_a': sym_a,
                            'symbol_b': sym_b,
                            'hedge_ratio': hedge_ratio,
                            'p_value': p_value,
                            'current_z_score': z_score,
                            'timestamp': datetime.now()
                        })
            except Exception as e:
                logger.debug(f"Error testing pair {sym_a}/{sym_b}: {e}")
                continue

        self.watchlist = new_watchlist
        self.last_scan_time = datetime.now()
        logger.info(f"Scan complete. Found {len(self.watchlist)} valid pairs.")
        return self.watchlist

    def _test_cointegration(self, series_a: pd.Series, series_b: pd.Series) -> Tuple[float, float, pd.Series, float]:
        """
        Performs Engle-Granger cointegration test.
        Returns: (hedge_ratio, p_value, spread_series, current_z_score)
        """
        # OLS: Y = beta * X + alpha
        # series_a = hedge_ratio * series_b + intercept
        X = sm.add_constant(series_b)
        model = sm.OLS(series_a, X).fit()
        hedge_ratio = model.params.iloc[1]
        intercept = model.params.iloc[0]
        
        # Spread
        spread = series_a - (hedge_ratio * series_b + intercept)
        
        # ADF Test on spread
        adf_result = adfuller(spread)
        p_value = adf_result[1]
        
        # Z-Score of the *current* spread value relative to the window
        spread_mean = spread.mean()
        spread_std = spread.std()
        current_spread = spread.iloc[-1]
        
        if spread_std == 0:
            z_score = 0
        else:
            z_score = (current_spread - spread_mean) / spread_std
            
        return hedge_ratio, p_value, spread, z_score

    def get_watchlist(self) -> List[Dict]:
        return self.watchlist
