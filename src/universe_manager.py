import logging
import itertools
import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor

logger = logging.getLogger(__name__)

def evaluate_pair(args):
    """
    Worker function to evaluate a single pair.
    Must be at module level for multiprocessing on Windows.
    """
    sym_a, sym_b, series_a, series_b, p_threshold, z_threshold, min_crossings = args
    
    try:
        # OLS: Y = beta * X + alpha
        # series_a = hedge_ratio * series_b + intercept
        X = sm.add_constant(series_b)
        model = sm.OLS(series_a, X).fit()
        hedge_ratio = model.params.iloc[1]
        intercept = model.params.iloc[0]
        
        # Spread
        spread = series_a - (hedge_ratio * series_b + intercept)
        
        # ADF Test on spread
        # autolag='AIC' is default but explicit is good. 
        # maxlag=1 is faster but less accurate. Let's stick to default or None.
        adf_result = adfuller(spread)
        p_value = adf_result[1]
        
        # Z-Score
        spread_mean = spread.mean()
        spread_std = spread.std()
        current_spread = spread.iloc[-1]
        
        if spread_std == 0:
            z_score = 0
        else:
            z_score = (current_spread - spread_mean) / spread_std
            
        # Zero Crossings Count
        # Count how many times the spread crossed the mean
        centered_spread = spread - spread_mean
        zero_crossings = ((centered_spread * centered_spread.shift(1)) < 0).sum()

        # Check thresholds
        # 1. P-Value (Cointegration strength)
        # 2. Z-Score (Current deviation)
        # 3. Zero Crossings (Mean reversion frequency)
        if p_value < p_threshold and abs(z_score) < z_threshold and zero_crossings >= min_crossings:
            return {
                'symbol_a': sym_a,
                'symbol_b': sym_b,
                'hedge_ratio': hedge_ratio,
                'p_value': p_value,
                'current_z_score': z_score,
                'zero_crossings': zero_crossings,
                'timestamp': datetime.now()
            }
            
    except Exception:
        return None
        
    return None

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
        p_value_threshold: float = 0.01, # Stricter default (was 0.05)
        z_score_threshold: float = 1.5, 
        min_history_days: int = 100,
        correlation_threshold: float = 0.9,
        min_zero_crossings: int = 15, # Minimum mean reversions
        max_pairs: int = 30 # Limit result size
    ):
        self.dh = data_handler
        self.universe = universe
        self.lookback_days = lookback_days
        self.p_value_threshold = p_value_threshold
        self.z_score_threshold = z_score_threshold
        self.min_history_days = min_history_days
        self.correlation_threshold = correlation_threshold
        self.min_zero_crossings = min_zero_crossings
        self.max_pairs = max_pairs
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
        
        # --- Vectorized Step 1: Correlation Filter ---
        logger.info("Calculating correlation matrix...")
        returns_df = prices_df.pct_change().dropna()
        corr_matrix = returns_df.corr()
        
        # Filter for high correlation
        # Keep only upper triangle to avoid duplicates and self-correlation
        mask = np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
        candidates = corr_matrix.where(mask).stack()
        
        high_corr_pairs = candidates[candidates > self.correlation_threshold]
        pairs_to_test = high_corr_pairs.index.tolist() # List of (sym_a, sym_b) tuples
        
        logger.info(f"Correlation filter reduced pairs from {len(valid_symbols)*(len(valid_symbols)-1)//2} to {len(pairs_to_test)}.")

        # --- Step 2: Cointegration Test (Multiprocessing on reduced set) ---
        logger.info(f"Testing {len(pairs_to_test)} pairs using multiprocessing...")
        
        tasks = []
        for sym_a, sym_b in pairs_to_test:
            tasks.append((
                sym_a, 
                sym_b, 
                prices_df[sym_a], 
                prices_df[sym_b], 
                self.p_value_threshold, 
                self.z_score_threshold,
                self.min_zero_crossings
            ))
            
        new_watchlist = []
        
        # Use ProcessPoolExecutor to parallelize the work
        # max_workers=None defaults to the number of processors on the machine
        with ProcessPoolExecutor() as executor:
            # chunksize can be tuned. For 126k pairs, 100-500 is reasonable.
            results = executor.map(evaluate_pair, tasks, chunksize=500)
            
            for res in results:
                if res:
                    logger.info(f"Found Pair: {res['symbol_a']}/{res['symbol_b']} (p={res['p_value']:.4f}, z={res['current_z_score']:.2f}, x={res['zero_crossings']})")
                    new_watchlist.append(res)

        # Sort and Limit
        # Sort by P-Value (ascending) - strongest cointegration first
        new_watchlist.sort(key=lambda x: x['p_value'])
        
        # Take top N
        if len(new_watchlist) > self.max_pairs:
            logger.info(f"Limiting watchlist to top {self.max_pairs} pairs (from {len(new_watchlist)} found).")
            new_watchlist = new_watchlist[:self.max_pairs]

        self.watchlist = new_watchlist
        self.last_scan_time = datetime.now()
        logger.info(f"Scan complete. Found {len(self.watchlist)} valid pairs.")
        return self.watchlist

        self.watchlist = new_watchlist
        self.last_scan_time = datetime.now()
        logger.info(f"Scan complete. Found {len(self.watchlist)} valid pairs.")
        return self.watchlist

    def get_watchlist(self) -> List[Dict]:
        return self.watchlist
