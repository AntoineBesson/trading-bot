from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from math import log, sqrt, exp
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from scipy.stats import norm

from src.strategies.base_strategy import BaseStrategy
from options.data_handler import OptionDataHandler
from options.multileg import MultiLegExecutionHelper

logger = logging.getLogger(__name__)

class VolatilityArbitrageStrategy(BaseStrategy):
    """
    Volatility Arbitrage Strategy (Gamma Scalping).
    
    Core Hypothesis: Variance Risk Premium.
    Bet: Implied Volatility (IV) > Realized Volatility (RV).
    Structure: Short Straddle (Delta Neutral) + Dynamic Hedging (Gamma Scalping).
    """
    
    def __init__(self, 
                 data_handler, 
                 execution_handler, 
                 portfolio_manager, 
                 strategy_id: str, 
                 symbol: str,
                 option_data_handler: OptionDataHandler,
                 multi_leg_execution: MultiLegExecutionHelper,
                 lookback_days: int = 30,
                 entry_threshold: float = 1.25, # IV / RV > 1.25
                 delta_threshold: float = 10.0, # Delta threshold for hedging (e.g. +/- 10 deltas)
                 profit_target: float = 0.50,   # 50% of max premium
                 stop_loss_iv_mult: float = 1.5 # Stop if IV expands by 50%
                 ):
        super().__init__(data_handler, execution_handler, portfolio_manager, strategy_id, [symbol])
        self.symbol = symbol
        self.option_data_handler = option_data_handler
        self.multi_leg_execution = multi_leg_execution
        self.lookback_days = lookback_days
        self.entry_threshold = entry_threshold
        self.delta_threshold = delta_threshold
        self.profit_target = profit_target
        self.stop_loss_iv_mult = stop_loss_iv_mult
        
        # State tracking
        self.entry_iv = 0.0
        self.entry_price = 0.0
        self.short_call_symbol = None
        self.short_put_symbol = None
        self.strike = 0.0
        self.expiration = None
        
    def calculate_parkinson_volatility(self, n: int = 30) -> Optional[float]:
        """
        Calculates Parkinson Volatility using High/Low prices.
        Formula: sigma = sqrt( (1 / (4 * n * ln(2))) * sum( ln(H/L)^2 ) )
        Returns annualized volatility.
        """
        # Fetch historical data (need slightly more than n days to be safe)
        start_date = (datetime.now() - timedelta(days=n*2)).strftime('%Y-%m-%d')
        bars_map = self.data_handler.get_historical_bars([self.symbol], "1D", start_date)
        
        if not bars_map or self.symbol not in bars_map:
            logger.warning(f"[{self.strategy_id}] No historical data for {self.symbol}")
            return None
            
        df = bars_map[self.symbol]
        if len(df) < n:
            logger.warning(f"[{self.strategy_id}] Not enough data for Parkinson Vol. Need {n}, got {len(df)}")
            return None
            
        # Take last n rows
        df = df.tail(n).copy()
        
        # Ensure high and low are floats
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        
        # Calculate log(High / Low)
        # Handle cases where High == Low (log(1) = 0)
        df['hl_ratio_log'] = np.log(df['high'] / df['low'])
        df['hl_sq'] = df['hl_ratio_log'] ** 2
        
        sum_sq = df['hl_sq'].sum()
        const = 1.0 / (4.0 * n * log(2.0))
        
        sigma_daily = sqrt(const * sum_sq)
        sigma_annualized = sigma_daily * sqrt(252)
        
        return sigma_annualized

    def get_atm_iv_and_options(self) -> tuple[float, pd.DataFrame]:
        """
        Fetches the option chain, finds ATM options, and calculates average IV.
        Returns (iv, options_df)
        """
        chain = self.option_data_handler.fetch_option_chain(self.symbol)
        
        if chain.empty:
            return 0.0, pd.DataFrame()
            
        # Filter for expiration between 25 and 45 days
        # Assuming 'expiration' column is YYYY-MM-DD
        today = datetime.now().date()
        # Ensure expiration is datetime
        chain['expiration_dt'] = pd.to_datetime(chain['expiration']).dt.date
        chain['days_to_expiry'] = (chain['expiration_dt'] - today).apply(lambda x: x.days)
        
        target_days = 30
        # Find expiration closest to 30 days, but at least 15 days out
        valid_expirations = chain[chain['days_to_expiry'] > 15]['days_to_expiry'].unique()
        if len(valid_expirations) == 0:
            return 0.0, pd.DataFrame()
            
        closest_expiry = min(valid_expirations, key=lambda x: abs(x - target_days))
        expiry_chain = chain[chain['days_to_expiry'] == closest_expiry]
        
        # Find ATM Strike
        # Get spot from data_handler
        latest_bars = self.data_handler.get_historical_bars([self.symbol], "1Min", 
                                                            (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
        if not latest_bars or self.symbol not in latest_bars or latest_bars[self.symbol].empty:
             # Fallback to daily
             latest_bars = self.data_handler.get_historical_bars([self.symbol], "1D", 
                                                            (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'))
        
        if not latest_bars or self.symbol not in latest_bars or latest_bars[self.symbol].empty:
            logger.warning(f"[{self.strategy_id}] Could not get spot price for {self.symbol}")
            return 0.0, pd.DataFrame()
            
        spot = float(latest_bars[self.symbol].iloc[-1]['close'])
        
        # Find strike closest to spot
        strikes = expiry_chain['strike'].unique()
        atm_strike = min(strikes, key=lambda x: abs(x - spot))
        
        atm_options = expiry_chain[expiry_chain['strike'] == atm_strike]
        
        # Calculate average IV of Call and Put
        ivs = atm_options['implied_vol'].astype(float)
        avg_iv = ivs.mean()
        
        return avg_iv, atm_options

    def generate_signal(self):
        """
        Main logic loop.
        """
        # 1. Calculate RV
        rv = self.calculate_parkinson_volatility(self.lookback_days)
        if rv is None or rv == 0:
            return

        # 2. Get IV and ATM options
        # We only need this if we are looking to enter OR if we need current IV for management
        iv, atm_options = self.get_atm_iv_and_options()
        if iv == 0:
            return
            
        logger.info(f"[{self.strategy_id}] {self.symbol} IV: {iv:.2%}, RV: {rv:.2%}, Ratio: {iv/rv:.2f}")

        # 3. Entry Logic
        if self.position == "flat":
            if iv / rv > self.entry_threshold:
                logger.info(f"[{self.strategy_id}] Entry Signal! IV/RV > {self.entry_threshold}")
                if not atm_options.empty:
                    self.execute_entry(atm_options)
        
        # 4. Management Logic (Gamma Scalping)
        elif self.position == "invested":
            self.manage_position(iv)

    def execute_entry(self, atm_options):
        # Sell 1 Call and 1 Put (Short Straddle)
        try:
            call = atm_options[atm_options['option_type'] == 'call'].iloc[0]
            put = atm_options[atm_options['option_type'] == 'put'].iloc[0]
        except IndexError:
            logger.error(f"[{self.strategy_id}] Could not find both Call and Put for ATM strike.")
            return
        
        self.short_call_symbol = call['symbol']
        self.short_put_symbol = put['symbol']
        self.strike = float(call['strike'])
        self.expiration = call['expiration']
        
        logger.info(f"[{self.strategy_id}] Selling Straddle: Call {self.short_call_symbol}, Put {self.short_put_symbol} @ Strike {self.strike}")
        
        # Submit orders
        self.execution_handler.submit_order(self.short_call_symbol, 'sell', 1)
        self.execution_handler.submit_order(self.short_put_symbol, 'sell', 1)
        
        # Update state
        self.position = "invested"
        self.entry_iv = (float(call['implied_vol']) + float(put['implied_vol'])) / 2
        self.entry_price = (float(call['price']) + float(put['price'])) 
        
    def manage_position(self, current_iv):
        # Get current spot
        latest_bars = self.data_handler.get_historical_bars([self.symbol], "1Min", (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
        if not latest_bars or self.symbol not in latest_bars or latest_bars[self.symbol].empty:
             # Fallback to daily
             latest_bars = self.data_handler.get_historical_bars([self.symbol], "1D", 
                                                            (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'))
        
        if not latest_bars or self.symbol not in latest_bars or latest_bars[self.symbol].empty:
            return
            
        spot = float(latest_bars[self.symbol].iloc[-1]['close'])
        
        # Calculate Greeks and Prices for our short positions
        try:
            expiry_date = pd.to_datetime(self.expiration).date()
        except Exception:
            logger.error(f"[{self.strategy_id}] Invalid expiration date: {self.expiration}")
            return

        ttm = (expiry_date - datetime.now().date()).days / 365.0
        if ttm <= 0:
            logger.info(f"[{self.strategy_id}] Options expired. Closing.")
            self.close_all()
            return
        
        # Calculate Current Option Prices (Theoretical)
        call_price = self.option_data_handler.greeks.price("call", spot, self.strike, ttm, current_iv)
        put_price = self.option_data_handler.greeks.price("put", spot, self.strike, ttm, current_iv)
        current_premium = call_price + put_price
        
        # --- EXIT CHECKS ---
        
        # 1. Profit Take (50% of max premium)
        # We sold for self.entry_price. We want to buy back at self.entry_price * 0.5
        if current_premium <= self.entry_price * (1 - self.profit_target):
            logger.info(f"[{self.strategy_id}] PROFIT TARGET REACHED: Current Premium {current_premium:.2f} <= 50% of {self.entry_price:.2f}")
            self.close_all()
            return

        # 2. Stop Loss: IV Expansion
        if current_iv > self.entry_iv * self.stop_loss_iv_mult:
            logger.warning(f"[{self.strategy_id}] STOP LOSS: IV Expanded significantly ({current_iv:.2%} vs {self.entry_iv:.2%})")
            self.close_all()
            return
            
        # 3. Stop Loss: Price Move (2x Expected Move)
        # Expected Move = Spot * IV * sqrt(30/365) approx, or just use entry IV and 30 days
        # Let's use the entry parameters for the expected move benchmark
        expected_move = self.strike * self.entry_iv * sqrt(30/365.0) 
        if abs(spot - self.strike) > 2 * expected_move:
             logger.warning(f"[{self.strategy_id}] STOP LOSS: Price moved > 2x Expected Move ({abs(spot - self.strike):.2f} > {2*expected_move:.2f})")
             self.close_all()
             return

        # --- HEDGING ---
        
        # Call Delta (Long)
        call_metrics = self.option_data_handler.greeks.metrics("call", spot, self.strike, ttm, current_iv)
        put_metrics = self.option_data_handler.greeks.metrics("put", spot, self.strike, ttm, current_iv)
        
        # We are SHORT options, so delta is negative of long delta
        short_call_delta = -call_metrics['delta']
        short_put_delta = -put_metrics['delta']
        
        # Total Option Delta (for 1 contract each = 100 shares multiplier)
        option_delta = (short_call_delta + short_put_delta) * 100
        
        # Get current stock shares
        positions = self.execution_handler.get_all_positions()
        current_shares = 0
        for pos in positions:
            if pos.symbol == self.symbol:
                current_shares = float(pos.qty)
                break
        
        total_delta = option_delta + current_shares
        
        logger.info(f"[{self.strategy_id}] Delta Check: Option Delta {option_delta:.2f}, Shares {current_shares}, Total {total_delta:.2f}")
        
        # Hedging Logic
        if abs(total_delta) > self.delta_threshold:
            shares_to_trade = -total_delta
            action = "buy" if shares_to_trade > 0 else "sell"
            qty = abs(int(shares_to_trade))
            
            if qty > 0:
                logger.info(f"[{self.strategy_id}] Hedging: {action.upper()} {qty} shares of {self.symbol}")
                self.execution_handler.submit_order(self.symbol, action, qty)

    def close_all(self):
        logger.info(f"[{self.strategy_id}] Closing all positions.")
        # Close stock
        self.execution_handler.close_position(self.symbol)
        # Close options
        if self.short_call_symbol:
            self.execution_handler.close_position(self.short_call_symbol)
        if self.short_put_symbol:
            self.execution_handler.close_position(self.short_put_symbol)
        
        self.position = "flat"
        self.short_call_symbol = None
        self.short_put_symbol = None

    def run_backtest(self, start_date, end_date, timeframe="1D"):
        """
        Runs a historical backtest of the Volatility Arbitrage strategy.
        """
        logger.info(f"[{self.strategy_id}] Starting Backtest from {start_date} to {end_date}...")
        
        # 1. Get Data
        bars_map = self.data_handler.get_historical_bars([self.symbol], timeframe, start_date, end_date)
        if not bars_map or self.symbol not in bars_map:
            logger.error("No data for backtest.")
            return

        df = bars_map[self.symbol].copy()
        df['returns'] = df['close'].pct_change()
        df['log_ret'] = np.log(df['close'] / df['close'].shift(1))
        
        # 2. Calculate RV (Parkinson)
        # sigma = sqrt( (1 / (4 * n * ln(2))) * sum( ln(H/L)^2 ) )
        n = self.lookback_days
        const = 1.0 / (4.0 * n * log(2.0))
        df['hl_ratio_log'] = np.log(df['high'] / df['low'])
        df['hl_sq'] = df['hl_ratio_log'] ** 2
        df['rv_parkinson'] = (df['hl_sq'].rolling(window=n).sum() * const).apply(sqrt) * sqrt(252)
        
        # 3. Simulate IV (Proxy: 1.3 * RV as a baseline "market premium")
        # In a real backtest, you would use historical IV data.
        df['iv_proxy'] = df['rv_parkinson'] * 1.3
        
        # 4. Simulate Strategy
        cumulative_pnl = 0.0
        trades = []
        in_position = False
        entry_iv = 0.0
        
        for i, row in df.iterrows():
            if pd.isna(row['rv_parkinson']) or pd.isna(row['iv_proxy']):
                continue
                
            # Signal Check
            iv = row['iv_proxy']
            rv = row['rv_parkinson']
            
            if not in_position:
                if iv / rv > self.entry_threshold:
                    in_position = True
                    entry_iv = iv
                    trades.append({'date': i, 'type': 'ENTRY', 'price': row['close'], 'iv': iv, 'rv': rv})
            else:
                # In Position: Calculate PnL
                # Short Straddle PnL ~= 0.5 * Gamma * S^2 * (ImpliedVariance - RealizedVariance)
                
                # Calculate Greeks (Approximate for ATM Straddle)
                # Gamma_straddle ~= 2 / (S * IV * sqrt(T))
                # Assume constant 30 days to expiry for the "rolling" position
                T = 30.0 / 365.0
                S = row['close']
                if S <= 0 or iv <= 0: continue
                
                gamma = 2 * norm.pdf(0) / (S * iv * sqrt(T)) # norm.pdf(0) ~= 0.3989
                
                # Daily Return squared (Realized Variance for this step)
                ret_sq = row['log_ret'] ** 2
                
                # Expected Variance (IV^2 * dt)
                dt = 1.0 / 252.0
                expected_var = (iv ** 2) * dt
                
                # PnL Calculation
                daily_pnl = 0.5 * gamma * (S**2) * (expected_var - ret_sq)
                cumulative_pnl += daily_pnl
                
                # Exit Checks
                # 1. IV Expansion (Stop Loss)
                if iv > entry_iv * self.stop_loss_iv_mult:
                    in_position = False
                    trades.append({'date': i, 'type': 'EXIT_STOP_IV', 'price': row['close'], 'pnl': cumulative_pnl})
                
                # 2. Signal Reversal (IV/RV drops)
                elif iv / rv < 1.0: 
                    in_position = False
                    trades.append({'date': i, 'type': 'EXIT_SIGNAL', 'price': row['close'], 'pnl': cumulative_pnl})

        logger.info(f"[{self.strategy_id}] Backtest Complete. Total PnL: {cumulative_pnl:.2f}")
        print(f"Backtest Results for {self.symbol}:")
        print(f"Total PnL: ${cumulative_pnl:.2f}")
        print(f"Trades: {len(trades)}")
        return cumulative_pnl
