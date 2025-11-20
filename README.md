# Algorithmic Trading Bot (Equity & Options)

A sophisticated, market-neutral trading system built on the Alpaca API. This bot specializes in **Pairs Trading** (Statistical Arbitrage) using both Equities and Options (Vega-Neutral Spreads).

It features a high-performance **Dynamic Universe Scanner** that continuously finds new cointegrated relationships across the S&P 500, and a "Capital Aware" execution engine that targets volatility-adjusted risk.

## Key Features

### 1. Dynamic Universe Scanning ("The Hunter")
*   **Vectorized Speed:** Uses Matrix Operations (NumPy/Pandas) to filter 125,000+ potential pairs in seconds.
*   **Multiprocessing:** Runs rigorous ADF Cointegration tests in parallel across all CPU cores.
*   **Smart Filters:**
    *   **Correlation:** > 0.8 (Finds related assets).
    *   **Cointegration:** P-Value < 0.05 (Statistically significant).
    *   **Mean Reversion:** Requires > 8 zero-crossings in 6 months (Ensures active trading).
    *   **Blacklist:** Automatically ignores dual-class shares (e.g., GOOG vs GOOGL).
    *   **Unique Selection:** Ensures no stock appears in more than one pair.

### 2. Advanced Option Strategy ("The Sniper")
*   **Vega-Neutrality:** Sizes option legs based on Implied Volatility (Vega) to isolate the spread movement and hedge against market-wide volatility shocks.
*   **Volatility Targeting:** Dynamically sizes positions to risk exactly **1% of account equity** per trade.
    *   High Volatility Pair -> Smaller Size.
    *   Low Volatility Pair -> Larger Size.
*   **Equity Guard:** Checks underlying stock prices first. If they haven't moved, it skips the expensive Option API calls to save rate limits and latency.

### 3. Robust Architecture
*   **Market Hours Aware:** Automatically sleeps when the US market is closed (9:30 AM - 4:00 PM ET).
*   **Resilient:** Handles API errors, network drops, and delisted symbols gracefully.
*   **Modular:** Separated concerns into Data, Execution, Strategy, and Universe Management.

---

## Project Structure

```
src/
├── main.py                # Entry point. Orchestrates the bot, scanning, and trading loop.
├── universe_manager.py    # The "Hunter". Scans S&P 500 for cointegrated pairs.
├── data_handler.py        # Alpaca Data API wrapper (Stocks).
├── execution.py           # Alpaca Trading API wrapper.
├── strategies/
│   ├── option_pairs.py    # The core Option Strategy (Vol Targeting, Greeks).
│   ├── pairs_trade.py     # Classic Equity Pairs Strategy.
│   └── base_strategy.py   # Abstract base class.
└── options/
    ├── greeks.py          # Black-Scholes & Greeks calculator.
    ├── data_handler.py    # Option Chain & Snapshot manager.
    └── multileg.py        # Multi-leg order execution helper.
```

## Getting Started

### 1. Prerequisites
*   Python 3.10+
*   Alpaca Markets Account (Paper or Live)

### 2. Installation
```powershell
# Clone the repo
git clone <repo-url>
cd trading-bot

# Create Virtual Environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Dependencies
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
ALPACA_API_KEY=PKxxxxxxxxxxxx
ALPACA_SECRET_KEY=skxxxxxxxxxxxxxxxxxxxx
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

### 4. Running the Bot
```powershell
python src/main.py
```
The bot will:
1.  Connect to Alpaca.
2.  Scan the `data/universe.csv` (or default S&P 500 list) for the best 30 pairs.
3.  Start the trading loop (checking every minute during market hours).

## Strategy Details

### Universe Selection
The `UniverseManager` performs a two-step scan:
1.  **Fast Filter:** Calculates the Correlation Matrix of returns for all 500 stocks. Keeps pairs with correlation > 0.8.
2.  **Slow Filter:** Runs the Engle-Granger Cointegration Test (ADF) on the survivors. Keeps pairs with P-Value < 0.05 and frequent mean reversion.

### Position Sizing (Vol Targeting)
The bot calculates position size using the formula:
$$ \text{Contracts} = \frac{\text{Account Equity} \times \text{Risk \%}}{\text{Spread Volatility} \times 100} $$
This ensures consistent risk exposure regardless of the asset's price or volatility.

## Notebooks
*   `notebooks/0_find_pairs.ipynb`: Research tool to visualize cointegration.
*   `notebooks/02_option_pair_trading.ipynb`: Backtesting engine for the Option Strategy.

## Testing
```powershell
pytest
```
Includes unit tests for Greeks calculation, strategy logic, and data handling.

