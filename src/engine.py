import time
import sys
import logging
import os
import json
import threading
from datetime import datetime, time as dtime
import pytz
from dotenv import load_dotenv
import pandas as pd

# Add src to path if needed, though usually not needed if running as module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_handler import DataHandler
from execution import ExecutionHandler
from options.data_handler import OptionDataHandler
from options.multileg import MultiLegExecutionHelper
from universe_manager import UniverseManager
from portfolio_manager import PortfolioManager
from strategy_manager import StrategyManager
from strategies_config import (
    create_option_pair_config, 
    create_volatility_arb_config, 
    create_sector_momentum_config,
    create_macro_arbitrage_config
)

# --- Configuration ---
SLEEP_DELAY = 60 
SCAN_INTERVAL = 24 * 60 * 60 

logger = logging.getLogger(__name__)

class TradingEngine:
    def __init__(self):
        """Initializes the bot components."""
        self._stop_event = threading.Event()
        self.thread = None
        
        # History persistence
        self.history_file = os.path.join(os.path.dirname(__file__), "data", "equity_history.json")
        self.equity_history = self._load_history()

        # 1. Load Environment
        load_dotenv()
        
        # 2. Initialize Handlers
        logger.info("Initializing Data & Execution Handlers...")
        try:
            # Set paper_trading=True for safety!
            self.dh = DataHandler(paper_trading=True)
            self.eh = ExecutionHandler(paper_trading=True)
        except Exception as e:
            logger.critical(f"Failed to initialize handlers: {e}")
            # In a service, we might not want to exit the process, but maybe raise
            raise e

        # 3. Initialize Managers
        self.pm = PortfolioManager(self.dh)
        self.sm = StrategyManager(self.dh, self.eh, self.pm)
        
        # 4. Initialize Helpers
        self.option_data_handler = OptionDataHandler(self.dh)
        self.multi_leg_helper = MultiLegExecutionHelper(self.eh)
        
        # 5. Initialize Universe Manager
        try:
            universe_path = os.path.join(os.path.dirname(__file__), "data", "universe.csv")
            self.universe = pd.read_csv(universe_path)['symbol'].tolist()
            logger.info(f"Loaded {len(self.universe)} symbols from {universe_path}")
        except Exception as e:
            logger.warning(f"Could not load universe.csv ({e}). Using default S&P Financials list.")
            # Default universe (S&P 500 Financials subset or similar)
            self.universe = [
                'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'BLK', 'SPY', 'XLF' # Simplified default
            ]
            
        self.universe_manager = UniverseManager(
            data_handler=self.dh,
            universe=self.universe,
            lookback_days=180,
            p_value_threshold=0.05,
            z_score_threshold=1.5
        )
        
        # 6. Initial Strategy Setup
        self.rebalance_strategies()

        # 7. Reconcile State
        self.sm.reconcile_positions()
        
        # 8. Record initial state
        self.record_history()

    def _load_history(self):
        """Loads equity history from disk."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load history: {e}")
        return []

    def record_history(self):
        """Saves the current portfolio value and a benchmark price."""
        try:
            # 1. Get Current Timestamp
            now = datetime.now().timestamp()
            
            # 2. Get Portfolio Value (Cash + Holdings)
            # Ensure your PortfolioManager has a get_total_equity() method or similar
            # If not, use self.pm.current_cash + value_of_positions
            total_equity = self.pm.get_total_equity() 
            
            # 3. Append to History
            self.equity_history.append({
                "time": now,
                "value": total_equity
            })
            
            # Keep only last 1000 points to save memory
            if len(self.equity_history) > 1000:
                self.equity_history.pop(0)
            
            # 4. Save to Disk
            try:
                with open(self.history_file, 'w') as f:
                    json.dump(self.equity_history, f)
            except Exception as e:
                logger.error(f"Failed to save history: {e}")
                
        except Exception as e:
            logger.error(f"Error recording history: {e}")

    def rebalance_strategies(self):
        """Scans the universe and rebuilds the strategy list."""
        logger.info("Rebalancing strategies based on universe scan...")
        
        # 1. Scan for pairs
        watchlist = self.universe_manager.scan()
        
        # 2. Build Strategy Configs
        strategy_configs = []
        
        # A. Option Pairs Strategies
        for item in watchlist:
            sym_a = item['symbol_a']
            sym_b = item['symbol_b']
            
            config = create_option_pair_config(sym_a, sym_b, allocation=5000.0)
            config['parameters']['option_data_handler'] = self.option_data_handler
            config['parameters']['multi_leg_execution'] = self.multi_leg_helper
            strategy_configs.append(config)
            
        # B. Volatility Arbitrage Strategies
        vol_arb_symbols = ['SPY']
        if watchlist:
            vol_arb_symbols.append(watchlist[0]['symbol_a'])
            
        for sym in vol_arb_symbols:
            config = create_volatility_arb_config(sym, allocation=10000.0)
            config['parameters']['option_data_handler'] = self.option_data_handler
            config['parameters']['multi_leg_execution'] = self.multi_leg_helper
            strategy_configs.append(config)
            
        # C. Sector Momentum Strategy
        sector_config = create_sector_momentum_config(allocation=30000.0)
        strategy_configs.append(sector_config)

        # D. Macro Arbitrage Strategy
        macro_config = create_macro_arbitrage_config(allocation=20000.0)
        strategy_configs.append(macro_config)

        # 3. Update Strategy Manager
        self.sm.update_strategies(strategy_configs)

    def is_market_open(self):
        """Checks if the US market is currently open."""
        tz = pytz.timezone('US/Eastern')
        now = datetime.now(tz)
        
        if now.weekday() >= 5:
            return False

        market_open = dtime(9, 30)
        market_close = dtime(16, 0)
        current_time = now.time()

        return market_open <= current_time <= market_close

    def run_loop(self):
        """The main infinite loop."""
        logger.info("Bot engine started.")
        
        last_scan = time.time()
        
        while not self._stop_event.is_set():
            try:
                # --- 0. Market Hours Check ---
                if not self.is_market_open():
                    logger.info("Market is closed. Waiting...")
                    # Wait for 5 minutes or until stopped
                    if self._stop_event.wait(300):
                        break
                    continue
                
                logger.info("Starting new tick...")

                # --- 1. Periodic Universe Scan ---
                if time.time() - last_scan > SCAN_INTERVAL:
                    logger.info("Scheduled universe scan triggered.")
                    self.rebalance_strategies()
                    last_scan = time.time()
                self.record_history()

                # --- 2. Run Strategies ---
                self.sm.run_tick()

                # --- 3. Sleep ---
                logger.info(f"Tick complete. Sleeping for {SLEEP_DELAY} seconds...")
                if self._stop_event.wait(SLEEP_DELAY):
                    break

            except Exception as e:
                logger.error(f"An error occurred in the main loop: {e}")
                logger.info("Retrying in 60 seconds...")
                if self._stop_event.wait(60):
                    break

        logger.info("Bot engine stopped.")

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self._stop_event.clear()
            self.thread = threading.Thread(target=self.run_loop, daemon=True)
            self.thread.start()
            logger.info("TradingEngine thread started.")

    def stop(self):
        if self.thread and self.thread.is_alive():
            logger.info("Stopping TradingEngine thread...")
            self._stop_event.set()
            self.thread.join()
            logger.info("TradingEngine thread stopped.")

    def get_status(self):
        strategies_status = []
        for strat_id, strategy in self.sm.strategies.items():
            strategies_status.append({
                "id": strat_id,
                "type": type(strategy).__name__,
                "active": getattr(strategy, 'active', True),
                "symbols": strategy.symbols
            })
            
        return {
            "running": self.thread is not None and self.thread.is_alive(),
            "strategies": strategies_status
        }
