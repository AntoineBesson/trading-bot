import logging
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from hmmlearn.hmm import GaussianHMM
import joblib
from pathlib import Path

logger = logging.getLogger(__name__)

class RegimeDetector:
    def __init__(self, data_handler, symbol='SPY', lookback_years=5, model_path='data/hmm_model.pkl'):
        self.dh = data_handler
        self.symbol = symbol
        self.lookback_years = lookback_years
        
        # Handle relative path to ensure it points to src/data
        if not os.path.isabs(model_path):
             model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), model_path)
             
        self.model_path = Path(model_path)
        self.model = None
        
        # Ensure data directory exists
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.load_or_train_model()

    def load_or_train_model(self):
        """
        Loads the model if it exists and is fresh (< 7 days old).
        Otherwise, retrains it.
        """
        if self.model_path.exists():
            mod_time = datetime.fromtimestamp(self.model_path.stat().st_mtime)
            age = datetime.now() - mod_time
            if age.days < 7:
                logger.info(f"RegimeDetector: Loading existing model (Age: {age.days} days)")
                try:
                    self.model = joblib.load(self.model_path)
                    return
                except Exception as e:
                    logger.error(f"RegimeDetector: Failed to load model: {e}. Retraining.")
            else:
                logger.info(f"RegimeDetector: Model is stale (Age: {age.days} days). Retraining.")
        else:
            logger.info("RegimeDetector: No model found. Training new model.")
            
        self.train_model()

    def fetch_data(self, days=None):
        """
        Fetches data for SPY.
        If days is None, fetches lookback_years.
        """
        end_date = datetime.now()
        if days:
            start_date = end_date - timedelta(days=days)
        else:
            start_date = end_date - timedelta(days=self.lookback_years * 365)
            
        # Format dates as YYYY-MM-DD
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        data_dict = self.dh.get_historical_bars([self.symbol], '1D', start_str, end_str)
        if not data_dict or self.symbol not in data_dict:
            logger.error(f"RegimeDetector: Could not fetch data for {self.symbol}")
            return pd.DataFrame()
            
        return data_dict[self.symbol]

    def prepare_features(self, df):
        """
        Constructs features: Log Returns, Normalized Range, Volume Change.
        Standardizes them using rolling window.
        """
        if df.empty:
            return pd.DataFrame()
            
        df = df.copy()
        
        # 1. Log Returns
        df['log_ret'] = np.log(df['close'] / df['close'].shift(1))
        
        # 2. Realized Volatility Proxy (Normalized Range)
        df['range'] = (df['high'] - df['low']) / df['open']
        
        # 3. Volume Change
        # Handle zero volume if any
        df['volume'] = df['volume'].replace(0, np.nan).ffill()
        df['log_vol_chg'] = np.log(df['volume'] / df['volume'].shift(1))
        
        # Drop NaNs created by shifts
        df.dropna(inplace=True)
        
        # Standardization (Rolling Z-Score)
        window = 252
        features = ['log_ret', 'range', 'log_vol_chg']
        
        for col in features:
            roll_mean = df[col].rolling(window=window).mean()
            roll_std = df[col].rolling(window=window).std()
            df[f'{col}_z'] = (df[col] - roll_mean) / roll_std
            
        # Drop NaNs from rolling window
        df.dropna(inplace=True)
        
        return df[[f'{c}_z' for c in features]]

    def train_model(self):
        """
        Trains the HMM model and saves it.
        """
        logger.info("RegimeDetector: Fetching training data...")
        raw_data = self.fetch_data()
        if raw_data.empty:
            logger.error("RegimeDetector: No data for training.")
            return

        X = self.prepare_features(raw_data)
        if X.empty:
            logger.error("RegimeDetector: Not enough data to calculate features (need > 252 days).")
            return

        logger.info(f"RegimeDetector: Training HMM on {len(X)} data points...")
        
        # Train HMM
        # n_iter=100 is default, but explicit is good.
        model = GaussianHMM(n_components=2, covariance_type="full", n_iter=100, random_state=42)
        model.fit(X)
        
        # Enforce State 0 = Low Variance (Calm)
        hidden_states = model.predict(X)
        X_vals = X.values
        
        state_0_mask = hidden_states == 0
        state_1_mask = hidden_states == 1
        
        if not np.any(state_0_mask) or not np.any(state_1_mask):
             logger.warning("RegimeDetector: Model collapsed to single state. Retraining might be needed.")
        else:
            # Feature 1 is 'range_z' (Normalized Range)
            var_0 = np.var(X_vals[state_0_mask, 1])
            var_1 = np.var(X_vals[state_1_mask, 1])
            
            logger.info(f"RegimeDetector: State 0 Var: {var_0:.4f}, State 1 Var: {var_1:.4f}")
            
            if var_0 > var_1:
                logger.info("RegimeDetector: State 0 is Volatile. Flipping states...")
                
                # Permute parameters to swap states 0 and 1
                model.startprob_ = model.startprob_[[1, 0]]
                model.transmat_ = model.transmat_[[1, 0]][:, [1, 0]]
                model.means_ = model.means_[[1, 0]]
                model.covars_ = model.covars_[[1, 0]]
                
                logger.info("RegimeDetector: States flipped.")

        self.model = model
        joblib.dump(self.model, self.model_path)
        logger.info(f"RegimeDetector: Model saved to {self.model_path}")

    def get_current_regime(self):
        """
        Returns the current regime: 0 (Calm) or 1 (Volatile).
        """
        if self.model is None:
            logger.warning("RegimeDetector: Model not initialized. Returning 0 (Calm) as default.")
            return 0
            
        # Fetch recent data (need enough for rolling window + some buffer)
        # We need at least 252 days for the rolling window to produce a value for the last day.
        # Fetching 400 days to be safe.
        raw_data = self.fetch_data(days=400) 
        if raw_data.empty:
            return 0
            
        X = self.prepare_features(raw_data)
        if X.empty:
            logger.warning("RegimeDetector: Not enough recent data for features. Returning 0.")
            return 0
            
        # Predict
        hidden_states = self.model.predict(X)
        current_state = hidden_states[-1]
        
        logger.info(f"RegimeDetector: Current Regime = {current_state} ({'Volatile' if current_state == 1 else 'Calm'})")
        return current_state
