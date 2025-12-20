import csv
import os

def generate_macro_universe_file(filepath="src/data/lead_lag_universe.csv"):
    """
    Generates a CSV file mapping Leaders (S&P 500 / Sectors) to Laggards (Russell 2000 / Small Cap Sectors).
    
    The most efficient way to map "All Stocks" for a Macro strategy is NOT to map 
    individual stock-to-stock (which is noisy), but to map:
    1. Broad Market Indices (SPY -> IWM)
    2. Sector Leaders (SPDR ETFs) -> Sector Laggards (Invesco S&P SmallCap ETFs)
    3. Key Mega-Cap Drivers -> Related Small Cap Baskets
    """
    
    # Define the high-confidence mappings
    # Leader (Large Cap/Sector) -> Laggard (Small Cap/Target)
    universe_map = [
        # --- Broad Market ---
        ("SPY", "IWM", "Broad Market"), # S&P 500 -> Russell 2000
        
        # --- Sector ETFs (The most robust way to trade "All Stocks") ---
        # Technology
        ("XLK", "PSCT", "Technology"), # Tech Select Sector -> SmallCap Info Tech
        # Financials
        ("XLF", "PSCF", "Financials"), # Financial Select Sector -> SmallCap Financials
        # Energy
        ("XLE", "PSCE", "Energy"),     # Energy Select Sector -> SmallCap Energy
        # Healthcare
        ("XLV", "PSCH", "Healthcare"), # Health Care Select Sector -> SmallCap Health Care
        # Industrials
        ("XLI", "PSCI", "Industrials"),# Industrial Select Sector -> SmallCap Industrials
        # Materials
        ("XLB", "PSCM", "Materials"),  # Materials Select Sector -> SmallCap Materials
        # Utilities
        ("XLU", "PSCU", "Utilities"),  # Utilities Select Sector -> SmallCap Utilities
        # Consumer Discretionary
        ("XLY", "PSCD", "Discretionary"), # Consumer Disc. -> SmallCap Cons. Disc.
        # Consumer Staples
        ("XLP", "PSCC", "Staples"),    # Consumer Staples -> SmallCap Cons. Staples
        # Real Estate
        ("XLRE", "PSR", "Real Estate"), # Real Estate Select -> Active REIT ETF
        
        # --- Mega-Cap Drivers (Specific Thematic Flows) ---
        # Banks
        ("JPM", "KRE", "Banking"),     # JPMorgan -> Regional Banking ETF
        # Semiconductors
        ("NVDA", "SOXQ", "Semis"),     # Nvidia -> PHLX Semi ETF (or SOXL)
        # Oil
        ("XOM", "XOP", "Oil & Gas"),   # Exxon -> Oil & Gas Exp. & Prod.
        # Homebuilders
        ("ITB", "XHB", "Housing"),     # Home Construction -> Homebuilders (Lead-Lag often flips here)
        # Retail
        ("XRT", "RTH", "Retail"),      # Retail ETF -> Retail Holders
    ]
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Leader", "Laggard", "Sector"])
        writer.writerows(universe_map)
        
    print(f"Successfully generated macro universe with {len(universe_map)} pairs at {filepath}")

def load_macro_universe(filepath="src/data/lead_lag_universe.csv"):
    """
    Helper to load the map into a dictionary.
    """
    mapping = {}
    if not os.path.exists(filepath):
        return mapping
        
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping[row['Leader']] = row['Laggard']
    return mapping

if __name__ == "__main__":
    generate_macro_universe_file()
