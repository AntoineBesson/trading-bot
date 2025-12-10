from strategies.option_pairs import OptionPairsStrategy
from strategies.volatility_arb import VolatilityArbitrageStrategy

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
            'delta_threshold': 10.0,
            'profit_target': 0.50,
            'stop_loss_iv_mult': 1.5
        }
    }
