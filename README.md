# Algorithmic Trading Platform (Multi-Strategy & AI-Enhanced)

A professional-grade, multi-strategy trading system built on the Alpaca API. This platform combines statistical arbitrage, trend following, and volatility strategies with AI-driven regime detection and a modern web dashboard.

It features a **Dynamic Universe Scanner**, a **Hidden Markov Model (HMM)** for market regime classification, and a **Portfolio Manager** for capital allocation and risk control.

## Key Features

### 1. Multi-Strategy Engine
*   **Pairs Trading (Equity & Options):** Statistical arbitrage using cointegration and Vega-neutral option spreads.
*   **Sector Momentum:** Monthly rebalancing strategy rotating into top-performing SPDR sectors.
*   **Donchian Breakout:** Classic trend-following strategy for capturing large moves.
*   **Volatility Arbitrage:** Gamma scalping strategy exploiting implied vs. realized volatility mispricing.

### 2. AI-Powered Regime Detection
*   **Hidden Markov Models (HMM):** Analyzes SPY returns to classify the market into **Bull**, **Bear**, or **Sideways** regimes.
*   **Adaptive Risk:** Strategies automatically adjust their aggression or go flat based on the detected regime.

### 3. Advanced Backtesting Suite
*   **Monte Carlo Simulation:** Stress-tests strategies against thousands of randomized market paths to estimate drawdown probabilities.
*   **Permutation Tests:** Validates that strategy alpha is statistically significant and not just random noise.
*   **Synthetic Data Generation:** Creates realistic market data for robust testing.

### 4. Web Dashboard (React + Vite)
*   **Real-time Monitoring:** Visualize equity curves, active positions, and strategy performance.
*   **Interactive Charts:** Built with Recharts/Chart.js for deep dives into trade history.
*   **Modern UI:** Fast, responsive interface powered by Vite and Tailwind CSS.

### 5. Robust Architecture
*   **Portfolio Manager ("The CFO"):** Centralized capital allocation and global risk management.
*   **Dynamic Universe ("The Hunter"):** Scans 125,000+ pairs in seconds using vectorized NumPy operations.
*   **Dockerized:** Full container support for easy deployment.

---

## Project Structure

```
├── src/
│   ├── main.py                # Entry point. Orchestrates the bot.
│   ├── portfolio_manager.py   # Allocates capital across strategies.
│   ├── regime_detector.py     # HMM model for market state detection.
│   ├── strategies/            # Strategy implementations.
│   │   ├── donchian_breakout.py
│   │   ├── sector_momentum.py
│   │   ├── volatility_arb.py
│   │   └── pairs_trade.py
│   ├── backtest/              # Advanced testing tools.
│   │   ├── monte_carlo.py
│   │   └── permutation_tester.py
│   └── options/               # Option pricing and execution.
├── frontend/                  # React + Vite Web Dashboard.
├── notebooks/                 # Research and Analysis.
├── tests/                     # Unit and Integration tests.
├── Dockerfile                 # Container definition.
└── docker-compose.yml         # Multi-container orchestration.
```

## Getting Started

### 1. Prerequisites
*   Python 3.10+
*   Node.js 18+ (for Frontend)
*   Docker (Optional)
*   Alpaca Markets Account

### 2. Installation (Local)

**Backend:**
```powershell
git clone <repo-url>
cd trading-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Frontend:**
```powershell
cd frontend
npm install
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
ALPACA_API_KEY=PKxxxxxxxxxxxx
ALPACA_SECRET_KEY=skxxxxxxxxxxxxxxxxxxxx
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

### 4. Running the Platform

**Using Docker (Recommended):**
```powershell
docker-compose up --build
```

**Manual Run:**
*   **Backend:** `python src/main.py`
*   **Frontend:** `cd frontend && npm run dev`

## Strategy Details

### Universe Selection ("The Hunter")
The `UniverseManager` performs a two-step scan:
1.  **Fast Filter:** Calculates Correlation Matrix (> 0.8).
2.  **Slow Filter:** Runs Engle-Granger Cointegration Test (P-Value < 0.05).

### Position Sizing (Vol Targeting)
Strategies use volatility targeting to normalize risk:
$$ \text{Size} = \frac{\text{Account Equity} \times \text{Risk \%}}{\text{Asset Volatility}} $$

## Notebooks
*   `notebooks/0_find_pairs.ipynb`: Cointegration research.
*   `notebooks/01_run_backtests.ipynb`: General strategy backtesting.
*   `notebooks/03_volatility_arb_backtest.ipynb`: Volatility arb analysis.
*   `notebooks/04_system_backtest.ipynb`: Full system simulation.

## Testing
```powershell
pytest
```
Includes unit tests for Greeks, strategies, and backtesting engines.

