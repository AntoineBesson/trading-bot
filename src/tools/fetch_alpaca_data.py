import os
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables (API Keys)
load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    raise ValueError("Error: ALPACA_API_KEY or ALPACA_SECRET_KEY not found in .env file")

def fetch_alpaca_history(symbol, timeframe, days_back, filename):
    """
    Fetches historical bars from Alpaca and saves to CSV.
    """
    print(f"Connecting to Alpaca to fetch {symbol}...")
    
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    # Calculate start date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # Map string timeframe to Alpaca TimeFrame object
    tf_map = {
        "1Min": TimeFrame.Minute,
        "1Hour": TimeFrame.Hour,
        "1Day": TimeFrame.Day
    }
    
    if timeframe not in tf_map:
        raise ValueError("Invalid timeframe. Use '1Min', '1Hour', or '1Day'")

    request_params = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=tf_map[timeframe],
        start=start_date,
        end=end_date,
        adjustment='all' # Adjust for splits/dividends
    )

    try:
        bars = client.get_stock_bars(request_params)
        
        # Convert to DataFrame
        df = bars.df
        
        # Alpaca returns a MultiIndex (symbol, timestamp). We just want timestamp as index.
        df = df.reset_index(level=0, drop=True)
        
        # Rename columns to match what PermutationTester expects (lowercase)
        # Alpaca returns: Open, High, Low, Close, Volume, TradeCount, VWAP
        df.columns = [c.lower() for c in df.columns]
        
        # Ensure directory exists
        os.makedirs('data', exist_ok=True)
        
        # Save
        path = f"data/{filename}"
        df.to_csv(path)
        
        print(f"✅ Success! Downloaded {len(df)} bars.")
        print(f"   Saved to: {path}")
        print(f"   Range: {df.index[0]} to {df.index[-1]}")
        
    except Exception as e:
        print(f"❌ Error fetching data: {e}")

if __name__ == "__main__":
    # --- CONFIGURATION ---
    SYMBOL = "SPY"
    TIMEFRAME = "1Hour"  # Options: 1Min, 1Hour, 1Day
    DAYS_BACK = 730      # How far back to go
    FILENAME = "SPY_1H_ALPACA.csv"
    
    fetch_alpaca_history(SYMBOL, TIMEFRAME, DAYS_BACK, FILENAME)