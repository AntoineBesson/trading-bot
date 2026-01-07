from src.strategies.option_pairs import OptionPairsStrategy
from src.strategies.volatility_arb import VolatilityArbitrageStrategy
from src.strategies.macro_arbitrage import MacroArbitrageStrategy
from src.tools.build_macro_universe import load_macro_universe

# --- Universe Definitions ---
SECTOR_UNIVERSE = [
    'XLK', # Technology
    'XLF', # Financials
    'XLE', # Energy
    'XLV', # Healthcare
    'XLI', # Industrials
    'XLP', # Staples
    'XLY', # Discretionary
    'XLB', # Materials
    'XLU', # Utilities
    'XLC', # Communications
    'XLRE' # Real Estate
]

DEFENSIVE_ASSETS = ['SHV', 'BIL'] # Short-Term Treasuries

def create_option_pair_config(symbol_a, symbol_b, allocation=5000.0):
    """
    Generates a configuration dictionary for an Option Pair strategy.
    
    Args:
        symbol_a (str): The first symbol in the pair.
        symbol_b (str): The second symbol in the pair.
        allocation (float): The capital allocated to this strategy.
        
    Returns:
        dict: A configuration dictionary ready for the StrategyManager.
    """
    strategy_id = f"OptionPair_{symbol_a}_{symbol_b}"
    
    return {
        'id': strategy_id,
        'strategy_class': OptionPairsStrategy,
        'allocation': allocation,
        'parameters': {
            'symbol_a': symbol_a,
            'symbol_b': symbol_b,
            'option_type': "call",
            'target_delta': 0.45,
            'days_to_expiry': 30,
            'entry_threshold': 2.0,
            'exit_threshold': 0.0,
            'contracts': 1,
            'auto_execute': True,
            # Note: Handlers (option_data_handler, multi_leg_execution) 
            # are injected by the StrategyManager or Main, but here we define parameters.
            # Since StrategyManager.spawn_strategy passes **config['parameters'],
            # we need to ensure the objects that are NOT JSON-serializable (like handlers)
            # are passed in. 
            # 
            # In the current main.py implementation, we are passing the handlers in the config.
            # This function will be called in main.py where those handlers are available.
        }
    }


def create_volatility_arb_config(symbol, allocation=10000.0):
    """
    Generates a configuration dictionary for a Volatility Arbitrage strategy.
    
    Args:
        symbol (str): The symbol to trade.
        allocation (float): The capital allocated to this strategy.
        
    Returns:
        dict: A configuration dictionary ready for the StrategyManager.
    """
    strategy_id = f"VolArb_{symbol}"
    
    return {
        'id': strategy_id,
        'strategy_class': VolatilityArbitrageStrategy,
        'allocation': allocation,
        'parameters': {
            'symbol': symbol,
            'lookback_days': 30,
            'entry_threshold': 1.25,
            'delta_threshold': 25.0,
            'profit_target': 0.50,
            'stop_loss_iv_mult': 1.3,
            'contracts': 1,
            'initial_capital': allocation
        }
    }

def create_sector_momentum_config(allocation=30000.0):
    """
    Generates a configuration dictionary for the Sector Momentum strategy.
    """
    from src.strategies.sector_momentum import SectorMomentumStrategy
    
    strategy_id = "SectorMomentum_Monthly"
    
    return {
        'id': strategy_id,
        'strategy_class': SectorMomentumStrategy,
        'allocation': allocation,
        'parameters': {
            'universe': SECTOR_UNIVERSE,
            'safety_asset': 'SHV',
            'top_n': 3,
            'initial_capital': allocation
        }
    }

def create_macro_arbitrage_config(allocation=20000.0):
    """
    Generates a configuration dictionary for the Macro Arbitrage strategy.
    Uses the optimized 'Production Universe' (SPY-IWM, JPM-KRE, etc.).
    """
    strategy_id = "MacroArb_Production"
    
    # Load the specific production universe
    # We pass the filename to the loader, or we manually define it here if the loader is rigid.
    # Assuming load_macro_universe can take a path or we just define the dict here for safety.
    
    production_pairs = {
        'SPY': 'IWM',
        'JPM': 'KRE',
        'NVDA': 'SOXQ',
        'XOM': 'XOP'
    }
    
    return {
        'id': strategy_id,
        'strategy_class': MacroArbitrageStrategy,
        'allocation': allocation,
        'parameters': {
            'leader_laggard_map': production_pairs,
            'lookback_window_minutes': 15,   # Optimized
            'holding_period_minutes': 120,   # Optimized
            'z_threshold': 2.0,              # Optimized
            'laggard_threshold_pct': 0.005,
            'auto_calibrate': False          # Use fixed optimized params
        }
    }
