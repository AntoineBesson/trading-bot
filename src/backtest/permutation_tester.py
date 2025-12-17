import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class PermutationTester:
    def __init__(self, data_frame):
        """
        Implements the NeuroTrader Permutation Test.
        :param data_frame: Pandas DF with 'open', 'high', 'low', 'close'
        """
        self.original_data = data_frame.copy()
        # Convert to log prices for better statistical properties
        for col in ['open', 'high', 'low', 'close']:
            self.original_data[col] = np.log(self.original_data[col])

    def generate_permutation(self):
        """
        Creates a 'Fake' price history by shuffling the intra-bar movements 
        and the overnight gaps independently.
        """
        df = self.original_data.copy()
        
        # 1. Deconstruct Price Movement
        # Gap = Today's Open - Yesterday's Close
        df['gap'] = df['open'] - df['close'].shift(1)
        
        # Intra-bar movements relative to Open
        df['rel_high'] = df['high'] - df['open']
        df['rel_low'] = df['low'] - df['open']
        df['rel_close'] = df['close'] - df['open']
        
        # Drop the first NaN from shift
        valid_indices = df.index[1:]
        
        # 2. Shuffle (Permute)
        # We shuffle the index pointers, not the data directly, to mix them up
        shuffled_gap_idx = np.random.permutation(valid_indices)
        shuffled_intra_idx = np.random.permutation(valid_indices)
        
        # 3. Reconstruct 'Fake' Prices
        new_opens = [df['open'].iloc[0]] # Start at same point
        new_closes = [df['close'].iloc[0]]
        new_highs = [df['high'].iloc[0]]
        new_lows = [df['low'].iloc[0]]
        
        current_close = df['close'].iloc[0]
        
        for i in range(len(valid_indices)):
            # Get random pieces from history
            gap_val = df.loc[shuffled_gap_idx[i], 'gap']
            rel_h = df.loc[shuffled_intra_idx[i], 'rel_high']
            rel_l = df.loc[shuffled_intra_idx[i], 'rel_low']
            rel_c = df.loc[shuffled_intra_idx[i], 'rel_close']
            
            # Rebuild bar
            new_open = current_close + gap_val
            new_high = new_open + rel_h
            new_low = new_open + rel_l
            new_close = new_open + rel_c
            
            new_opens.append(new_open)
            new_highs.append(new_high)
            new_lows.append(new_low)
            new_closes.append(new_close)
            
            current_close = new_close
            
        # 4. Convert back from Log to Normal prices
        permuted_df = pd.DataFrame({
            'open': np.exp(new_opens),
            'high': np.exp(new_highs),
            'low': np.exp(new_lows),
            'close': np.exp(new_closes)
        }, index=df.index)
        
        return permuted_df

    def run_test(self, backtest_func, n_permutations=100, **kwargs):
        """
        Runs the strategy on Real Data vs N Permutations.
        Returns a 'p-value' (Score). 
        Lower p-value (< 0.05) = Strategy is REAL.
        High p-value (> 0.05) = Strategy is FAKE/LUCK.
        
        :param backtest_func: Function(df, **kwargs) -> float (performance metric)
        """
        # 1. Run on Real Data
        real_profit = backtest_func(self.original_data, **kwargs)
        logger.info(f"Real Data Profit Factor: {real_profit:.2f}")
        
        better_than_real_count = 0
        
        # 2. Run on Permuted (Fake) Data
        for i in range(n_permutations):
            fake_data = self.generate_permutation()
            fake_profit = backtest_func(fake_data, **kwargs)
            
            if fake_profit >= real_profit:
                better_than_real_count += 1
            
            if i % 10 == 0:
                print(f"Permutation {i}/{n_permutations}: Fake Profit {fake_profit:.2f}")

        # 3. Calculate P-Value
        p_value = better_than_real_count / n_permutations
        return p_value

    @staticmethod
    def donchian_backtest(df, lookback=20):
        """
        Simplified vector backtest for speed (as shown in video).
        """
        # Signal: 1 if Close > Max(Last N), -1 if Close < Min(Last N)
        # Using simple pandas vectorization for speed
        upper = df['close'].rolling(lookback).max().shift(1)
        lower = df['close'].rolling(lookback).min().shift(1)
        
        signals = np.zeros(len(df))
        signals[df['close'] > upper] = 1
        signals[df['close'] < lower] = -1
        
        # Forward fill positions (hold until signal changes)
        # (This is a simplified version of Donchian logic)
        signals = pd.Series(signals).replace(0, np.nan).ffill().fillna(0).values
        
        # Returns
        # Strategy Return = Position(t) * Return(t+1)
        market_returns = df['close'].pct_change().shift(-1).fillna(0)
        strategy_returns = signals * market_returns
        
        # Calculate Profit Factor: Sum(Positive Returns) / Sum(Negative Returns)
        gains = strategy_returns[strategy_returns > 0].sum()
        losses = abs(strategy_returns[strategy_returns < 0].sum())
        
        if losses == 0: return 0 if gains == 0 else 999
        return gains / losses