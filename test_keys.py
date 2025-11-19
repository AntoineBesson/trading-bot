import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient


print("Testing Alpaca API keys...")

# Load keys from .env file
load_dotenv()

API_KEY = os.environ.get("APCA_API_KEY_ID")
SECRET_KEY = os.environ.get("APCA_API_SECRET_KEY")

if API_KEY is None or SECRET_KEY is None:
    print("Error: API keys not found in .env file.")
else:
    try:
        # Use paper=True for paper trading keys
        trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
        
        # Make a simple request to get account details
        account = trading_client.get_account()
        
        # If this works, your keys are correct and active
        print("\n--- SUCCESS! ---")
        print(f"Connected to account: {account.account_number}")
        print(f"Status: {account.status}")
        print(f"Portfolio Value: {account.portfolio_value}")
        
    except Exception as e:
        print("\n---!!! ERROR CONNECTING !!!---")
        print("There was a problem with your keys or connection:")
        print(e)