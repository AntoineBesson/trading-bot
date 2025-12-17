import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class PortfolioManager:
    """
    The CFO: Controls capital allocation and risk limits per strategy.
    """
    def __init__(self, data_handler):
        self.dh = data_handler
        # Dictionary to track allocation per strategy ID
        try:
            # We access the API through the DataHandler
            account = self.dh.api.get_account()
            self.current_capital = float(account.equity)
            logger.info(f"PortfolioManager initialized. Net Equity: ${self.current_capital}")
        except Exception as e:
            logger.warning(f"Could not fetch initial equity from Alpaca: {e}. Defaulting to $100k.")
            self.current_capital = 100000.0 # Fallback if API fails
        self.allocations: Dict[str, float] = {}

    def get_total_equity(self):
        """
        Returns the LIVE total value of the portfolio (Cash + Positions).
        Used by the Engine to draw the graph.
        """
        try:
            # 1. Fetch live equity from Alpaca
            account = self.dh.api.get_account()
            live_equity = float(account.equity)
            
            # 2. Update our internal tracker
            self.current_capital = live_equity
            
            return live_equity
            
        except Exception as e:
            logger.error(f"Error fetching live equity: {e}")
            # If API fails, return the last known good value so the graph doesn't crash
            return self.current_capital

    def set_allocation(self, strategy_id: str, amount: float, leverage: float = 1.0):
        """
        Sets the maximum capital budget for a specific strategy.
        :param amount: The base equity allocated.
        :param leverage: The leverage multiplier (e.g., 1.5 for 150%).
        """
        self.allocations[strategy_id] = {'equity': amount, 'leverage': leverage}
        logger.info(f"PortfolioManager: Set allocation for {strategy_id} to ${amount:.2f} with {leverage}x leverage")

    def check_trade(self, strategy_id: str, estimated_cost: float, current_exposure: float = None) -> bool:
        """
        Approves or denies a trade request based on available budget.
        :param current_exposure: (Optional) The strategy reports its own current exposure. 
                                 If None, PM tries to calculate it (which might be inaccurate for options).
        """
        if strategy_id not in self.allocations:
            logger.warning(f"PortfolioManager: No allocation found for {strategy_id}. Denying trade.")
            return False

        alloc_info = self.allocations[strategy_id]
        budget = alloc_info['equity'] * alloc_info['leverage']
        
        # 1. Get current market value of positions held by this strategy
        if current_exposure is None:
            current_exposure = self._get_strategy_exposure(strategy_id)
        
        # 2. Check if New + Current > Budget
        if current_exposure + estimated_cost > budget:
            logger.warning(
                f"PortfolioManager: Budget Exceeded for {strategy_id}. "
                f"Budget: ${budget:.2f} (Lev {alloc_info['leverage']}x), Current: ${current_exposure:.2f}, Requested: ${estimated_cost:.2f}"
            )
            return False
            
        return True

    def _get_strategy_exposure(self, strategy_id: str) -> float:
        """
        Calculates the current market value of all positions associated with this strategy.
        Assumes strategies track their own symbols or we filter by some tag.
        For now, we will rely on the Strategy object to tell us its symbols, 
        or we query Alpaca and filter.
        
        Since Alpaca doesn't natively tag positions by 'Strategy ID', 
        we have to infer it from the symbols the strategy manages.
        """
        # This is a simplified implementation. 
        # In a real system, we might store a mapping of Symbol -> StrategyID 
        # or use order tags if the broker supports it.
        
        # For this implementation, we will ask the DataHandler for all positions
        # and filter by the symbols we know belong to this strategy.
        # However, PortfolioManager doesn't know the symbols here directly.
        # We might need to pass the symbols in check_trade or store them.
        
        # Let's assume for now we check the account equity and rely on the 
        # strategy to not double-count symbols. 
        # A robust way is to pass the current held symbols to this method.
        return 0.0 # Placeholder: Needs integration with Strategy's symbol list

    def get_current_exposure(self, symbols: list) -> float:
        """
        Helper to calculate exposure for a list of symbols.
        """
        total_value = 0.0
        positions = self.dh.get_all_positions() # Assuming this returns a list of Alpaca Positions
        
        for pos in positions:
            if pos.symbol in symbols:
                total_value += float(pos.market_value)
                
        return abs(total_value)

    def get_remaining_budget(self, strategy_id: str) -> float:
        """
        Returns the remaining budget for a strategy.
        """
        if strategy_id not in self.allocations:
            return 0.0
            
        alloc_info = self.allocations[strategy_id]
        budget = alloc_info['equity'] * alloc_info['leverage']
        current_exposure = self._get_strategy_exposure(strategy_id)
        
        return max(0.0, budget - current_exposure)
