import pandas as pd
import numpy as np
import logging
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class DonchianBreakoutStrategy(BaseStrategy):
    """
    Donchian Channel Breakout Strategy.
    - GO LONG when price > Highest High of last N bars.
    - GO SHORT when price < Lowest Low of last N bars.
    """
    def __init__(self, data_handler, execution_handler, portfolio_manager, strategy_id, symbols, lookback=20):
        super().__init__(data_handler, execution_handler, portfolio_manager, strategy_id, symbols)
        self.lookback = lookback
        self.name = "DonchianBreakout"

    def generate_signal(self):
        signals = []
        for symbol in self.symbols:
            try:
                # 1. Fetch History (Lookback + 1 for calculation)
                bars = self.data_handler.get_historical_prices(symbol, days=self.lookback*2)
                if len(bars) < self.lookback:
                    continue

                # 2. Calculate Donchian Channels
                # We typically use the 'High' and 'Low' columns. 
                # If your data_handler only gives 'Close', use that, but High/Low is better.
                closes = bars['close']
                
                # The channel is based on the *previous* N bars (don't include current bar to avoid lookahead)
                upper_band = closes.rolling(window=self.lookback).max().shift(1)
                lower_band = closes.rolling(window=self.lookback).min().shift(1)
                
                current_price = closes.iloc[-1]
                prev_upper = upper_band.iloc[-1]
                prev_lower = lower_band.iloc[-1]

                # 3. Logic
                current_pos = self.get_current_position_size(symbol)
                
                # Breakout UP -> Long
                if current_price > prev_upper:
                    if current_pos <= 0:
                        logger.info(f"[{self.strategy_id}] {symbol} Breakout UP ({current_price} > {prev_upper}). Going LONG.")
                        signals.append({'symbol': symbol, 'action': 'BUY', 'quantity': 10}) # Simplified qty
                
                # Breakout DOWN -> Short
                elif current_price < prev_lower:
                    if current_pos >= 0:
                        logger.info(f"[{self.strategy_id}] {symbol} Breakout DOWN ({current_price} < {prev_lower}). Going SHORT.")
                        signals.append({'symbol': symbol, 'action': 'SELL', 'quantity': 10})

            except Exception as e:
                logger.error(f"Error in Donchian Strategy for {symbol}: {e}")
        
        return signals

    def get_current_position_size(self, symbol):
        # Helper to check if we are already long/short (Mock implementation)
        # In your real bot, check self.portfolio_manager or self.execution_handler
        return 0

    @staticmethod
    def backtest(df, lookback=20, return_trades=False):
        """
        Vectorized backtest for Permutation Testing.
        :param df: DataFrame with 'close' column.
        :param lookback: Lookback period for Donchian Channel.
        :param return_trades: If True, returns list of trade returns. If False, returns Profit Factor.
        """
        # Signal: 1 if Close > Max(Last N), -1 if Close < Min(Last N)
        upper = df['close'].rolling(lookback).max().shift(1)
        lower = df['close'].rolling(lookback).min().shift(1)
        
        signals = np.zeros(len(df))
        signals[df['close'] > upper] = 1
        signals[df['close'] < lower] = -1
        
        # Forward fill positions (hold until signal changes)
        signals = pd.Series(signals).replace(0, np.nan).ffill().fillna(0).values
        
        # Returns
        market_returns = df['close'].pct_change().shift(-1).fillna(0)
        strategy_returns = signals * market_returns
        
        if return_trades:
            return strategy_returns[strategy_returns != 0].values
            
        gains = strategy_returns[strategy_returns > 0].sum()
        losses = abs(strategy_returns[strategy_returns < 0].sum())
        
        if losses == 0: return 0 if gains == 0 else 999
        return gains / losses