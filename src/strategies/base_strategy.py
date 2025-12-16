from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseStrategy(ABC):
    """
    An abstract base class for all trading strategies.
    
    It defines the common interface (methods) that every strategy
    must implement. This ensures the main bot can interact with
    any strategy in a standardized way.
    """
    
    def __init__(self, data_handler, execution_handler, portfolio_manager, strategy_id: str, symbols: list):
        """
        Initializes the base strategy.
        
        :param data_handler: An instance of DataHandler (for getting data).
        :param execution_handler: An instance of ExecutionHandler (for placing trades).
        :param portfolio_manager: An instance of PortfolioManager (for budget checks).
        :param strategy_id: Unique identifier for this strategy instance.
        :param symbols: A list of symbols the strategy will trade.
        """
        self.data_handler = data_handler
        self.execution_handler = execution_handler
        self.portfolio_manager = portfolio_manager
        self.strategy_id = strategy_id
        self.symbols = symbols
        self.name = strategy_id
        self.active = True
        
        logger.info(f"Strategy {self.strategy_id} initialized with symbols: {self.symbols}")

    @abstractmethod
    def generate_signal(self):
        """
        The core logic of the strategy.
        """
        raise NotImplementedError("Should implement generate_signal()")

    def reconcile(self, positions_map):
        """
        The 'Sherlock Holmes' Logic.
        Reconstructs the strategy's state from the broker's open positions.
        
        :param positions_map: A dictionary of {symbol: PositionObject} for all open positions.
        """
        logger.info(f"[{self.strategy_id}] Reconciling state...")
        # Default implementation for simple strategies (trading the symbols directly)
        strategy_positions = [p for sym, p in positions_map.items() if sym in self.symbols]
        
        if not strategy_positions:
            self.position = "flat"
            logger.info(f"[{self.strategy_id}] No positions found. State set to FLAT.")
        else:
            self.position = "invested"
            logger.info(f"[{self.strategy_id}] Found {len(strategy_positions)} positions. State set to INVESTED.")

    
    def kill_switch(self):
        """
        Emergency exit. Closes all positions associated with this strategy.
        """
        logger.warning(f"[{self.strategy_id}] KILL SWITCH ACTIVATED. Closing all positions.")
        # This is a generic implementation. Complex strategies (like options) 
        # might need to override this to close specific option contracts.
        for symbol in self.symbols:
            try:
                self.execution_handler.close_position(symbol)
            except Exception as e:
                logger.error(f"[{self.strategy_id}] Failed to close {symbol}: {e}")



    @abstractmethod
    def run_backtest(self, start_date, end_date, timeframe):
        """
        Runs a historical backtest of the strategy.
        
        This method should:
        1. Get historical data using self.data_handler.
        2. Simulate the generate_signal() logic over the historical data.
        3. Calculate and print performance metrics (e.g., P&L, Sharpe Ratio).
        
        :param start_date: e.g., '2020-01-01'
        :param end_date: e.g., '2023-01-01'
        :param timeframe: e.g., '1D'
        """
        raise NotImplementedError("Should implement run_backtest()")