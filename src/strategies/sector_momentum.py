from __future__ import annotations

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from strategies.base_strategy import BaseStrategy
from strategies_config import SECTOR_UNIVERSE, DEFENSIVE_ASSETS

logger = logging.getLogger(__name__)

class SectorMomentumStrategy(BaseStrategy):
    """
    Sector Momentum Strategy (Monthly Rebalance).
    
    Logic:
    1. Universe: 11 SPDR Sector ETFs + Safety (SHV/BIL).
    2. Schedule: Rebalance on the last trading day of the month.
    3. Momentum: Rank by 6-Month Return (126 days). Pick Top 3.
    4. Regime Filter: For each candidate, if Price < 200-Day SMA, swap for Safety.
    5. Execution: Equal weight (33.3% each).
    """
    
    def __init__(self, 
                 data_handler, 
                 execution_handler, 
                 portfolio_manager, 
                 strategy_id: str = "SectorMomentum",
                 universe: List[str] = SECTOR_UNIVERSE,
                 safety_asset: str = "SHV",
                 top_n: int = 3,
                 momentum_window: int = 126, # ~6 months
                 sma_window: int = 200,
                 initial_capital: float = 10000.0
                 ):
        # We pass the full universe + safety asset to the BaseStrategy
        all_symbols = universe + [safety_asset]
        super().__init__(data_handler, execution_handler, portfolio_manager, strategy_id, all_symbols)
        
        self.universe = universe
        self.safety_asset = safety_asset
        self.top_n = top_n
        self.momentum_window = momentum_window
        self.sma_window = sma_window
        self.initial_capital = initial_capital
        
        # State
        self.current_holdings = {} # {symbol: qty}
        self.last_rebalance_date = None

    def generate_signal(self):
        """
        Checks if it's time to rebalance, and if so, executes the logic.
        """
        today = datetime.now().date()
        
        if not self._is_rebalance_day(today):
            logger.info(f"[{self.strategy_id}] Not a rebalance day. Skipping.")
            return

        logger.info(f"[{self.strategy_id}] Rebalance Triggered for {today}")
        self._rebalance_portfolio()
        self.last_rebalance_date = today

    def _is_rebalance_day(self, date) -> bool:
        """
        Checks if today is the last trading day of the month.
        Simplified logic: Check if tomorrow is a new month.
        In a real system, we'd check the market calendar.
        """
        # Simple check: if tomorrow is day 1, today is last day.
        # Issue: Weekends.
        # Better: Check if we are in the last few days of the month and haven't rebalanced yet?
        # Or just run on the first trading day of the month?
        # User said: "last trading day of the month (or the first trading day of the new month)"
        
        # Let's try to detect the first trading day of the month.
        # If today.day <= 3 and we haven't rebalanced this month yet.
        # But the user prefers last trading day.
        
        # Let's use pandas BMonthEnd to check if today is a business month end.
        is_month_end = pd.Timestamp(date) == (pd.Timestamp(date) + pd.tseries.offsets.BMonthEnd(0))
        return is_month_end

    def _rebalance_portfolio(self):
        # 1. Fetch Data (250 days for SMA calculation)
        lookback = max(self.momentum_window, self.sma_window) + 20 # Buffer
        start_date = (datetime.now() - timedelta(days=lookback * 2)).strftime('%Y-%m-%d') # *2 for weekends
        
        logger.info(f"[{self.strategy_id}] Fetching data for universe...")
        bars_map = self.data_handler.get_historical_bars(self.universe, "1D", start_date)
        
        if not bars_map:
            logger.error(f"[{self.strategy_id}] Failed to fetch data.")
            return

        # 2. Calculate Momentum and SMA
        scores = []
        
        for symbol in self.universe:
            if symbol not in bars_map:
                continue
            
            df = bars_map[symbol]
            if len(df) < self.sma_window:
                logger.warning(f"[{self.strategy_id}] Not enough data for {symbol}. Skipping.")
                continue
                
            # Current Price
            current_price = float(df.iloc[-1]['close'])
            
            # Momentum (6-Month Return)
            # Price 126 days ago
            if len(df) > self.momentum_window:
                price_ago = float(df.iloc[-self.momentum_window]['close'])
                momentum_score = (current_price / price_ago) - 1
            else:
                momentum_score = -999.0 # Should not happen given check above
            
            # SMA 200
            sma_200 = df['close'].rolling(window=self.sma_window).mean().iloc[-1]
            
            scores.append({
                'symbol': symbol,
                'momentum': momentum_score,
                'price': current_price,
                'sma_200': sma_200,
                'trend_ok': current_price > sma_200
            })
            
        if not scores:
            return

        # 3. Rank and Select Top 3
        scores.sort(key=lambda x: x['momentum'], reverse=True)
        top_candidates = scores[:self.top_n]
        
        logger.info(f"[{self.strategy_id}] Top Candidates: {[c['symbol'] for c in top_candidates]}")
        
        # 4. Regime Filter
        final_basket = []
        for cand in top_candidates:
            if cand['trend_ok']:
                final_basket.append(cand['symbol'])
                logger.info(f"[{self.strategy_id}] {cand['symbol']} Trend OK (Price {cand['price']:.2f} > SMA {cand['sma_200']:.2f}). Selected.")
            else:
                final_basket.append(self.safety_asset)
                logger.info(f"[{self.strategy_id}] {cand['symbol']} Trend BROKEN (Price {cand['price']:.2f} < SMA {cand['sma_200']:.2f}). Swapped for {self.safety_asset}.")
                
        # 5. Execution
        self._execute_rebalance(final_basket)

    def _execute_rebalance(self, target_symbols: List[str]):
        logger.info(f"[{self.strategy_id}] Executing Rebalance. Target Basket: {target_symbols}")
        
        # Calculate Target Allocation
        # We assume equal weight for the strategy's allocated capital
        # Note: PortfolioManager manages the total capital for this strategy.
        # We need to know how much capital we have.
        
        # Get total equity allocated to this strategy
        # If PortfolioManager doesn't track cash per strategy, we might need to estimate 
        # based on current holdings value + available cash?
        # For now, let's ask PortfolioManager for the budget.
        
        # In the current PM implementation, 'allocations' is a limit.
        # We should try to use the full allocation or the current value of the strategy.
        # Let's assume we use the full 'allocation' amount defined in config.
        
        # But wait, if we lost money, we shouldn't trade based on original allocation.
        # We should trade based on Net Liquidation Value of this strategy.
        # Since we don't track that perfectly, let's approximate:
        # Strategy Equity = Current Value of Holdings + (Allocated - Cost Basis of Holdings)?
        # Or just use the 'allocation' as the target exposure.
        
        # Let's use the PortfolioManager's allocation as the target *Exposure*.
        # If we have $10k allocated, we want $3.3k in each of the 3 assets.
        
        if self.strategy_id in self.portfolio_manager.allocations:
            alloc_info = self.portfolio_manager.allocations[self.strategy_id]
            # Handle both float (old) and dict (new) for backward compatibility if needed, 
            # but we updated PM to use dict.
            if isinstance(alloc_info, dict):
                total_equity = alloc_info['equity'] * alloc_info.get('leverage', 1.0)
            else:
                total_equity = float(alloc_info)
        else:
            total_equity = self.initial_capital
            
        target_per_asset = total_equity / len(target_symbols)
        
        # Group targets by symbol (in case we have multiple Safety assets)
        target_allocation = {}
        for sym in target_symbols:
            target_allocation[sym] = target_allocation.get(sym, 0.0) + target_per_asset
            
        # Get Current Positions
        current_positions = self.execution_handler.get_all_positions()
        # Filter for our universe
        my_positions = {p.symbol: float(p.qty) for p in current_positions if p.symbol in self.symbols}
        
        # Calculate Current Exposure for PM Check
        current_exposure = 0.0
        for sym, qty in my_positions.items():
            # Get price
            bars = self.data_handler.get_latest_bars([sym], 1)
            if bars and sym in bars:
                price = float(bars[sym][0]['close'])
                current_exposure += qty * price
        
        # 1. Sell Logic
        # Sell anything not in target or sell excess
        for sym, qty in my_positions.items():
            if sym not in target_allocation:
                # Sell 100%
                logger.info(f"[{self.strategy_id}] Selling {sym} (Not in target).")
                self.execution_handler.close_position(sym)
                # Update exposure (approx)
                # We don't know exact fill price yet, but let's assume it reduces exposure
                # Actually, we should just pass the pre-trade exposure to check_trade 
                # and let it decide if we can ADD. Selling is always allowed.
            else:
                # Check if we need to trim?
                # For simplicity in this "monthly" rebalance, we can just calculate the delta.
                pass
                
        # 2. Buy/Adjust Logic
        # We iterate through targets and adjust position
        for sym, target_val in target_allocation.items():
            # Get current price
            # We can use the last close from data handler
            bars = self.data_handler.get_latest_bars([sym], 1)
            if not bars or sym not in bars:
                logger.warning(f"[{self.strategy_id}] No price for {sym}. Skipping.")
                continue
            price = float(bars[sym][0]['close'])
            
            current_qty = my_positions.get(sym, 0.0)
            current_val = current_qty * price
            
            diff_val = target_val - current_val
            
            # Threshold to avoid tiny trades (e.g. < $100)
            if abs(diff_val) < 100:
                continue
                
            qty_to_trade = int(diff_val / price)
            
            if qty_to_trade > 0:
                # Buy
                # Pass current_exposure to PM. 
                # Note: If we just sold something, our exposure is lower, but we haven't updated 'current_exposure' variable.
                # Ideally we update it.
                if self.portfolio_manager.check_trade(self.strategy_id, qty_to_trade * price, current_exposure=current_exposure):
                    logger.info(f"[{self.strategy_id}] Buying {qty_to_trade} {sym} (Target ${target_val:.2f})")
                    self.execution_handler.submit_order(sym, 'buy', qty_to_trade)
                    current_exposure += qty_to_trade * price # Update for next loop
            elif qty_to_trade < 0:
                # Sell
                logger.info(f"[{self.strategy_id}] Selling {abs(qty_to_trade)} {sym} (Target ${target_val:.2f})")
                self.execution_handler.submit_order(sym, 'sell', abs(qty_to_trade))
                current_exposure -= abs(qty_to_trade) * price

    def run_backtest(self, start_date, end_date, timeframe="1D"):
        """
        Backtest implementation for Sector Momentum.
        """
        logger.info(f"[{self.strategy_id}] Starting Backtest from {start_date} to {end_date}...")
        
        # Fetch all data at once
        bars_map = self.data_handler.get_historical_bars(self.universe + [self.safety_asset], timeframe, start_date, end_date)
        
        # Align data into a single DataFrame for easier processing
        # We need a DF with columns like (symbol, close)
        # Or a Panel. Let's use a Dict of Series for Closes.
        closes = {}
        for sym, df in bars_map.items():
            closes[sym] = df['close']
            
        price_df = pd.DataFrame(closes).dropna()
        
        # Simulation Loop
        # We iterate day by day to check for month end
        
        equity = self.initial_capital
        holdings = {} # {symbol: qty}
        equity_curve = []
        trades = []
        
        # Pre-calculate indicators to speed up?
        # Momentum: 126 day pct change
        momentum_df = price_df.pct_change(self.momentum_window)
        # SMA: 200 day mean
        sma_df = price_df.rolling(self.sma_window).mean()
        
        dates = price_df.index
        
        for i, date in enumerate(dates):
            if i < self.sma_window: # Warmup
                continue
                
            # Check Rebalance
            is_rebalance = self._is_rebalance_day(date)
            
            # Calculate Portfolio Value
            current_val = 0.0
            if not holdings:
                current_val = equity # Cash
            else:
                for sym, qty in holdings.items():
                    price = price_df.loc[date, sym]
                    current_val += qty * price
                equity = current_val
            
            equity_curve.append({'date': date, 'equity': equity})
            
            if is_rebalance:
                # Logic
                # 1. Rank
                # Get momentum for universe only
                current_mom = momentum_df.loc[date, self.universe]
                ranked = current_mom.sort_values(ascending=False)
                top_3 = ranked.head(self.top_n).index.tolist()
                
                # 2. Filter
                target_basket = []
                for sym in top_3:
                    price = price_df.loc[date, sym]
                    sma = sma_df.loc[date, sym]
                    if price > sma:
                        target_basket.append(sym)
                    else:
                        target_basket.append(self.safety_asset)
                
                # 3. Rebalance
                # Sell all current (Simplified for backtest)
                holdings = {}
                
                target_amt = equity / len(target_basket)
                for sym in target_basket:
                    price = price_df.loc[date, sym]
                    qty = target_amt / price
                    holdings[sym] = holdings.get(sym, 0) + qty
                    
                trades.append({'date': date, 'basket': target_basket, 'equity': equity})
        
        total_return = (equity / self.initial_capital - 1) * 100
        print(f"Sector Momentum Backtest Result: {total_return:.2f}%")
        
        return {
            "total_pnl": equity - self.initial_capital,
            "return_pct": total_return,
            "trades": pd.DataFrame(trades),
            "equity_curve": pd.DataFrame(equity_curve).set_index('date')
        }
