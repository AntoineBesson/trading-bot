import os
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv

# --- IMPORTANT ---
# This assumes you have your .env file in the root directory
# (one level up from 'src')
# If your .env file is in the SAME directory as this script, 
# you can just use load_dotenv()
# But for our repo structure, we do this:
load_dotenv(dotenv_path='../.env')

class DataHandler:
    """
    Handles all market data requests.
    This class is the "senses" of the bot.
    """
    def __init__(self, paper_trading=True):
        """
        Initializes the connection to the Alpaca API.
        """
        self.api_key = os.environ.get("APCA_API_KEY_ID")
        self.secret_key = os.environ.get("APCA_API_SECRET_KEY")
        
        if self.api_key is None or self.secret_key is None:
            raise EnvironmentError("API keys not found. Check your .env file.")
            
        if paper_trading:
            self.base_url = "https://paper-api.alpaca.markets"
        else:
            self.base_url = "https://api.alpaca.markets"
            
        self.api = tradeapi.REST(
            self.api_key,
            self.secret_key,
            self.base_url,
            api_version='v2'
        )
        print("Data Handler initialized.")

    def get_historical_bars(self, symbols, timeframe, start, end=None):
        """
        Fetches historical bar data for one or more symbols.
        
        :param symbols: A list of symbols (e.g., ['AAPL', 'GOOG'])
        :param timeframe: '1Min', '5Min', '15Min', '1H', '1D'
        :param start: Start date (e.g., '2020-01-01')
        :param end: End date (e.g., '2021-01-01')
        :return: A dictionary of pandas DataFrames, one for each symbol.
        """
        try:
            # Note: get_bars is deprecated, use get_bars_rest
            # Let's use the new SDK format:
            from alpaca_trade_api.rest import TimeFrame, GetBarsRequest
            
            # Convert string timeframe to SDK TimeFrame object
            tf_map = {
                '1Min': TimeFrame.Minute,
                '5Min': TimeFrame.FiveMinutes,
                '15Min': TimeFrame.FifteenMinutes,
                '1H': TimeFrame.Hour,
                '1D': TimeFrame.Day
            }
            if timeframe not in tf_map:
                raise ValueError(f"Unsupported timeframe: {timeframe}")
                
            request_params = GetBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=tf_map[timeframe],
                start=start,
                end=end
            )
            
            bar_data = self.api.get_bars(request_params)
            
            # Process data into a clean dictionary of DataFrames
            data_frames = {}
            for symbol in symbols:
                # Filter bars for the specific symbol
                data_frames[symbol] = bar_data.df[bar_data.df['symbol'] == symbol]
                
            return data_frames

        except Exception as e:
            print(f"Error fetching historical data: {e}")
            return None

    def get_latest_bar(self, symbol):
        """
        Fetches the single latest bar for a symbol.
        """
        try:
            bar = self.api.get_latest_bar(symbol)
            return bar
        except Exception as e:
            print(f"Error fetching latest bar for {symbol}: {e}")
            return None

    def get_latest_quote(self, symbol):
        """
        Fetches the latest Level 1 quote (bid/ask) for a symbol.
        """
        try:
            quote = self.api.get_latest_quote(symbol)
            return quote
        except Exception as e:
            print(f"Error fetching latest quote for {symbol}: {e}")
            return None