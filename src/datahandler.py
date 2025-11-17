import os
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv

# Load .env file (assuming it's in the root, one level up)
load_dotenv(dotenv_path='../.env')

class ExecutionHandler:
    """
    Handles all order execution logic.
    This class is the "hands" of the bot.
    """
    def __init__(self, paper_trading=True):
        """
        Initializes the connection to the Alpaca API.
        """
        self.api_key = os.environ.get("APCA_API_KEY_ID")
        self.secret_key = os.environ.get("APCA_API_SECRET_KEY")
        
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
        print("Execution Handler initialized.")

    def execute_order(self, signal):
        """
        Places an order with the broker.
        
        :param signal: A dictionary containing order details.
                       e.g., {
                           'symbol': 'AAPL',
                           'action': 'buy',  # 'buy' or 'sell'
                           'qty': 10,
                           'type': 'market', # 'market', 'limit', etc.
                           'time_in_force': 'gtc' # 'gtc', 'day'
                           # 'limit_price': 150.00 (if type is 'limit')
                       }
        :return: The order object from the API, or None if failed.
        """
        print(f"Attempting to execute order: {signal}")
        
        # --- Input Validation ---
        if signal is None:
            print("No signal provided. Skipping execution.")
            return None
            
        required_keys = ['symbol', 'action', 'qty', 'type', 'time_in_force']
        if not all(key in signal for key in required_keys):
            print(f"Signal is missing required keys. Signal: {signal}")
            return None
            
        try:
            order = self.api.submit_order(
                symbol=signal['symbol'],
                qty=signal['qty'],
                side=signal['action'],
                type=signal['type'],
                time_in_force=signal['time_in_force'],
                limit_price=signal.get('limit_price', None), # Safely get limit_price
                stop_price=signal.get('stop_price', None)    # Safely get stop_price
            )
            
            print(f"Order submitted successfully: {order.id}")
            return order

        except Exception as e:
            print(f"Error submitting order: {e}")
            return None

    def get_all_positions(self):
        """
        Fetches a list of all open positions.
        """
        try:
            positions = self.api.list_positions()
            return positions
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []

    def close_position(self, symbol):
        """
        Closes the entire open position for a given symbol.
        """
        print(f"Attempting to close position for: {symbol}")
        try:
            position = self.api.close_position(symbol)
            print(f"Position closed: {position.symbol}")
            return position
        except Exception as e:
            print(f"Error closing position for {symbol}: {e}")
            return None