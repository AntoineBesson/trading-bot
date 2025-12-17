import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class PermutationTester:
    def __init__(self, data_frame):
        """
        Implements the NeuroTrader Permutation Test.
        :param data_frame: Pandas DF with 'open', 'high', 'low', 'close'
        """
        # Keep a clean copy of normal prices for the "Real" backtest
        self.data_raw = data_frame.copy()
        
        # Create a log-copy for the permutation math (better statistical properties)
        self.data_log = data_frame.copy()
        for col in ['open', 'high', 'low', 'close']:
            # Ensure no zeros or negative numbers before log
            self.data_log[col] = np.log(self.data_log[col])

    def generate_permutation(self):
        """
        Creates a 'Fake' price history by shuffling the intra-bar movements 
        and the overnight gaps independently.
        """
        # Use the LOG data for shuffling
        df = self.data_log.copy()
        
        # 1. Deconstruct Price Movement
        df['gap'] = df['open'] - df['close'].shift(1)
        df['rel_high'] = df['high'] - df['open']
        df['rel_low'] = df['low'] - df['open']
        df['rel_close'] = df['close'] - df['open']
        
        valid_indices = df.index[1:]
        
        # 2. Shuffle (Permute)
        shuffled_gap_idx = np.random.permutation(valid_indices)
        shuffled_intra_idx = np.random.permutation(valid_indices)
        
        # 3. Reconstruct 'Fake' Prices
        new_opens = [df['open'].iloc[0]]
        new_closes = [df['close'].iloc[0]]
        new_highs = [df['high'].iloc[0]]
        new_lows = [df['low'].iloc[0]]
        
        current_close = df['close'].iloc[0]
        
        for i in range(len(valid_indices)):
            gap_val = df.loc[shuffled_gap_idx[i], 'gap']
            rel_h = df.loc[shuffled_intra_idx[i], 'rel_high']
            rel_l = df.loc[shuffled_intra_idx[i], 'rel_low']
            rel_c = df.loc[shuffled_intra_idx[i], 'rel_close']
            
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
        """
        print(f"Running Permutation Test ({n_permutations} runs)...")
        
        # 1. Run on Real Data (Use data_raw!)
        real_profit = backtest_func(self.data_raw, **kwargs)
        print(f"Real Data Profit Factor: {real_profit:.2f}")
        
        better_than_real_count = 0
        
        # 2. Run on Permuted (Fake) Data
        for i in range(n_permutations):
            fake_data = self.generate_permutation()
            fake_profit = backtest_func(fake_data, **kwargs)
            
            if fake_profit >= real_profit:
                better_than_real_count += 1
            
            if (i + 1) % 100 == 0:
                print(f"Completed {i + 1}/{n_permutations} runs...")

        # 3. Calculate P-Value
        p_value = better_than_real_count / n_permutations
        return p_value

    @staticmethod
    def donchian_backtest(df, lookback=20):
        """
        Simplified vector backtest.
        """
        # Ensure we are working with a copy to avoid SettingWithCopy warnings
        df = df.copy()
        
        upper = df['close'].rolling(lookback).max().shift(1)
        lower = df['close'].rolling(lookback).min().shift(1)
        
        signals = np.zeros(len(df))
        signals[df['close'] > upper] = 1
        signals[df['close'] < lower] = -1
        
        # Forward fill positions
        signals = pd.Series(signals).replace(0, np.nan).ffill().fillna(0).values
        
        # Returns
        market_returns = df['close'].pct_change().shift(-1).fillna(0)
        strategy_returns = signals * market_returns
        
        gains = strategy_returns[strategy_returns > 0].sum()
        losses = abs(strategy_returns[strategy_returns < 0].sum())
        
        if losses == 0: return 0 if gains == 0 else 999
        return gains / losses

# ==========================================
# RUNNER SCRIPT
# ==========================================
if __name__ == "__main__":
    # 1. Load Real Data
    # Replace this path with your actual CSV file path
    csv_path = "data/SPY_1H_ALPACA.csv" 
    
    try:
        print(f"Loading data from {csv_path}...")
        # Assuming CSV has columns: Date, Open, High, Low, Close
        df = pd.read_csv(csv_path, parse_dates=True, index_col=0)
        
        # Normalize column names to lowercase
        df.columns = [c.lower() for c in df.columns]
        
        # 2. Initialize Tester
        tester = PermutationTester(df)
        
        # 3. Run Test (1000 Permutations)
        p_val = tester.run_test(
            PermutationTester.donchian_backtest, 
            n_permutations=1000, 
            lookback=20
        )
        
        print("-" * 30)
        print(f"FINAL P-VALUE: {p_val:.4f}")
        print("-" * 30)
        
        if p_val < 0.05:
            print("✅ PASS: Strategy has a statistically significant edge.")
        else:
            print("❌ FAIL: Strategy results are likely due to luck.")
            
    except FileNotFoundError:
        print(f"Error: Could not find file '{csv_path}'. Please ensure your data file exists.")
    except Exception as e:
        print(f"An error occurred: {e}")