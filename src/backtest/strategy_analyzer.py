import pandas as pd
import numpy as np
import logging
from src.backtest.permutation_tester import PermutationTester
from src.backtest.monte_carlo import MonteCarloOptimizer
from src.backtest.synthetic_data import generate_synthetic_data

logger = logging.getLogger(__name__)

class StrategyAnalyzer:
    def __init__(self):
        pass

    def run_analysis(self, strategy_name, backtest_func, data, **kwargs):
        print(f"--- Analyzing {strategy_name} ---")
        
        # 1. Permutation Test
        print("\n[1] Running Permutation Test...")
        tester = PermutationTester(data)
        # We pass return_trades=False to ensure we get a score for the permutation test
        p_value = tester.run_test(backtest_func, n_permutations=50, return_trades=False, **kwargs)
        
        print(f"Permutation P-Value: {p_value:.4f}")
        if p_value < 0.05:
            print(">> PASS: Strategy likely has real edge.")
        else:
            print(">> FAIL: Strategy results likely due to chance.")

        # 2. Monte Carlo Simulation
        print("\n[2] Running Monte Carlo Simulation...")
        # Get trade returns for Monte Carlo
        trades = self._get_trades(backtest_func, data, **kwargs)
        
        if len(trades) < 10:
            print(">> WARNING: Not enough trades for Monte Carlo.")
            return

        mc = MonteCarloOptimizer(trades)
        simulations = mc.run_simulation(num_simulations=1000)
        stats = mc.analyze_results(simulations)
        
        print(f"Risk of Ruin (50% Drawdown): {stats['risk_of_ruin_50pct']:.2f}%")
        print(f"Median Final Equity: ${stats['median_final_equity']:.2f}")
        print(f"Worst Case Equity (95%): ${stats['worst_case_equity']:.2f}")
        
        # Optional: Plot
        # mc.plot_cone(simulations)

    def _get_trades(self, backtest_func, data, **kwargs):
        try:
            return backtest_func(data, return_trades=True, **kwargs)
        except TypeError:
            print("Backtest function does not support 'return_trades'. Using dummy returns.")
            return []

# --- Vector Backtest Implementations ---

def donchian_backtest(df, lookback=20, return_trades=False):
    """
    Vectorized Donchian Breakout.
    """
    upper = df['close'].rolling(lookback).max().shift(1)
    lower = df['close'].rolling(lookback).min().shift(1)
    
    signals = np.zeros(len(df))
    signals[df['close'] > upper] = 1
    signals[df['close'] < lower] = -1
    
    signals = pd.Series(signals).replace(0, np.nan).ffill().fillna(0).values
    market_returns = df['close'].pct_change().shift(-1).fillna(0)
    strategy_returns = signals * market_returns
    
    if return_trades:
        # Extract non-zero returns as "trades" (simplified)
        return strategy_returns[strategy_returns != 0].values
    
    gains = strategy_returns[strategy_returns > 0].sum()
    losses = abs(strategy_returns[strategy_returns < 0].sum())
    
    if losses == 0: return 0 if gains == 0 else 999
    return gains / losses

def pairs_mean_reversion_backtest(df, z_entry=2.0, z_exit=0.5, lookback=20, return_trades=False):
    """
    Vectorized Mean Reversion on the Spread.
    IMPORTANT: 'df' must contain the SPREAD history in the 'close' column.
    """
    # Calculate Z-Score of the spread
    spread = df['close']
    mean = spread.rolling(lookback).mean()
    std = spread.rolling(lookback).std()
    z_score = (spread - mean) / std
    
    signals = np.zeros(len(df))
    # Short the spread when Z > Entry (expect reversion down)
    signals[z_score > z_entry] = -1
    # Long the spread when Z < -Entry (expect reversion up)
    signals[z_score < -z_entry] = 1
    
    # Exit logic (Simplified for vectorization)
    # We treat '0' as 'Exit' signal here, but ffill handles holding.
    # To implement "Exit at z_exit", we need to explicitly set 0 when condition met.
    # Here we just hold until reverse signal or extreme reversion (simplified).
    # Better vectorization:
    long_exit = z_score > -z_exit
    short_exit = z_score < z_exit
    
    # This is complex to vectorize perfectly. 
    # For the purpose of Permutation Test (speed), we can use a simpler proxy:
    # Always be in position based on sign of Z-score? No, that's trend following.
    # Mean Reversion: Fade the move.
    
    # Simple Reversion:
    # If Z > 2, Short. Hold until Z < 0.
    # If Z < -2, Long. Hold until Z > 0.
    
    # Iterative approach (slower but correct)
    pos = 0
    final_signals = []
    for z in z_score:
        if pos == 0:
            if z > z_entry: pos = -1
            elif z < -z_entry: pos = 1
        elif pos == 1:
            if z > -z_exit: pos = 0
        elif pos == -1:
            if z < z_exit: pos = 0
        final_signals.append(pos)
        
    signals = np.array(final_signals)
    
    market_returns = df['close'].pct_change().shift(-1).fillna(0)
    strategy_returns = signals * market_returns
    
    if return_trades:
        return strategy_returns[strategy_returns != 0].values
        
    gains = strategy_returns[strategy_returns > 0].sum()
    losses = abs(strategy_returns[strategy_returns < 0].sum())
    
    if losses == 0: return 0 if gains == 0 else 999
    return gains / losses

if __name__ == "__main__":
    # Generate Data
    print("Generating synthetic data...")
    df = generate_synthetic_data(length=2000, volatility=0.015)
    
    analyzer = StrategyAnalyzer()
    
    # Test Donchian
    analyzer.run_analysis("Donchian Breakout", donchian_backtest, df, lookback=20)
    
    # Test Pairs (using same random data as 'spread' - likely to fail)
    analyzer.run_analysis("Pairs Mean Reversion (Random Data)", pairs_mean_reversion_backtest, df, lookback=20)
