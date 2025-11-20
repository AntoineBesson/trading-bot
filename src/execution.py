import os
from dotenv import load_dotenv

# --- Imports for the NEW 'alpaca-py' library ---
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    ClosePositionRequest
)
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce

# Load .env file (assuming it's in the root, one level up)
load_dotenv(dotenv_path='../.env')

class ExecutionHandler:
    """
    Handles all order execution logic using the NEW 'alpaca-py' library.
    This class is the "hands" of the bot.
    """
    def __init__(self, paper_trading=True):
        """
        Initializes the connection to the Alpaca API.
        """
        self.api_key = os.environ.get("APCA_API_KEY_ID")
        self.secret_key = os.environ.get("APCA_API_SECRET_KEY")
        
        if self.api_key is None or self.secret_key is None:
            raise EnvironmentError("API keys not found. Check your .env file.")

        # The new client takes 'paper' as a direct boolean argument
        self.api = TradingClient(
            self.api_key,
            self.secret_key,
            paper=paper_trading
        )
        print("Execution Handler (alpaca-py) initialized.")

    def get_all_positions(self):
        """
        Retrieves all open positions from the broker.
        """
        try:
            return self.api.get_all_positions()
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []

    def close_position(self, symbol):
        """
        Closes a position for a specific symbol.
        """
        try:
            self.api.close_position(symbol_or_asset_id=symbol)
            print(f"Closed position for {symbol}")
        except Exception as e:
            print(f"Error closing position for {symbol}: {e}")

    def execute_order(self, signal):
        """
        Places an order with the broker based on a signal.
        
        :param signal: A dictionary containing order details.
                       e.g., {
                           'symbol': 'AAPL',
                           'action': 'buy',  # 'buy' or 'sell'
                           'qty': 10,
                           'type': 'market', # 'market', 'limit'
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

        # --- Convert signal strings to API Enums ---
        try:
            side = OrderSide[signal['action'].upper()]
            order_type = OrderType[signal['type'].upper()]
            tif = TimeInForce[signal['time_in_force'].upper()]
        except KeyError as e:
            print(f"Invalid signal parameter: {e}. Check action/type/time_in_force.")
            return None
            
        # --- Build Order Request ---
        try:
            order_request = None
            if order_type == OrderType.MARKET:
                order_request = MarketOrderRequest(
                    symbol=signal['symbol'],
                    qty=signal['qty'],
                    side=side,
                    time_in_force=tif
                )
            elif order_type == OrderType.LIMIT:
                if 'limit_price' not in signal:
                    print("Limit order signal is missing 'limit_price'.")
                    return None
                order_request = LimitOrderRequest(
                    symbol=signal['symbol'],
                    qty=signal['qty'],
                    side=side,
                    time_in_force=tif,
                    limit_price=signal['limit_price']
                )
            # You can add more order types (stop, stop_limit) here
            
            if order_request is None:
                print(f"Unsupported order type: {signal['type']}")
                return None

            # --- Submit Order ---
            order = self.api.submit_order(order_request)
            
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
            positions = self.api.get_all_positions()
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
            # This request closes the position with a market order
            request = ClosePositionRequest(symbol=symbol)
            position = self.api.close_position(request)
            
            print(f"Position closed: {position.symbol}")
            return position
        except Exception as e:
            print(f"Error closing position for {symbol}: {e}")
            return None