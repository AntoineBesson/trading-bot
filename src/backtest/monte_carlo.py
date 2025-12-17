import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

class MonteCarloOptimizer:
    def __init__(self, trades_list, initial_capital=100000):
        """
        :param trades_list: A list of percentage returns (e.g., [0.02, -0.01, 0.05])
        """
        self.trades = np.array(trades_list)
        self.capital = initial_capital
        
    def run_simulation(self, num_simulations=1000, num_trades=None):
        """
        Runs the Monte Carlo simulation.
        :param num_trades: How many trades to simulate into the future (default: length of history)
        """
        if num_trades is None:
            num_trades = len(self.trades)
            
        results = []
        
        # 1. Run N Simulations
        for _ in range(num_simulations):
            # Sampling WITH replacement allows us to simulate "streaks" of bad luck
            # that might not have happened in history but COULD happen.
            random_returns = np.random.choice(self.trades, size=num_trades, replace=True)
            
            # Calculate Equity Curve
            equity_curve = [self.capital]
            current_cap = self.capital
            
            for ret in random_returns:
                current_cap *= (1 + ret)
                equity_curve.append(current_cap)
            
            results.append(equity_curve)
            
        return np.array(results)

    def analyze_results(self, simulations):
        """
        Calculates key metrics from the simulations.
        """
        final_values = simulations[:, -1]
        
        # 1. Risk of Ruin (Probability of losing > 50% capital)
        ruin_count = np.sum(final_values < (self.capital * 0.5))
        risk_of_ruin = (ruin_count / len(final_values)) * 100
        
        # 2. Median & Worst Case Return
        median_return = np.median(final_values)
        worst_case = np.percentile(final_values, 5) # 5th percentile (95% confidence)
        
        return {
            "risk_of_ruin_50pct": risk_of_ruin,
            "median_final_equity": median_return,
            "worst_case_equity": worst_case
        }

    def plot_cone(self, simulations):
        """Visualizes the Cone of Uncertainty."""
        plt.figure(figsize=(10, 6))
        
        # Plot first 100 paths as thin gray lines
        for i in range(min(100, len(simulations))):
            plt.plot(simulations[i], color='gray', alpha=0.1)
            
        # Plot Median (Red) and Worst Case (Blue)
        median_curve = np.median(simulations, axis=0)
        worst_curve = np.percentile(simulations, 5, axis=0)
        
        plt.plot(median_curve, color='red', label='Median Expectation')
        plt.plot(worst_curve, color='blue', label='Worst Case (95% Conf)')
        
        plt.title("Monte Carlo Simulation: Future Equity Cone")
        plt.xlabel("Number of Trades")
        plt.ylabel("Equity ($)")
        plt.legend()
        plt.show()