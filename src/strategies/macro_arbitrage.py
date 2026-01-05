import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from .base_strategy import BaseStrategy
try:
    from src.tools.sentiment_analyzer import SentimentAnalyzer
    from src.tools.build_macro_universe import load_macro_universe
    from src.regime_detector import RegimeDetector
except ImportError:
    from tools.sentiment_analyzer import SentimentAnalyzer
    from tools.build_macro_universe import load_macro_universe
    from regime_detector import RegimeDetector

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
                 leader_laggard_map: Dict[str, str] = None,
                 lookback_window_minutes: int = 15,
                 holding_period_minutes: int = 120,
                 z_threshold: float = 2.0,
                 laggard_threshold_pct: float = 0.005,
                 auto_calibrate: bool = False):
        """
        :param leader_laggard_map: Dictionary mapping Leader Symbol -> Laggard Symbol.
                                   If None, loads from src/data/lead_lag_universe.csv
        :param lookback_window_minutes: Time window to calculate the Leader's move.
        :param holding_period_minutes: Time window to hold the trade.
        :param z_threshold: Number of standard deviations for the trigger (default 2.0).
        :param laggard_threshold_pct: Max % change allowed in Laggard to consider it "dislocated" (e.g., 0.005 for 0.5%).
        :param auto_calibrate: If True, runs correlation analysis on startup to set lookback_window.
        """
        if leader_laggard_map is None:
            leader_laggard_map = load_macro_universe()
            if not leader_laggard_map:
                logger.warning(f"[{strategy_id}] No universe map found. Strategy will be empty.")
        
        # Extract all unique symbols from the map
        symbols = list(set(list(leader_laggard_map.keys()) + list(leader_laggard_map.values())))
        
        super().__init__(data_handler, execution_handler, portfolio_manager, strategy_id, symbols)
        
        self.leader_laggard_map = leader_laggard_map
        self.lookback_window = lookback_window_minutes
        self.holding_period = holding_period_minutes
        self.z_threshold = z_threshold
        self.laggard_threshold = laggard_threshold_pct
        
        self.sentiment_analyzer = SentimentAnalyzer(data_handler)
        self.regime_detector = RegimeDetector(data_handler)
        
        # State tracking to avoid re-entering the same move
        self.last_trigger_time = {pair: None for pair in leader_laggard_map.keys()}
        
        # Track open positions for time-based exits: {symbol: entry_time}
        self.open_positions = {}
        
        if auto_calibrate:
            self.calibrate_lag()

    def calibrate_lag(self):
        """
        Automatically determines the best lookback window (lag) based on recent historical data.
        """
        logger.info(f"[{self.strategy_id}] Auto-calibrating lag...")
        
        # Fetch last 5 days of minute data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        
        # Note: get_historical_bars might return a dict of DataFrames
        bars_map = self.data_handler.get_historical_bars(
            self.symbols,
            timeframe_str='1Min',
            start=start_date.strftime('%Y-%m-%d'),
            end=end_date.strftime('%Y-%m-%d')
        )
        
        if not bars_map:
            logger.warning(f"[{self.strategy_id}] Not enough data to calibrate lag. Using default {self.lookback_window}m.")
            return

        lags = []
        for leader, laggard in self.leader_laggard_map.items():
            if leader in bars_map and laggard in bars_map:
                leader_df = bars_map[leader]
                laggard_df = bars_map[laggard]
                
                if leader_df.empty or laggard_df.empty:
                    continue
                    
                # Calculate returns
                leader_returns = leader_df['close'].pct_change().dropna()
                laggard_returns = laggard_df['close'].pct_change().dropna()
                
                # Align indices (intersection of timestamps)
                # Ensure indices are datetime
                if not isinstance(leader_returns.index, pd.DatetimeIndex):
                    leader_returns.index = pd.to_datetime(leader_returns.index)
                if not isinstance(laggard_returns.index, pd.DatetimeIndex):
                    laggard_returns.index = pd.to_datetime(laggard_returns.index)
                    
                common_idx = leader_returns.index.intersection(laggard_returns.index)
                
                if len(common_idx) < 100:
                    logger.warning(f"[{self.strategy_id}] Insufficient overlapping data for {leader}-{laggard}.")
                    continue
                    
                best_lag = self.analyze_lead_lag_correlation(
                    leader_returns.loc[common_idx], 
                    laggard_returns.loc[common_idx]
                )
                lags.append(best_lag)
        
        if lags:
            avg_lag = int(np.mean(lags))
            # Ensure reasonable bounds (e.g., 1 to 60 minutes)
            avg_lag = max(1, min(60, avg_lag))
            self.lookback_window = avg_lag
            logger.info(f"[{self.strategy_id}] Calibrated lookback window to {self.lookback_window} minutes (Avg of {lags}).")
        else:
            logger.warning(f"[{self.strategy_id}] Lag calibration failed (no valid correlations). Keeping default {self.lookback_window}m.")

    def _check_exits(self):
        """
        Checks open positions and closes them if the holding period has expired.
        """
        current_time = datetime.now()
        # Create a list of symbols to close to avoid modifying dict while iterating
        to_close = []
        
        for symbol, entry_time in self.open_positions.items():
            # Calculate duration in minutes
            duration = (current_time - entry_time).total_seconds() / 60
            
            if duration >= self.holding_period:
                logger.info(f"[{self.strategy_id}] Holding period expired for {symbol} ({duration:.1f}m >= {self.holding_period}m). Closing position.")
                to_close.append(symbol)
                
        for symbol in to_close:
            self._close_position(symbol)

    def _close_position(self, symbol: str):
        """
        Closes a position via ExecutionHandler.
        """
        try:
            self.execution_handler.close_position(symbol)
            if symbol in self.open_positions:
                del self.open_positions[symbol]
            logger.info(f"[{self.strategy_id}] Closed position for {symbol}.")
        except Exception as e:
            logger.error(f"[{self.strategy_id}] Failed to close position for {symbol}: {e}")

    def generate_signal(self):
        """
        Main strategy loop.
        1. Check for exits (Time-based).
        2. Monitor Leaders for significant moves.
        3. Check if Laggards are flat (Dislocation).
        4. Validate with NLP (Systematic vs Idiosyncratic).
        5. Execute trade.
        """
        if not self.active:
            return

        # 1. Manage Exits
        self._check_exits()

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
        if len(leader_df) < self.lookback_window + 60: # Need extra data for volatility calc
            return

        # --- 1. Dynamic Volatility Scaling (Z-Score) ---
        # Calculate Rolling Volatility (Standard Deviation of returns)
        # We use a 60-period window (1 hour) to gauge current volatility baseline
        leader_returns_series = leader_df['close'].pct_change()
        leader_vol = leader_returns_series.rolling(window=60).std().iloc[-1]
        
        if pd.isna(leader_vol) or leader_vol == 0:
            return

        # Calculate Leader Move
        current_price_leader = leader_df['close'].iloc[-1]
        past_price_leader = leader_df['close'].iloc[-self.lookback_window]
        leader_return = (current_price_leader - past_price_leader) / past_price_leader
        
        # Scale 1-min volatility to the lookback period (sqrt(T))
        period_vol = leader_vol * np.sqrt(self.lookback_window)
        
        # Calculate Z-Score
        z_score = leader_return / period_vol
        
        # Trigger Condition: Significant Move in Leader (Z-Score > Threshold)
        if abs(z_score) >= self.z_threshold:
            logger.info(f"[{self.strategy_id}] Trigger: {leader} Z-Score {z_score:.2f} (Return {leader_return:.2%}) > {self.z_threshold}.")
            
            # Check if we already traded this recently (simple debounce)
            last_trigger = self.last_trigger_time.get(leader)
            if last_trigger:
                # Don't re-trigger within the holding period
                time_since_trigger = (datetime.now() - last_trigger).total_seconds() / 60
                if time_since_trigger < self.holding_period:
                    logger.info(f"[{self.strategy_id}] Debounce: {leader} triggered recently ({time_since_trigger:.1f}m ago). Skipping.")
                    return
            
            # --- NEW: Correlation Filter ---
            # Only trade if the pair has been correlated recently (e.g., last 60 mins)
            # This filters out "noise" moves where the link is broken
            laggard_returns_series = laggard_df['close'].pct_change()
            
            # Align series for correlation
            # We take the last 60 points
            if len(laggard_returns_series) >= 60 and len(leader_returns_series) >= 60:
                recent_corr = leader_returns_series.tail(60).corr(laggard_returns_series.tail(60))
                
                if recent_corr < 0.7:
                    logger.info(f"[{self.strategy_id}] Filtered: Correlation too low ({recent_corr:.2f} < 0.7).")
                    return
            else:
                # Not enough data for correlation, skip safely
                return

            # --- NEW: Regime Filter ---
            # Only trade in Volatile/Trending regimes (State 1)
            # Note: In a real live loop, we might cache this to avoid calling it every minute
            current_regime = self.regime_detector.get_current_regime()
            if current_regime == 0:
                logger.info(f"[{self.strategy_id}] Filtered: Regime is Calm (0). Waiting for Volatility.")
                return

            # 2. Dislocation Check: Laggard has NOT moved significantly
            current_price_laggard = laggard_df['close'].iloc[-1]
            past_price_laggard = laggard_df['close'].iloc[-self.lookback_window]
            laggard_return = (current_price_laggard - past_price_laggard) / past_price_laggard
            
            # Dynamic Dislocation Threshold: Laggard should have moved less than 25% of the Leader's move
            # Or use the fixed threshold if preferred. Let's use the dynamic one from backtest.
            dynamic_laggard_threshold = abs(leader_return) * 0.25
            
            if abs(laggard_return) < dynamic_laggard_threshold:
                logger.info(f"[{self.strategy_id}] Dislocation found: {laggard} moved {laggard_return:.2%} (Threshold {dynamic_laggard_threshold:.2%}).")
                
                # 3. Regime Filter (HMM)
                # Only trade if we are NOT in a low-volatility sideways chop
                # Assuming portfolio_manager has access to regime_detector or we check vol directly
                # Here we use the simple Volatility Percentile proxy from the backtest for consistency
                # In a full integration, we'd call self.portfolio_manager.regime_detector.get_current_regime()
                
                # Simple Proxy: Is current vol > 20th percentile of recent history?
                # We don't have long history here, so we'll skip or use a simplified check
                # For now, let's assume the Z-Score check implicitly handles "dead" markets 
                # because getting a 2-sigma move in a dead market is hard/rare.
                
                # 4. NLP Filter: Validate Systematic Move
                is_systematic = self.sentiment_analyzer.validate_sector_move(leader)
                
                if is_systematic:
                    logger.info(f"[{self.strategy_id}] NLP Confirmed: Systematic move. Entering trade on {laggard}.")
                    
                    # Determine direction
                    direction = "BUY" if leader_return > 0 else "SELL"
                    
                    # Execute Trade
                    self._place_trade(laggard, direction, current_price_laggard)
                    
                    # Update Trigger Time
                    self.last_trigger_time[leader] = datetime.now()
                else:
                    logger.info(f"[{self.strategy_id}] NLP Rejected: Move likely idiosyncratic to {leader}.")
            else:
                logger.info(f"[{self.strategy_id}] No Dislocation: {laggard} already moved {laggard_return:.2%}.")

    def _place_trade(self, symbol: str, side: str, price: float):
        """
        Executes the trade via ExecutionHandler with dynamic sizing.
        """
        # 1. Get Strategy Allocation
        if hasattr(self.portfolio_manager, 'allocations') and self.strategy_id in self.portfolio_manager.allocations:
            alloc_data = self.portfolio_manager.allocations[self.strategy_id]
            total_equity = alloc_data['equity'] * alloc_data.get('leverage', 1.0)
        else:
            # Fallback if PM not configured correctly
            total_equity = 10000.0 
            logger.warning(f"[{self.strategy_id}] No allocation found in PM. Using fallback ${total_equity}.")

        # 2. Calculate Position Size
        # Divide capital equally among all pairs in the universe
        num_pairs = len(self.leader_laggard_map)
        if num_pairs == 0: num_pairs = 1
        
        target_equity_per_trade = total_equity / num_pairs
        
        # Calculate quantity (floor)
        if price > 0:
            qty = int(target_equity_per_trade / price)
        else:
            qty = 0
            
        if qty < 1:
            logger.warning(f"[{self.strategy_id}] Calculated quantity is 0 for {symbol} (Price: ${price:.2f}, Alloc: ${target_equity_per_trade:.2f}). Skipping.")
            return

        # 3. Check Budget with Portfolio Manager
        estimated_cost = qty * price
        if not self.portfolio_manager.check_trade(self.strategy_id, estimated_cost):
             logger.warning(f"[{self.strategy_id}] PM denied trade for {symbol} (Cost: ${estimated_cost:.2f}).")
             return

        try:
            if side == "BUY":
                self.execution_handler.buy(symbol, qty)
            else:
                self.execution_handler.sell(symbol, qty)
            
            # Track position for exit
            self.open_positions[symbol] = datetime.now()
            
            logger.info(f"[{self.strategy_id}] Placed {side} order for {qty} {symbol} (${estimated_cost:.2f}).")
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
