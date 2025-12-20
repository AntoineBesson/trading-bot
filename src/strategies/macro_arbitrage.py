import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from .base_strategy import BaseStrategy
try:
    from src.tools.sentiment_analyzer import SentimentAnalyzer
except ImportError:
    from tools.sentiment_analyzer import SentimentAnalyzer

logger = logging.getLogger(__name__)

class MacroArbitrageStrategy(BaseStrategy):
    """
    A Lead-Lag "Macro-Arbitrage" strategy that exploits information propagation delays
    between "Leader" assets (Big Caps/Sector ETFs) and "Laggard" assets (Small Caps).
    
    It combines statistical arbitrage (price dislocation) with NLP sentiment analysis
    (to filter out idiosyncratic moves).
    """
    
    def __init__(self, 
                 data_handler, 
                 execution_handler, 
                 portfolio_manager, 
                 strategy_id: str, 
                 leader_laggard_map: Dict[str, str],
                 lookback_window_minutes: int = 15,
                 move_threshold_pct: float = 0.02,
                 laggard_threshold_pct: float = 0.005):
        """
        :param leader_laggard_map: Dictionary mapping Leader Symbol -> Laggard Symbol.
                                   Example: {'JPM': 'KRE', 'NVDA': 'SOXL'}
        :param lookback_window_minutes: Time window to calculate the Leader's move.
        :param move_threshold_pct: Absolute % change in Leader to trigger a potential setup (e.g., 0.02 for 2%).
        :param laggard_threshold_pct: Max % change allowed in Laggard to consider it "dislocated" (e.g., 0.005 for 0.5%).
        """
        # Extract all unique symbols from the map
        symbols = list(set(list(leader_laggard_map.keys()) + list(leader_laggard_map.values())))
        
        super().__init__(data_handler, execution_handler, portfolio_manager, strategy_id, symbols)
        
        self.leader_laggard_map = leader_laggard_map
        self.lookback_window = lookback_window_minutes
        self.move_threshold = move_threshold_pct
        self.laggard_threshold = laggard_threshold_pct
        
        self.sentiment_analyzer = SentimentAnalyzer(data_handler)
        
        # State tracking to avoid re-entering the same move
        self.last_trigger_time = {pair: None for pair in leader_laggard_map.keys()}

    def generate_signal(self):
        """
        Main strategy loop.
        1. Monitor Leaders for significant moves.
        2. Check if Laggards are flat (Dislocation).
        3. Validate with NLP (Systematic vs Idiosyncratic).
        4. Execute trade.
        """
        if not self.active:
            return

        logger.info(f"[{self.strategy_id}] Scanning for Lead-Lag opportunities...")

        # Fetch latest data for all symbols
        # We need minute bars for the lookback window
        # Assuming data_handler has a way to get the latest 'n' minute bars
        # If not, we might need to fetch a larger chunk.
        
        # For this implementation, we'll assume we can fetch the last 60 minutes to be safe
        end_time = datetime.now(pd.Timestamp.now().tz) if hasattr(pd.Timestamp.now(), 'tz') else datetime.now()
        start_time = end_time - timedelta(minutes=self.lookback_window + 10)
        
        # Format dates for API
        start_str = start_time.strftime('%Y-%m-%d')
        # We might need intraday data, so we rely on data_handler to handle the request
        # Note: data_handler.get_historical_bars usually fetches daily or historical. 
        # For live trading, we'd use a real-time stream or a snapshot.
        # Here we simulate using the historical fetcher for the "latest" bars.
        
        bars_map = self.data_handler.get_historical_bars(
            self.symbols, 
            timeframe_str='1Min', 
            start=start_str
        )
        
        if not bars_map:
            logger.warning(f"[{self.strategy_id}] No data received.")
            return

        for leader, laggard in self.leader_laggard_map.items():
            self._check_pair(leader, laggard, bars_map)

    def _check_pair(self, leader: str, laggard: str, bars_map: Dict[str, pd.DataFrame]):
        """
        Analyzes a single Leader-Laggard pair.
        """
        if leader not in bars_map or laggard not in bars_map:
            return

        leader_df = bars_map[leader]
        laggard_df = bars_map[laggard]
        
        if leader_df.empty or laggard_df.empty:
            return

        # Get the return over the lookback window
        # We look at the change from 'lookback_window' minutes ago to now
        if len(leader_df) < self.lookback_window:
            return

        # Calculate Leader Move
        current_price_leader = leader_df['close'].iloc[-1]
        past_price_leader = leader_df['close'].iloc[-self.lookback_window]
        leader_return = (current_price_leader - past_price_leader) / past_price_leader
        
        # 1. Trigger Condition: Significant Move in Leader
        if abs(leader_return) >= self.move_threshold:
            logger.info(f"[{self.strategy_id}] Trigger: {leader} moved {leader_return:.2%} in last {self.lookback_window}m.")
            
            # Check if we already traded this recently (simple debounce)
            # In a real system, we'd track the specific 'event' ID.
            
            # 2. Dislocation Check: Laggard has NOT moved significantly
            current_price_laggard = laggard_df['close'].iloc[-1]
            past_price_laggard = laggard_df['close'].iloc[-self.lookback_window]
            laggard_return = (current_price_laggard - past_price_laggard) / past_price_laggard
            
            if abs(laggard_return) < self.laggard_threshold:
                logger.info(f"[{self.strategy_id}] Dislocation found: {laggard} only moved {laggard_return:.2%}.")
                
                # 3. NLP Filter: Validate Systematic Move
                is_systematic = self.sentiment_analyzer.validate_sector_move(leader)
                
                if is_systematic:
                    logger.info(f"[{self.strategy_id}] NLP Confirmed: Systematic move. Entering trade on {laggard}.")
                    
                    # Determine direction
                    direction = "BUY" if leader_return > 0 else "SELL"
                    
                    # Execute Trade
                    # Size would be calculated by Portfolio Manager, here we request a target
                    # For simplicity, we'll just log the signal or place a fixed size order
                    self._place_trade(laggard, direction)
                else:
                    logger.info(f"[{self.strategy_id}] NLP Rejected: Move likely idiosyncratic to {leader}.")
            else:
                logger.info(f"[{self.strategy_id}] No Dislocation: {laggard} already moved {laggard_return:.2%}.")

    def _place_trade(self, symbol: str, side: str):
        """
        Executes the trade via ExecutionHandler.
        """
        # This is a simplified placeholder. 
        # In the real bot, we'd calculate position size based on volatility/risk.
        qty = 10 # Placeholder
        try:
            if side == "BUY":
                self.execution_handler.buy(symbol, qty)
            else:
                self.execution_handler.sell(symbol, qty)
            logger.info(f"[{self.strategy_id}] Placed {side} order for {qty} {symbol}.")
        except Exception as e:
            logger.error(f"[{self.strategy_id}] Trade failed: {e}")

    def run_backtest(self, start_date, end_date, timeframe):
        """
        Backtesting implementation.
        """
        logger.info(f"[{self.strategy_id}] Running backtest from {start_date} to {end_date}...")
        # Implementation would involve iterating through historical data 
        # and calling _check_pair logic without live execution.
        pass

    # --- Phase 2: Optimization / Analysis Tools ---

    @staticmethod
    def analyze_lead_lag_correlation(leader_returns: pd.Series, laggard_returns: pd.Series, max_lag: int = 60) -> int:
        """
        Performs Cross-Correlation Analysis to find the "Information Propagation Delay".
        
        :param leader_returns: Minute-by-minute returns of the Leader.
        :param laggard_returns: Minute-by-minute returns of the Laggard.
        :param max_lag: Maximum lag in minutes to test.
        :return: The lag (in minutes) with the highest correlation.
        """
        correlations = []
        lags = range(1, max_lag + 1)
        
        for lag in lags:
            # Shift laggard BACKWARDS to align future laggard returns with current leader returns?
            # No, we want Corr(Leader(t), Laggard(t + k))
            # So we shift Laggard returns by -k (shift up) to align t+k with t
            shifted_laggard = laggard_returns.shift(-lag)
            
            # Calculate correlation, dropping NaNs created by shift
            corr = leader_returns.corr(shifted_laggard)
            correlations.append(corr)
            
        # Find the index of the max correlation
        # We use abs() because the relationship could be inverse (though unlikely for this strategy)
        # Usually we expect positive correlation.
        max_corr_idx = np.argmax(correlations)
        best_lag = lags[max_corr_idx]
        max_corr_val = correlations[max_corr_idx]
        
        logger.info(f"Lead-Lag Analysis: Peak correlation {max_corr_val:.4f} found at {best_lag} minutes lag.")
        
        return best_lag
