import time
import sys
import signal
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd

# --- Import your modules ---
# (We add 'src' to the path so this works no matter where you run it from)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_handler import DataHandler
from execution import ExecutionHandler
from strategies.pairs_trade import PairsTradeStrategy
from strategies.option_pairs import OptionPairsStrategy
from options.data_handler import OptionDataHandler
from options.multileg import MultiLegExecutionHelper
from universe_manager import UniverseManager

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

        # 3. Initialize Strategy Stack
        self.option_data_handler = OptionDataHandler(self.dh)
        self.multi_leg_helper = MultiLegExecutionHelper(self.eh)
        
        # 4. Initialize Universe Manager
        try:
            # This assumes your CSV has a column header named "symbol"
            self.universe = pd.read_csv("data/universe.csv")['symbol'].tolist()
            logger.info(f"Loaded {len(self.universe)} symbols from data/universe.csv")
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
        self.universe_manager = UniverseManager(
            data_handler=self.dh,
            universe=self.universe,
            lookback_days=180,
            p_value_threshold=0.05,
            z_score_threshold=1.5
        )
        
        logger.info("Initializing strategies...")
        self.strategies = []
        self.rebalance_strategies() # Initial scan and build
        
        # 5. Register Signal Handlers (for graceful shutdown)
        signal.signal(signal.SIGINT, self.handle_exit_signal)
        signal.signal(signal.SIGTERM, self.handle_exit_signal)

    def rebalance_strategies(self):
        """Scans the universe and rebuilds the strategy list."""
        logger.info("Rebalancing strategies based on universe scan...")
        
        # 1. Scan for pairs
        watchlist = self.universe_manager.scan()
        
        # 2. Build Strategies from Watchlist
        new_strategies = []
        for item in watchlist:
            sym_a = item['symbol_a']
            sym_b = item['symbol_b']
            # hedge_ratio = item['hedge_ratio'] # Used for equity pairs, option strategy calculates its own
            
            logger.info(f"Adding strategy for pair: {sym_a}/{sym_b}")
            
            # Add Option Pairs Strategy
            new_strategies.append(
                OptionPairsStrategy(
                    data_handler=self.dh,
                    execution_handler=self.eh,
                    symbol_a=sym_a,
                    symbol_b=sym_b,
                    option_type="call", # Default to calls
                    target_delta=0.45,
                    days_to_expiry=30,
                    entry_threshold=2.0, # Enter when Z-score hits 2.0 (as requested)
                    exit_threshold=0.0,
                    contracts=1,
                    auto_execute=True,
                    option_data_handler=self.option_data_handler,
                    multi_leg_execution=self.multi_leg_helper,
                )
            )
            
        self.strategies = new_strategies
        logger.info(
            "Active strategies: %s",
            ", ".join(getattr(s, "name", s.__class__.__name__) + f"({s.symbol_a}/{s.symbol_b})" for s in self.strategies),
        )

    def handle_exit_signal(self, signum, frame):
        """Handles Ctrl+C or kill signals to stop the bot gracefully."""
        logger.info("Shutdown signal received. Finishing current iteration...")
        self.keep_running = False

    def run(self):
        """The main infinite loop."""
        logger.info("Bot started. Running 24/7 loop...")
        
        last_scan = time.time()
        
        while self.keep_running:
            try:
                # --- 0. Periodic Universe Scan ---
                if time.time() - last_scan > SCAN_INTERVAL:
                    logger.info("Scheduled universe scan triggered.")
                    self.rebalance_strategies()
                    last_scan = time.time()

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