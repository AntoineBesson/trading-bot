import sys
import os
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from data_handler import DataHandler
from sampling.dollar_bars import get_dollar_bars

def main():
    try:
        dh = DataHandler()
    except Exception as e:
        print(f"Failed to init DataHandler: {e}")
        return

    symbol = "SPY"
    
    # Get last 2 days to ensure we have data (markets closed on weekends)
    # Just grab a chunk.
    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    
    print(f"Fetching trades for {symbol} from {start_date}...")
    # Getting 10,000 trades
    trades_dict = dh.get_historical_trades([symbol], start=start_date, limit=10000)
    
    if not trades_dict or symbol not in trades_dict:
        print("No trades found. Ensure .env has keys and market is open/recorded.")
        return

    trades_df = trades_dict[symbol]
    print(f"Raw trades rows: {len(trades_df)}")
    print("First few trades:")
    print(trades_df[['t', 'p', 's']].head() if 't' in trades_df.columns else trades_df.head())
    
    # Adjust threshold based on what we see. 
    # SPY is expensive, so volume grows fast.
    threshold = 5_000_000 # $5M per bar
    
    print(f"\nCalculating Dollar Bars (threshold=${threshold:,.0f})...") 
    
    dollar_bars = get_dollar_bars(trades_df, threshold=threshold)
    
    print(f"Generated {len(dollar_bars)} dollar bars.")
    if not dollar_bars.empty:
        print(dollar_bars.head())
        print("\nLatest bars:")
        print(dollar_bars.tail())
    else:
        print("No bars generated. Try lowering the threshold or fetching more data.")

if __name__ == "__main__":
    main()
