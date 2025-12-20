import pandas as pd
import numpy as np
from src.strategies.macro_arbitrage import MacroArbitrageStrategy

def generate_dummy_data(n_points=1000, lag=15):
    """
    Generates correlated dummy data with a specific lag.
    """
    np.random.seed(42)
    
    # Leader returns: Random noise
    leader_returns = np.random.normal(0, 0.01, n_points)
    
    # Laggard returns: Leader returns shifted by 'lag' + some noise
    laggard_returns = np.zeros(n_points)
    laggard_returns[lag:] = leader_returns[:-lag]
    
    # Add some noise to laggard
    laggard_returns += np.random.normal(0, 0.005, n_points)
    
    return pd.Series(leader_returns), pd.Series(laggard_returns)

def main():
    print("Generating dummy data with a 15-minute lag...")
    leader, laggard = generate_dummy_data(lag=15)
    
    print("Running Cross-Correlation Analysis...")
    best_lag = MacroArbitrageStrategy.analyze_lead_lag_correlation(leader, laggard, max_lag=60)
    
    print(f"\nResult: The calculated best lag is {best_lag} minutes.")
    print(f"Expected: 15 minutes.")
    
    if best_lag == 15:
        print("SUCCESS: The analyzer correctly identified the lag.")
    else:
        print("FAILURE: The analyzer missed the lag.")

if __name__ == "__main__":
    main()
