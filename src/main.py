import logging
import os
import signal
import sys
import time
from datetime import datetime, time as dtime

import pandas as pd
import pytz
from dotenv import load_dotenv

from src.data_handler import DataHandler
from src.execution import ExecutionHandler
from src.options.data_handler import OptionDataHandler
from src.options.multileg import MultiLegExecutionHelper
from src.portfolio_manager import PortfolioManager
from src.strategy_manager import StrategyManager
from src.strategies.pairs_trade import PairsTradeStrategy
from src.strategies.option_pairs import OptionPairsStrategy
from src.strategies.volatility_arb import VolatilityArbitrageStrategy
from src.strategies_config import (
    create_macro_arbitrage_config,
    create_option_pair_config,
    create_sector_momentum_config,
    create_volatility_arb_config,
)
from src.universe_manager import UniverseManager

# --- Configuration ---
# How often the bot checks for signals (in seconds)
SLEEP_DELAY = 60 
# How often to rescan the universe (in seconds) - e.g., every 24 hours
SCAN_INTERVAL = 24 * 60 * 60 

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

        # 3. Initialize Managers (The New Architecture)
        self.pm = PortfolioManager(self.dh)
        self.sm = StrategyManager(self.dh, self.eh, self.pm)
        
        # 4. Initialize Helpers
        self.option_data_handler = OptionDataHandler(self.dh)
        self.multi_leg_helper = MultiLegExecutionHelper(self.eh)
        
        # 5. Initialize Universe Manager
        try:
            # This assumes your CSV has a column header named "symbol"
            # Use absolute path to ensure it works regardless of CWD
            universe_path = os.path.join(os.path.dirname(__file__), "data", "universe.csv")
            self.universe = pd.read_csv(universe_path)['symbol'].tolist()
            logger.info(f"Loaded {len(self.universe)} symbols from {universe_path}")
        except Exception as e:
            logger.warning(f"Could not load universe.csv ({e}). Using default S&P Financials list.")
            # Default universe (S&P 500 Financials subset or similar)
            self.universe = [
    'ZTS', 'ZBRA', 'ZBH', 'YUM', 'XYZ', 'XYL', 'XOM', 'XEL', 'WYNN', 'WY', 
    'WTW', 'WST', 'WSM', 'WRB', 'WMT', 'WMB', 'WM', 'WFC', 'WELL', 'WEC', 
    'WDC', 'WDAY', 'WBD', 'WAT', 'WAB', 'VZ', 'VTRS', 'VTR', 'VST', 'VRTX', 
    'VRSN', 'VRSK', 'VMC', 'VLTO', 'VLO', 'VICI', 'V', 'USB', 'URI', 'UPS', 
    'UNP', 'UNH', 'ULTA', 'UHS', 'UDR', 'UBER', 'UAL', 'TYL', 'TXT', 'TXN', 
    'TTWO', 'TTD', 'TT', 'TSN', 'TSLA', 'TSCO', 'TRV', 'TROW', 'TRMB', 'TRGP', 
    'TPR', 'TPL', 'TMUS', 'TMO', 'TKO', 'TJX', 'TGT', 'TFC', 'TER', 'TEL', 
    'TECH', 'TDY', 'TDG', 'TAP', 'T', 'SYY', 'SYK', 'SYF', 'SWKS', 'SWK', 
    'SW', 'STZ', 'STX', 'STT', 'STLD', 'STE', 'SRE', 'SPGI', 'SPG', 'SOLV', 
    'SOLS', 'SO', 'SNPS', 'SNA', 'SMCI', 'SLB', 'SJM', 'SHW', 'SCHW', 'SBUX', 
    'SBAC', 'RVTY', 'RTX', 'RSG', 'ROST', 'ROP', 'ROL', 'ROK', 'RMD', 'RL', 
    'RJF', 'RF', 'REGN', 'REG', 'RCL', 'QCOM', 'QQ', 'PYPL', 'PWR', 'PTC', 
    'PSX', 'PSKY', 'PSA', 'PRU', 'PPL', 'PPG', 'POOL', 'PODD', 'PNW', 'PNR', 
    'PNC', 'PM', 'PLTR', 'PLD', 'PKG', 'PHM', 'PH', 'PGR', 'PG', 'PFG', 
    'PFE', 'PEP', 'PEG', 'PCG', 'PCAR', 'PAYX', 'PAYC', 'PANW', 'OXY', 'OTIS', 
    'ORLY', 'ORCL', 'ON', 'OMC', 'OKE', 'ODFL', 'O', 'NXP', 'NWSA', 'NWS', 
    'NVR', 'NVDA', 'NUE', 'NTRS', 'NTAP', 'NSC', 'NRG', 'NOW', 'NOC', 'NKE', 
    'NI', 'NFLX', 'NEM', 'NEE', 'NDSN', 'NDAQ', 'NCLH', 'MU', 'MTD', 'MTCH', 
    'MTB', 'MSI', 'MSFT', 'MSCI', 'MS', 'MRNA', 'MRK', 'MPWR', 'MPC', 'MOS', 
    'MOH', 'MO', 'MNST', 'MMM', 'MMC', 'MLM', 'MKC', 'MHK', 'MGM', 'META', 
    'MET', 'MDT', 'MDLZ', 'MCO', 'MCK', 'MCHP', 'MCD', 'MAS', 'MAR', 'MAA', 
    'MA', 'LYV', 'LYB', 'LW', 'LVS', 'LUV', 'LULU', 'LRCX', 'LOW', 'LNT', 
    'LMT', 'LLY', 'LKQ', 'LIN', 'LII', 'LHX', 'LH', 'LEN', 'LDOS', 'L', 
    'KVUE', 'KR', 'KO', 'KMI', 'KMB', 'KLAC', 'KKR', 'KIM', 'KHC', 'KEYS', 
    'KEY', 'KDP', 'K', 'JPM', 'JNJ', 'JKHY', 'JCI', 'JBL', 'JBHT', 'J', 
    'IVZ', 'ITW', 'IT', 'ISRG', 'IRM', 'IR', 'IQV', 'IPG', 'IP', 'INVH', 
    'INTU', 'INTC', 'INCY', 'IFF', 'IEX', 'IDXX', 'ICE', 'IBM', 'IBKR', 
    'HWM', 'HUM', 'HUBB', 'HSY', 'HST', 'HSIC', 'HRL', 'HPQ', 'HPE', 'HOOD', 
    'HON', 'HOLX', 'HLT', 'HII', 'HIG', 'HD', 'HCA', 'HBAN', 'HAS', 'HAL', 
    'GWW', 'GS', 'GRMN', 'GPN', 'GPC', 'GOOGL', 'GOOG', 'GNRC', 'GM', 'GLW', 
    'GL', 'GIS', 'GILD', 'GEV', 'GEN', 'GEHC', 'GE', 'GDDY', 'GD', 'FTV', 
    'FTNT', 'FSLR', 'FRT', 'FOXA', 'FOX', 'FITB', 'FISV', 'FIS', 'FICO', 
    'FFIV', 'FE', 'FDX', 'FDS', 'FCX', 'FAST', 'FANG', 'F', 'EXR', 'EXPE', 
    'EXPD', 'EXE', 'EXC', 'EW', 'EVRG', 'ETR', 'ETN', 'ESS', 'ES', 'ERIE', 
    'EQT', 'EQR', 'EQIX', 'EPAM', 'EOG', 'EMR', 'EME', 'ELV', 'EL', 'EIX', 
    'EG', 'EFX', 'ED', 'ECL', 'EBAY', 'EA', 'DXCM', 'DVN', 'DVA', 'DUK', 
    'DTE', 'DRI', 'DPZ', 'DOW', 'DOV', 'DOC', 'DLTR', 'DLR', 'DIS', 'DHR', 
    'DHI', 'DGX', 'DG', 'DELL', 'DECK', 'DE', 'DDOG', 'DD', 'DAY', 'DASH', 
    'DAL', 'D', 'CVX', 'CVS', 'CTVA', 'CTSH', 'CTRA', 'CTAS', 'CSX', 'CSGP', 
    'CSCO', 'CRWD', 'CRM', 'CRL', 'CPT', 'CPRT', 'CPB', 'CPAY', 'COST', 
    'COR', 'COP', 'COO', 'COIN', 'COF', 'CNP', 'CNC', 'CMS', 'CMI', 'CMG', 
    'CME', 'CMCSA', 'CLX', 'CL', 'CINF', 'CI', 'CHTR', 'CHRW', 'CHD', 'CFG', 
    'CF', 'CEG', 'CDW', 'CDNS', 'CCL', 'CCI', 'CBRE', 'CBOE', 'CB', 'CAT', 
    'CARR', 'CAH', 'CAG', 'C', 'BXP', 'BX', 'BSX', 'BRO', 'BRK.B', 'BR', 
    'BMY', 'BLK', 'BLDR', 'BKR', 'BKNG', 'BK', 'BIIB', 'BG', 'BF.B', 'BEN', 
    'BDX', 'BBY', 'BAX', 'BALL', 'BAC', 'BA', 'AZO', 'AXP', 'AXON', 'AWK', 
    'AVY', 'AVGO', 'AVB', 'ATO', 'ARE', 'APTV', 'APP', 'APO', 'APH', 'APD', 
    'APA', 'AOS', 'AON', 'ANET', 'AMZN', 'AMT', 'AMP', 'AMGN', 'AME', 'AMD', 
    'AMCR', 'AMAT', 'ALLE', 'ALL', 'ALGN', 'ALB', 'AKAM', 'AJG', 'AIZ', 
    'AIG', 'AFL', 'AES', 'AEP', 'AEE', 'ADSK', 'ADP', 'ADM', 'ADI', 'ADBE', 
    'ACN', 'ACGL', 'ABT', 'ABNB', 'ABBV', 'AAPL', 'A'
]
            print(self.universe)
        self.universe_manager = UniverseManager(
            data_handler=self.dh,
            universe=self.universe,
            lookback_days=180,
            p_value_threshold=0.05,
            z_score_threshold=1.5
        )
        
        # 6. Initial Strategy Setup
        self.rebalance_strategies()

        # 7. Reconcile State (Find existing trades)
        self.sm.reconcile_positions()

        # 8. Signal Handling
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def rebalance_strategies(self):
        """
        Scans the universe and spawns/kills strategies based on opportunities.
        This is the 'Brain' of the operation.
        """
        logger.info("Rebalancing strategies...")
        
        # --- 1. Macro Arbitrage (Production) ---
        # This is a persistent strategy that manages its own universe internally.
        # We only need to spawn it once.
        macro_id = "MacroArb_Production"
        if macro_id not in self.sm.strategies:
            logger.info(f"Spawning {macro_id}...")
            config = create_macro_arbitrage_config(allocation=20000.0)
            self.sm.spawn_strategy(config)
        
        # --- 2. Sector Momentum (Monthly) ---
        # This is a persistent strategy that rebalances itself monthly.
        # We only need to spawn it once.
        sector_mom_id = "SectorMomentum_Monthly"
        if sector_mom_id not in self.sm.strategies:
            logger.info(f"Spawning {sector_mom_id}...")
            config = create_sector_momentum_config(allocation=30000.0)
            self.sm.spawn_strategy(config)

        # --- 3. Volatility Arbitrage (Scanner) ---
        # Scan for high IV opportunities
        # (Simplified logic: Pick 1 random symbol for demo)
        # In reality, you'd scan self.universe for IV Rank > 50
        target_symbol = "SPY" 
        vol_arb_id = f"VolArb_{target_symbol}"
        
        if vol_arb_id not in self.sm.strategies:
             logger.info(f"Spawning {vol_arb_id}...")
             config = create_volatility_arb_config(target_symbol, allocation=10000.0)
             self.sm.spawn_strategy(config)
             
        # --- 4. Option Pairs (Scanner) ---
        # Scan for cointegrated pairs suitable for options
        # (Simplified logic: Pick 1 pair for demo)
        pair_a, pair_b = "GLD", "SLV"
        opt_pair_id = f"OptionPair_{pair_a}_{pair_b}"
        
        if opt_pair_id not in self.sm.strategies:
            logger.info(f"Spawning {opt_pair_id}...")
            # Inject the specialized handlers into the config parameters
            config = create_option_pair_config(pair_a, pair_b, allocation=5000.0)
            config['parameters']['option_data_handler'] = self.option_data_handler
            config['parameters']['multi_leg_execution'] = self.multi_leg_helper
            
            self.sm.spawn_strategy(config)

        # 3. Update Strategy Manager
        self.sm.update_strategies(strategy_configs)

    def is_market_open(self):
        """Checks if the US market is currently open (9:30 AM - 4:00 PM ET, Mon-Fri)."""
        tz = pytz.timezone('US/Eastern')
        now = datetime.now(tz)
        
        # Check for weekend (Saturday=5, Sunday=6)
        if now.weekday() >= 5:
            return False

        # Check time (09:30 - 16:00)
        market_open = dtime(9, 30)
        market_close = dtime(16, 0)
        current_time = now.time()

        return market_open <= current_time <= market_close

    def signal_handler(self, signum, frame):
        """Handles Ctrl+C or kill signals to stop the bot gracefully."""
        logger.info("Shutdown signal received. Finishing current iteration...")
        self.keep_running = False
        self.sm.kill_all() # Optional: Close positions on exit

    def run(self):
        """The main infinite loop."""
        logger.info("Bot started. Running 24/7 loop...")
        
        last_scan = time.time()
        
        while self.keep_running:
            try:
                # --- 0. Market Hours Check ---
                if not self.is_market_open():
                    logger.info("Market is closed. Sleeping for 5 minutes...")
                    time.sleep(300) # Sleep 5 minutes
                    continue
                
                logger.info("Starting new tick...")

                # --- 1. Periodic Universe Scan ---
                if time.time() - last_scan > SCAN_INTERVAL:
                    logger.info("Scheduled universe scan triggered.")
                    self.rebalance_strategies()
                    last_scan = time.time()

                # --- 2. Run Strategies ---
                self.sm.run_tick()

                # --- 3. Sleep ---
                # Wait for the next check (e.g., 1 minute)
                logger.info(f"Tick complete. Sleeping for {SLEEP_DELAY} seconds...")
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