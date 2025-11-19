# trading-bot

This repo hosts two market-neutral systems built on Alpaca data/execution:

1. **Equity Pairs Trade** – find cointegrated stocks (see `notebooks/0_find_pairs.ipynb`), backtest them with `PairsTradeStrategy`, then execute with `ExecutionHandler`.
2. **Option Vega-Neutral Spread** – size two option legs by vega exposure so the combined book is resilient to implied-volatility shocks (`OptionPairsStrategy`).

## Components at a Glance

```
src/
├── data_handler.py        # Alpaca data client (stocks)
├── execution.py           # Alpaca trading client (stocks / fallback legging)
├── options/
│   ├── greeks.py          # Black-Scholes pricing + strike-by-delta solver
│   ├── data_handler.py    # Option snapshots, IV estimation, chain filtering
│   └── multileg.py        # Debit/credit payload builder for multi-leg orders
└── strategies/
	├── pairs_trade.py     # Rolling z-score equity spread engine
	└── option_pairs.py    # Vega-neutral option spread strategy
```

## Equity Pairs Quickstart

1. Load data + find candidates via `notebooks/0_find_pairs.ipynb` (exports `data/cointegrated_pairs.csv`).
2. Backtest and compare against SPY with `notebooks/01_run_backtests.ipynb` or call `PairsTradeStrategy.run_backtest` directly.
3. In live mode, instantiate `PairsTradeStrategy(data_handler, execution_handler, symbol_a, symbol_b, hedge_ratio)` and call `generate_signal()` inside your loop.

## Option Vega-Neutral Pairs Strategy

The option stack lives in `src/options/` and plugs into `OptionPairsStrategy`:

- `GreeksCalculator` exposes Black-Scholes pricing, greeks, and strike-by-delta search. It can optionally lean on `py_vollib_vectorized` for vectorized notebooks.
- `OptionDataHandler` estimates implied volatility from your underlying history, solves for the target-delta strike, and surfaces a complete option snapshot (price, delta, vega, theta, gamma).
- `MultiLegExecutionHelper` prepares multi-leg debit/credit payloads. If the broker lacks complex-order APIs it gracefully falls back to sequential leg execution using `ExecutionHandler`.
- `OptionPairsStrategy` mirrors the equity approach but sizes the hedge leg by vega, marks to model in backtests, and emits option-specific leg dictionaries you can send to the helper.

To walk through the workflow end-to-end, open `notebooks/02_option_pair_trading.ipynb`:

1. Load your preferred pair and estimate IV via `OptionDataHandler`.
2. Configure target delta / days-to-expiry / thresholds.
3. Backtest with `OptionPairsStrategy.run_backtest`, then flip to live by wiring `multi_leg_execution.execute(strategy.generate_signal())` inside your loop.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

`pytest` now includes `tests/test_option_strategy.py`, which exercises the greeks utility, option data handler, multi-leg helper, and the option strategy signal flow.

