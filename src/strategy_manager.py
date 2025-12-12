import logging
from typing import Dict, List, Any
from strategies.option_pairs import OptionPairsStrategy
from regime_detector import RegimeDetector
# from strategies.pairs_trade import PairsTradeStrategy # Uncomment if needed

logger = logging.getLogger(__name__)

class StrategyManager:
    """
    The Conductor: Manages the lifecycle of strategies.
    """
    def __init__(self, data_handler, execution_handler, portfolio_manager):
        self.dh = data_handler
        self.eh = execution_handler
        self.pm = portfolio_manager
        self.strategies: Dict[str, Any] = {} # Map ID -> Strategy Instance
        self.regime_detector = RegimeDetector(self.dh)

    def update_strategies(self, strategy_configs: List[Dict]):
        """
        Updates the active strategies based on the provided configuration.
        
        :param strategy_configs: List of dicts. Each dict must have:
            - id: str
            - strategy_class: class object (e.g. OptionPairsStrategy)
            - allocation: float
            - parameters: dict (kwargs for the strategy init)
        """
        active_ids = set()
        
        for config in strategy_configs:
            strat_id = config['id']
            active_ids.add(strat_id)
            
            # 1. Update Allocation
            self.pm.set_allocation(strat_id, config['allocation'])
            
            # 2. Create or Update Strategy
            if strat_id not in self.strategies:
                logger.info(f"StrategyManager: Spawning new strategy {strat_id}")
                try:
                    StrategyClass = config['strategy_class']
                    params = config['parameters']
                    
                    # Inject dependencies
                    strategy = StrategyClass(
                        data_handler=self.dh,
                        execution_handler=self.eh,
                        portfolio_manager=self.pm,
                        strategy_id=strat_id,
                        **params
                    )
                    
                    # 3. Reconcile State (The "Sherlock Holmes" Logic)
                    # We pass an empty map initially. The main loop calls reconcile_positions() 
                    # shortly after, which will do the full check with actual broker data.
                    strategy.reconcile({})
                    
                    self.strategies[strat_id] = strategy
                    
                except Exception as e:
                    logger.error(f"StrategyManager: Failed to spawn {strat_id}: {e}")
            else:
                # Strategy already exists. 
                # In a complex system, we might update parameters here.
                pass

        # 4. Cleanup (Optional)
        # If a strategy is no longer in the config, we might want to stop it.
        # For now, we just log it.
        current_ids = set(self.strategies.keys())
        removed_ids = current_ids - active_ids
        for rid in removed_ids:
            logger.warning(f"StrategyManager: Strategy {rid} is no longer in the config. It is still running but won't be updated.")
            # self.strategies.pop(rid) # Uncomment to actually remove it

    def reconcile_positions(self):
        """
        Queries the broker for all open positions and matches them to strategies.
        """
        logger.info("StrategyManager: Reconciling open positions...")
        
        try:
            # 1. Get all open positions from Alpaca
            open_positions = self.eh.get_all_positions() 
            
            # 2. Group positions by symbol for easy lookup
            # positions_map = {'AAPL': PositionObj, 'MSFT': PositionObj}
            positions_map = {p.symbol: p for p in open_positions}
            
            logger.info(f"StrategyManager: Found {len(positions_map)} open positions at broker.")
            
            # 3. Check each active strategy
            for strat_id, strategy in self.strategies.items():
                # Ask the strategy to check if it owns any of these positions
                strategy.reconcile(positions_map)
                
        except Exception as e:
            logger.error(f"StrategyManager: Reconciliation failed: {e}")

    def kill_strategy(self, strategy_id):
        """
        Kills a specific strategy and closes its positions.
        """
        if strategy_id in self.strategies:
            logger.warning(f"StrategyManager: Killing strategy {strategy_id}")
            strategy = self.strategies[strategy_id]
            strategy.kill_switch()
            # Optionally remove it from the active list?
            # self.strategies.pop(strategy_id) 
        else:
            logger.warning(f"StrategyManager: Cannot kill {strategy_id} - not found.")

    def run_tick(self):
        """
        The main heartbeat. Asks every strategy to play its part.
        """
        # 1. Get Current Regime
        current_regime = self.regime_detector.get_current_regime()
        
        for strat_id, strategy in self.strategies.items():
            try:
                # Check if strategy is manually disabled
                if hasattr(strategy, 'active') and not strategy.active:
                    continue

                strat_type = type(strategy).__name__
                
                # Check regime constraints
                # State 1 = Volatile (Bad for Pairs Trade)
                if current_regime == 1 and "PairsTrade" in strat_type:
                    logger.info(f"StrategyManager: Skipping {strat_id} ({strat_type}) due to High Volatility Regime")
                    continue
                
                # State 0 = Calm (Bad for Volatility Arbitrage / Gamma Scalping)
                if current_regime == 0 and "VolatilityArbitrage" in strat_type:
                    logger.info(f"StrategyManager: Skipping {strat_id} ({strat_type}) due to Calm Regime")
                    continue

                logger.debug(f"StrategyManager: Ticking {strat_id}")
                signals = strategy.generate_signal()
                
                if signals:
                    logger.info(f"StrategyManager: {strat_id} generated {len(signals)} signals.")
                    # Execution is usually handled inside generate_signal via ExecutionHandler
                    # or returned here. 
                    # Based on OptionPairsStrategy, it returns signals but also has auto_execute logic?
                    # Let's assume the strategy handles execution or we pass signals to EH here.
                    
                    # If the strategy returns signals but doesn't execute them itself:
                    if not getattr(strategy, 'auto_execute', False):
                        self.eh.execute_signals(signals)
                        
            except Exception as e:
                logger.error(f"StrategyManager: Error in {strat_id}: {e}")

    def kill_all(self):
        """
        The Red Button.
        """
        logger.critical("StrategyManager: KILL ALL triggered.")
        for strategy in self.strategies.values():
            strategy.kill_switch()
