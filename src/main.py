import time
import sys
import signal
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

# --- Import your modules ---
# (We add 'src' to the path so this works no matter where you run it from)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_handler import DataHandler
from execution import ExecutionHandler
from strategies.pairs_trade import PairsTradeStrategy
from strategies.option_pairs import OptionPairsStrategy
from options.data_handler import OptionDataHandler
from options.multileg import MultiLegExecutionHelper

# --- Configuration ---
# How often the bot checks for signals (in seconds)
SLEEP_DELAY = 60 

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("trading_bot.log"), # Save to file
        logging.StreamHandler(sys.stdout)       # Print to console
    ]
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        """Initializes the bot components."""
        self.keep_running = True
        
        # 1. Load Environment
        load_dotenv()
        
        # 2. Initialize Handlers
        logger.info("Initializing Data & Execution Handlers...")
        try:
            # Set paper_trading=True for safety! Change to False only when ready to lose money.
            self.dh = DataHandler(paper_trading=True)
            self.eh = ExecutionHandler(paper_trading=True)
        except Exception as e:
            logger.critical(f"Failed to initialize handlers: {e}")
            sys.exit(1)

        # 3. Initialize Strategy Stack
        self.option_data_handler = OptionDataHandler(self.dh)
        self.multi_leg_helper = MultiLegExecutionHelper(self.eh)
        logger.info("Initializing strategies...")
        self.strategies = self._build_strategies()
        logger.info(
            "Loaded strategies: %s",
            ", ".join(getattr(strategy, "name", strategy.__class__.__name__) for strategy in self.strategies),
        )
        
        # 4. Register Signal Handlers (for graceful shutdown)
        signal.signal(signal.SIGINT, self.handle_exit_signal)
        signal.signal(signal.SIGTERM, self.handle_exit_signal)

    def _build_strategies(self):
        """Create and return the configured strategies."""

        strategies = []

        strategies.append(
            PairsTradeStrategy(
                data_handler=self.dh,
                execution_handler=self.eh,
                symbol_a="V",      # <--- REPLACE with your Symbol A
                symbol_b="MA",     # <--- REPLACE with your Symbol B
                hedge_ratio=0.527, # <--- REPLACE with your Hedge Ratio from the notebook
                entry_threshold=2.0,
                exit_threshold=0.0,
                auto_execute=True,
            )
        )

        strategies.append(
            OptionPairsStrategy(
                data_handler=self.dh,
                execution_handler=self.eh,
                symbol_a="V",
                symbol_b="MA",
                option_type="call",
                target_delta=0.45,
                days_to_expiry=30,
                entry_threshold=0.5,
                exit_threshold=0.0,
                contracts=1,
                auto_execute=True,
                option_data_handler=self.option_data_handler,
                multi_leg_execution=self.multi_leg_helper,
            )
        )

        return strategies

    def handle_exit_signal(self, signum, frame):
        """Handles Ctrl+C or kill signals to stop the bot gracefully."""
        logger.info("Shutdown signal received. Finishing current iteration...")
        self.keep_running = False

    def run(self):
        """The main infinite loop."""
        logger.info("Bot started. Running 24/7 loop...")
        
        while self.keep_running:
            try:
                for strategy in self.strategies:
                    name = getattr(strategy, "name", strategy.__class__.__name__)
                    symbols = getattr(strategy, "symbols", [])
                    pair_desc = "/".join(symbols) if symbols else getattr(strategy, "symbol_a", name)

                    # --- 1. Heartbeat ---
                    logger.info(f"[{name}] Checking market data for {pair_desc}...")

                    # --- 2. Generate & Execute Signals ---
                    signals = strategy.generate_signal()

                    if signals:
                        logger.info(f"[{name}] Signals generated: {signals}")
                    else:
                        z_score = getattr(strategy, "last_z_score", None)
                        if z_score is not None:
                            logger.info(f"[{name}] No trade. Z-Score: {z_score:.4f}")
                        else:
                            logger.info(f"[{name}] No trade. Criteria not met.")

                # --- 3. Sleep ---
                # Wait for the next check (e.g., 1 minute)
                time.sleep(SLEEP_DELAY)

            except Exception as e:
                # --- 4. Error Handling ---
                # If the internet goes down or API fails, DON'T CRASH. Log it and retry.
                logger.error(f"An error occurred in the main loop: {e}")
                logger.info("Retrying in 60 seconds...")
                time.sleep(60)

        logger.info("Bot shut down gracefully.")

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()