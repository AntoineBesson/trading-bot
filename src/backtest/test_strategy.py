import pandas as pd
from src.backtest.permutation_tester import PermutationTester
from src.strategies.donchian_breakout import DonchianBreakoutStrategy

# 1. Load Data (e.g., SPY)
df = pd.read_csv('data/SPY_1H.csv', parse_dates=True, index_col=0)

# 2. Initialize Tester
tester = PermutationTester(df)

# 3. Run the Permutation Test
# We want to see if a lookback of 20 is actually good
p_value = tester.run_test(DonchianBreakoutStrategy, lookback_param=20, n_permutations=100)

print(f"Final P-Value: {p_value}")

if p_value < 0.05:
    print("PASS: The strategy found real patterns!")
else:
    print("FAIL: The strategy is likely overfit or lucky.")