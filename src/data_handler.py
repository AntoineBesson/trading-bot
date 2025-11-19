import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
# --- Imports for the NEW 'alpaca-py' library ---
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

# Load .env file (assuming it's in the root, one level up)
env_path = Path(__file__).resolve().parents[1] / ".env"
if not load_dotenv(env_path):
    # Fallback to default search so users running outside the repo root still load secrets
    load_dotenv()


class DataHandler:
    """
    Handles all market data requests using the NEW 'alpaca-py' library.
    """
    def __init__(self, paper_trading=True):
        """
        Initializes the connection to the Alpaca API.
        """
        self.api_key = os.environ.get("APCA_API_KEY_ID")
        self.secret_key = os.environ.get("APCA_API_SECRET_KEY")
        
        if self.api_key is None or self.secret_key is None:
            raise EnvironmentError("API keys not found. Check your .env file.")
            
        # The new library doesn't use 'paper_trading' in the client constructor
        # It's handled by the keys you use (paper keys vs. live keys)
        # We'll use the 'paper=True' flag in the TradingClient (in ExecutionHandler)
        # For data, it doesn't matter.
        self.client = StockHistoricalDataClient(
            self.api_key,
            self.secret_key
        )
        print("Data Handler (alpaca-py) initialized.")

    def get_historical_bars(self, symbols, timeframe_str, start, end=None):
        """
        Fetches historical bar data for one or more symbols.
        
        :param symbols: A list of symbols (e.g., ['AAPL', 'GOOG'])
        :param timeframe_str: '1Min', '5Min', '15Min', '1H', '1D'
        :param start: Start date (e.g., '2020-01-01')
        :param end: End date (e.g., '2021-01-01')
        :return: A dictionary of pandas DataFrames, one for each symbol.
        """
        
        # --- 1. Robust TimeFrame Mapping (This is correct) ---
        tf_map = {
            '1Min': TimeFrame.Minute,
            '5Min': TimeFrame(5, TimeFrameUnit.Minute),
            '15Min': TimeFrame(15, TimeFrameUnit.Minute),
            '1H': TimeFrame.Hour,
            '1D': TimeFrame.Day
        }
        if timeframe_str not in tf_map:
            raise ValueError(f"Unsupported timeframe: {timeframe_str}")
        
        timeframe = tf_map[timeframe_str]

        # --- 2. Robust Date Parsing (This is correct) ---
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end) if end else None
        except Exception as e:
            print(f"Error parsing date strings: {e}. Please use YYYY-MM-DD format.")
            return None

        try:
            # Build the request (This is correct)
            request_params = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=timeframe,
                start=start_dt,
                end=end_dt
            )
            
            print("Submitting data request to Alpaca...")
            bar_data = self.client.get_stock_bars(request_params)
            
            if not bar_data:
                print("---!!! Alpaca returned an empty data set. !!!---")
                return {}

            # --- 3. NEW AND CORRECT DATA PARSING ---
            
            # bar_data.df has a MultiIndex: (symbol, timestamp)
            # We will group by the first level ('symbol') and create a dict
            
            final_data = {}
            
            # Check if we got any data at all
            if bar_data.df.empty:
                print("BarSet was returned, but its DataFrame is empty.")
                return {}

            # Group by the first index level, which is 'symbol'
            grouped_by_symbol = bar_data.df.groupby(level=0)
            
            for symbol, symbol_df in grouped_by_symbol:
                # symbol_df still has the MultiIndex. 
                # We'll drop the 'symbol' part of the index to make it a clean DataFrame.
                final_data[symbol] = symbol_df.reset_index(level=0, drop=True)
            
            return final_data
            # --- END OF NEW PARSING ---

        except Exception as e:
            print(f"---!!! AN ERROR OCCURRED during data fetch !!!---")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    def get_latest_bar(self, symbol):
        """
        Fetches the single latest bar for a symbol.
        Note: This is less efficient, use get_historical_bars if possible.
        """
        try:
            # We must use the StockHistoricalDataClient for this
            # (No direct 'get_latest_bar' in alpaca-py)
            request_params = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Minute,  # Get the finest grain
                start=datetime.now(timezone.utc) - timedelta(days=2),
                limit=1  # Get only the last one
            )
            bars = self.client.get_stock_bars(request_params)
            latest_bar = self._extract_latest_from_bars(bars, symbol)
            if latest_bar:
                return latest_bar

            print(f"Falling back to daily close for {symbol}.")
            fallback = self._latest_daily_close(symbol)
            if fallback:
                return fallback
            print(f"No latest bar data returned for {symbol}.")
            return None

        except Exception as e:
            print(f"Error fetching latest bar for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_latest_from_bars(self, bars, symbol):
        if bars is None or getattr(bars, "df", pd.DataFrame()).empty:
            return None
        try:
            symbol_df = bars.df.xs(symbol)
        except KeyError:
            return None
        if symbol_df.empty:
            return None
        symbol_df = symbol_df.sort_index()
        latest_row = symbol_df.iloc[-1]
        latest_dict = latest_row.to_dict()
        latest_dict.setdefault("symbol", symbol)
        latest_dict["timestamp"] = symbol_df.index[-1].isoformat()
        return latest_dict

    def _latest_daily_close(self, symbol):
        start = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
        history = self.get_historical_bars([symbol], "1D", start)
        if not history:
            return None
        df = history.get(symbol)
        if df is None or df.empty:
            return None
        last_row = df.iloc[-1]
        ts = df.index[-1]
        timestamp = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        payload = last_row.to_dict()
        payload.setdefault("symbol", symbol)
        payload.setdefault("close", float(payload.get("close", payload.get("c", 0.0))))
        payload["timestamp"] = timestamp
        return payload

    # Note: Latest quote is handled by the TradingClient, not Data client.
    # We'll add this to ExecutionHandler or a new "QuoteHandler" later
    # if you need real-time streaming.