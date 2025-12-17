import pandas as pd
import numpy as np
import logging
import argparse
import os
import sys

# Add project root to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.backtest.permutation_tester import PermutationTester
from src.backtest.monte_carlo import MonteCarloOptimizer
from src.backtest.synthetic_data import generate_synthetic_data

# Import Strategies
from src.strategies.donchian_breakout import DonchianBreakoutStrategy
from src.strategies.pairs_trade import PairsTradeStrategy
from src.strategies.volatility_arb import VolatilityArbitrageStrategy

logger = logging.getLogger(__name__)

class StrategyAnalyzer:
    def __init__(self):
        pass

    def run_analysis(self, strategy_name, backtest_func, data, **kwargs):
        print(f"\n{'='*40}")
        print(f"ANALYZING: {strategy_name}")
        print(f"{'='*40}")
        
        # 1. Permutation Test
        print("\n[1] Running Permutation Test (NeuroTrader Method)...")
        print("    - Shuffling price changes to create 'fake' history.")
        print("    - Comparing Strategy Performance on Real vs Fake Data.")
        
        tester = PermutationTester(data)
        p_value = tester.run_test(backtest_func, n_permutations=50, return_trades=False, **kwargs)
        
        print(f"\n    >>> Permutation P-Value: {p_value:.4f}")
        if p_value < 0.05:
            print("    >>> PASS: Strategy likely has real predictive power (Edge).")
        else:
            print("    >>> FAIL: Strategy results likely due to chance/overfitting.")

        # 2. Monte Carlo Simulation
        print("\n[2] Running Monte Carlo Simulation...")
        print("    - Simulating 1000 possible futures by resampling trades.")
        
        trades = self._get_trades(backtest_func, data, **kwargs)
        
        if len(trades) < 10:
            print("    >>> WARNING: Not enough trades (<10) for reliable Monte Carlo.")
            return

        mc = MonteCarloOptimizer(trades)
        simulations = mc.run_simulation(num_simulations=1000)
        stats = mc.analyze_results(simulations)
        
        print(f"    >>> Risk of Ruin (50% Drawdown): {stats['risk_of_ruin_50pct']:.2f}%")
        print(f"    >>> Median Final Equity: ${stats['median_final_equity']:.2f}")
        print(f"    >>> Worst Case Equity (95% Conf): ${stats['worst_case_equity']:.2f}")
        
        # mc.plot_cone(simulations)

    def _get_trades(self, backtest_func, data, **kwargs):
        try:
            return backtest_func(data, return_trades=True, **kwargs)
        except TypeError:
            print("Backtest function does not support 'return_trades'.")
            return []

def load_data(filepath):
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return None
    df = pd.read_csv(filepath, parse_dates=True, index_col=0)
    # Ensure lowercase columns
    df.columns = [c.lower() for c in df.columns]
    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Strategy Analysis (Permutation & Monte Carlo)")
    parser.add_argument("--strategy", type=str, choices=['donchian', 'pairs', 'vol_arb'], required=True, help="Strategy to test")
    parser.add_argument("--data", type=str, help="Path to CSV data file")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic data")
    
    args = parser.parse_args()
    
    analyzer = StrategyAnalyzer()
    
    # Data Loading
    df = None
    if args.synthetic:
        print("Generating synthetic data...")
        df = generate_synthetic_data(length=2000, volatility=0.015)
        # Add fake IV for vol arb test
        df['iv'] = 0.20 + np.random.normal(0, 0.05, len(df))
    elif args.data:
        df = load_data(args.data)
    else:
        print("Please provide --data <path> or use --synthetic")
        exit()
        
    if df is None:
        exit()

    # Strategy Selection
    if args.strategy == 'donchian':
        analyzer.run_analysis("Donchian Breakout", DonchianBreakoutStrategy.backtest, df, lookback=20)
        
    elif args.strategy == 'pairs':
        # For pairs, we assume the input data IS the spread or has 'close' as the spread
        analyzer.run_analysis("Pairs Mean Reversion", PairsTradeStrategy.backtest, df, lookback=20)
        
    elif args.strategy == 'vol_arb':
        analyzer.run_analysis("Volatility Arbitrage", VolatilityArbitrageStrategy.backtest, df, entry_threshold=1.25)
