from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    """
    An abstract base class for all trading strategies.
    
    It defines the common interface (methods) that every strategy
    must implement. This ensures the main bot can interact with
    any strategy in a standardized way.
    """
    
    def __init__(self, data_handler, execution_handler, symbols):
        """
        Initializes the base strategy.
        
        :param data_handler: An instance of DataHandler (for getting data).
        :param execution_handler: An instance of ExecutionHandler (for placing trades).
        :param symbols: A list of symbols the strategy will trade.
        """
        self.data_handler = data_handler
        self.execution_handler = execution_handler
        self.symbols = symbols
        self.name = "BaseStrategy"
        
        print(f"{self.name} initialized with symbols: {self.symbols}")

    @abstractmethod
    def generate_signal(self):
        """
        The core logic of the strategy.
        
        This method will be called by the main bot loop. It should:
        1. Get the latest data using self.data_handler.
        2. Perform calculations (e.g., check for mean reversion, HMM state).
        3. If a trading opportunity exists, return a signal dictionary.
        
        :return: A signal dictionary (e.g., {'symbol': 'AAPL', 'action': 'buy', ...})
                 or None if no action is to be taken.
        """
        raise NotImplementedError("Should implement generate_signal()")

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