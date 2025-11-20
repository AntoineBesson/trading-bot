"""Option-based extension of the pairs trading strategy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import logging
import pandas as pd

from strategies.base_strategy import BaseStrategy
from options.data_handler import OptionDataHandler, OptionSnapshot
from options.multileg import MultiLegExecutionHelper

logger = logging.getLogger(__name__)

Signal = Dict[str, object]


@dataclass
class OptionPairsStrategy(BaseStrategy):
    data_handler: object
    execution_handler: object
    portfolio_manager: object # NEW: The CFO
    strategy_id: str          # NEW: Unique ID
    symbol_a: str
    symbol_b: str
    option_type: str = "call"
    long_option_type: Optional[str] = None
    short_option_type: Optional[str] = None
    target_delta: float = 0.45
    days_to_expiry: int = 30
    lookback_days: int = 90
    entry_threshold: float = 1.0
    exit_threshold: float = 0.0
    contracts: int = 1
    risk_per_trade: float = 0.01 # Risk 1% of account per trade
    timeframe: str = "1D"
    stat_refresh_days: int = 5
    auto_execute: bool = False
    benchmark_symbol: Optional[str] = None
    initial_capital: float = 10_000.0
    option_data_handler: Optional[OptionDataHandler] = None
    multi_leg_execution: Optional[MultiLegExecutionHelper] = None
    name: str = field(default="OptionPairsStrategy", init=False)

    def __post_init__(self) -> None:
        super().__init__(
            data_handler=self.data_handler,
            execution_handler=self.execution_handler,
            portfolio_manager=self.portfolio_manager,
            strategy_id=self.strategy_id,
            symbols=[self.symbol_a, self.symbol_b],
        )
        self.option_data = self.option_data_handler or OptionDataHandler(self.data_handler)
        self.multi_leg_exec = self.multi_leg_execution or MultiLegExecutionHelper(self.execution_handler)
        self.long_option_type = self.long_option_type or self.option_type
        self.short_option_type = self.short_option_type or self.option_type
        self.position = "flat"
        self.position_option_type: Optional[str] = None
        self.last_z_score: Optional[float] = None
        self.spread_mean: Optional[float] = None
        self.spread_std: Optional[float] = None
        self._last_stat_refresh: Optional[datetime] = None
        self._vega_ratio: float = 1.0
        
        # Equity Guard: Track last known stock prices
        self.last_stock_price_a: Optional[float] = None
        self.last_stock_price_b: Optional[float] = None
        
        self._init_reference_distribution()

    # ------------------------------------------------------------------
    def generate_signal(self) -> List[Signal]:
        self._maybe_refresh_spread_stats()
        
        # --- OPTIMIZATION: Equity Guard ---
        # Fetch underlying stock prices first (Fast/Cheap API call)
        # Only proceed to expensive option chain lookup if stocks have moved significantly
        bar_a = self.data_handler.get_latest_bar(self.symbol_a)
        bar_b = self.data_handler.get_latest_bar(self.symbol_b)
        
        if bar_a and bar_b:
            curr_a = bar_a['close']
            curr_b = bar_b['close']
            
            # If we have previous prices, check if they moved enough to warrant an option lookup
            if self.last_stock_price_a and self.last_stock_price_b:
                pct_change_a = abs((curr_a - self.last_stock_price_a) / self.last_stock_price_a)
                pct_change_b = abs((curr_b - self.last_stock_price_b) / self.last_stock_price_b)
                
                # If both stocks moved less than 0.1%, skip the heavy option call
                # Unless we are IN a trade (we always want to monitor exits)
                if pct_change_a < 0.001 and pct_change_b < 0.001 and self.position == "flat":
                    # Update cache even if we skip
                    self.last_stock_price_a = curr_a
                    self.last_stock_price_b = curr_b
                    return []

            # Update cache
            self.last_stock_price_a = curr_a
            self.last_stock_price_b = curr_b
        # --- END OPTIMIZATION ---

        pricing_snaps = self._get_snapshots(self.option_type)
        if pricing_snaps is None:
            return []

        snap_a, snap_b = pricing_snaps
        self._vega_ratio = self._compute_vega_ratio(snap_a, snap_b)
        spread = snap_a.price - self._vega_ratio * snap_b.price
        z_score = self._compute_z_score(spread)
        self.last_z_score = z_score

        action = self._determine_action(z_score)
        if action == "none":
            return []

        trade_option_type = self._option_type_for_action(action)
        trade_snaps = self._get_snapshots(trade_option_type)
        if trade_snaps is None:
            return []

        trade_snap_a, trade_snap_b = trade_snaps
        signals = self._dispatch_action(action, trade_snap_a, trade_snap_b)
        if self.auto_execute and signals:
            self.multi_leg_exec.execute(signals)
        return signals

    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        timeframe: str,
    ) -> Dict[str, object]:
        option_prices = self._build_option_series(start_date, end_date, timeframe)
        if option_prices.empty:
            raise ValueError("No data for option backtest")

        trades: List[Dict[str, object]] = []
        position = "flat"
        active_trade: Optional[Dict[str, object]] = None
        capital = self.initial_capital
        equity = capital
        equity_curve: List[float] = []

        for timestamp, row in option_prices.iterrows():
            spread = row["spread"]
            z = row["z_score"]
            price_a = row["price_a"]
            price_b = row["price_b"]
            vega_ratio = row["vega_ratio"]

            if position == "flat":
                if z >= self.entry_threshold:
                    position = "short"
                    active_trade = {
                        "timestamp": str(timestamp),
                        "direction": "short",
                        "entry_a": price_a,
                        "entry_b": price_b,
                        "vega_ratio": vega_ratio,
                    }
                    trades.append(active_trade)
                elif z <= -self.entry_threshold:
                    position = "long"
                    active_trade = {
                        "timestamp": str(timestamp),
                        "direction": "long",
                        "entry_a": price_a,
                        "entry_b": price_b,
                        "vega_ratio": vega_ratio,
                    }
                    trades.append(active_trade)
            elif position == "short" and z <= self.exit_threshold and active_trade:
                pnl = (active_trade["entry_a"] - price_a) * self.contracts
                pnl += (price_b - active_trade["entry_b"]) * self.contracts * active_trade["vega_ratio"]
                equity += pnl
                active_trade["exit_a"] = price_a
                active_trade["exit_b"] = price_b
                active_trade["pnl"] = pnl
                position = "flat"
            elif position == "long" and z >= -self.exit_threshold and active_trade:
                pnl = (price_a - active_trade["entry_a"]) * self.contracts
                pnl += (active_trade["entry_b"] - price_b) * self.contracts * active_trade["vega_ratio"]
                equity += pnl
                active_trade["exit_a"] = price_a
                active_trade["exit_b"] = price_b
                active_trade["pnl"] = pnl
                position = "flat"

            equity_curve.append(equity)

        closed = [t for t in trades if "pnl" in t]
        win_rate = sum(1 for t in closed if t["pnl"] > 0) / len(closed) if closed else 0.0
        equity_series = pd.Series(equity_curve, index=option_prices.index[: len(equity_curve)])
        returns = equity_series.pct_change().fillna(0)
        sharpe = self._compute_sharpe(returns, timeframe)
        max_dd = self._compute_max_drawdown(equity_series)
        strategy_return = (equity_series.iloc[-1] / capital - 1) if not equity_series.empty else 0.0

        return {
            "num_trades": len(closed),
            "open_trades": len(trades) - len(closed),
            "total_pnl": equity - capital,
            "win_rate": win_rate,
            "strategy_return": strategy_return,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "equity_curve": equity_series,
            "trades": closed,
        }

    # ------------------------------------------------------------------
    def _determine_action(self, z_score: float) -> str:
        if self.position == "flat":
            if z_score >= self.entry_threshold:
                return "open_short"
            if z_score <= -self.entry_threshold:
                return "open_long"
        elif self.position == "short" and z_score <= self.exit_threshold:
            return "close_short"
        elif self.position == "long" and z_score >= -self.exit_threshold:
            return "close_long"
        return "none"

    def _get_snapshots(self, option_type: str) -> Optional[Tuple[OptionSnapshot, OptionSnapshot]]:
        if not option_type:
            return None
        snap_a = self.option_data.get_option_snapshot(
            symbol=self.symbol_a,
            option_type=option_type,
            target_delta=self.target_delta,
            days_to_expiry=self.days_to_expiry,
        )
        snap_b = self.option_data.get_option_snapshot(
            symbol=self.symbol_b,
            option_type=option_type,
            target_delta=self.target_delta,
            days_to_expiry=self.days_to_expiry,
        )
        if not snap_a or not snap_b:
            return None
        return snap_a, snap_b

    def _option_type_for_action(self, action: str) -> str:
        if action == "open_long":
            return self.long_option_type
        if action == "open_short":
            return self.short_option_type
        if self.position_option_type:
            return self.position_option_type
        return self.long_option_type if self.position == "long" else self.short_option_type

    def _dispatch_action(self, action: str, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> List[Signal]:
        # --- Volatility Targeting (The "Quant" Way) ---
        # 1. Get Account Equity
        try:
            account = self.data_handler.get_account()
            equity = float(account.equity) if account else self.initial_capital
        except Exception:
            equity = self.initial_capital

        # 2. Calculate Risk Amount (e.g., 1% of $100k = $1,000)
        risk_amount = equity * self.risk_per_trade

        # 3. Calculate Volatility (Standard Deviation of the Spread)
        # If spread_std is high, we trade smaller size.
        # If spread_std is low, we trade larger size.
        # We use the spread_std (dollar value of spread deviation) as a proxy for risk per unit.
        # Ideally, we'd use the option's specific volatility, but spread vol is a good proxy for the pair.
        volatility_proxy = self.spread_std if self.spread_std and self.spread_std > 0 else 1.0
        
        # 4. Calculate Position Size
        # "I want to risk $1,000. One unit of risk is 1 Standard Deviation of the spread."
        # Contracts = Risk Amount / (Volatility * Contract Multiplier)
        # Multiplier is 100 for options.
        # We also clamp it to be reasonable (e.g. not 0, not 1000 contracts).
        
        # Note: This assumes that a 1-sigma move against us represents our "Risk Unit".
        # You can adjust this denominator to be 2*volatility if you want to survive a 2-sigma move.
        raw_contracts = risk_amount / (volatility_proxy * 100)
        
        # Ensure we can afford it (Basic check against option price)
        option_price = snap_a.ask if "open" in action else snap_a.bid
        max_affordable = (equity * 0.5) / (option_price * 100) # Don't use >50% of account on one leg
        
        target_contracts = int(min(raw_contracts, max_affordable))
        target_contracts = max(1, target_contracts) # Always trade at least 1
        
        logger.info(f"Vol Target Sizing: Equity=${equity:.0f}, Risk=${risk_amount:.0f}, Vol=${volatility_proxy:.2f} -> {target_contracts} contracts")

        # --- Portfolio Manager Cap ---
        if "open" in action:
            remaining_budget = self.portfolio_manager.get_remaining_budget(self.strategy_id)
            
            cost_per_unit = 0.0
            if action == "open_short":
                # We buy B. Quantity is target * vega_ratio
                cost_per_unit = self._vega_ratio * snap_b.ask * 100
            elif action == "open_long":
                # We buy A. Quantity is target
                cost_per_unit = snap_a.ask * 100
                
            if cost_per_unit > 0:
                max_contracts_budget = int(remaining_budget // cost_per_unit)
                if max_contracts_budget < target_contracts:
                    logger.info(f"[{self.strategy_id}] Capping trade due to budget. Req: {target_contracts}, Allowed: {max_contracts_budget}")
                    target_contracts = max_contracts_budget
                    
                if target_contracts < 1:
                    logger.warning(f"[{self.strategy_id}] Insufficient budget for even 1 contract.")
                    return []

        if action == "open_short":
            # Short the spread: Sell A, Buy B
            qty_a = target_contracts
            qty_b = int(round(target_contracts * self._vega_ratio))
            
            self.position = "short"
            self.position_option_type = self.short_option_type
            self.open_qty_a = qty_a
            self.open_qty_b = qty_b
            
            return [
                self._build_leg(snap_a, "sell", qty_a),
                self._build_leg(snap_b, "buy", qty_b),
            ]
        elif action == "open_long":
            # Long the spread: Buy A, Sell B
            qty_a = target_contracts
            qty_b = int(round(target_contracts * self._vega_ratio))
            
            self.position = "long"
            self.position_option_type = self.long_option_type
            self.open_qty_a = qty_a
            self.open_qty_b = qty_b
            
            return [
                self._build_leg(snap_a, "buy", qty_a),
                self._build_leg(snap_b, "sell", qty_b),
            ]
        elif action == "close_short":
            # Close short: Buy A, Sell B
            qty_a = getattr(self, 'open_qty_a', target_contracts) 
            qty_b = getattr(self, 'open_qty_b', int(round(qty_a * self._vega_ratio)))
            
            self.position = "flat"
            self.position_option_type = None
            self.open_qty_a = 0
            self.open_qty_b = 0
            
            return [
                self._build_leg(snap_a, "buy", qty_a),
                self._build_leg(snap_b, "sell", qty_b),
            ]
        elif action == "close_long":
            # Close long: Sell A, Buy B
            qty_a = getattr(self, 'open_qty_a', target_contracts)
            qty_b = getattr(self, 'open_qty_b', int(round(qty_a * self._vega_ratio)))
            
            self.position = "flat"
            self.position_option_type = None
            self.open_qty_a = 0
            self.open_qty_b = 0
            
            return [
                self._build_leg(snap_a, "sell", qty_a),
                self._build_leg(snap_b, "buy", qty_b),
            ]
        return []

    def _build_leg(self, snap: OptionSnapshot, action: str, qty: int) -> Signal:
        return {
            "asset_type": "option",
            "underlying": snap.symbol,
            "symbol": snap.symbol,
            "option_type": snap.option_type,
            "strike": snap.strike,
            "expiration": snap.expiration,
            "action": action,
            "qty": int(qty),
            "limit_price": snap.price,
            "type": "limit",
            "time_in_force": "day",
        }

    def _hedge_contracts(self, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> int:
        ratio = self._compute_vega_ratio(snap_a, snap_b)
        qty = max(1, int(round(self.contracts * ratio)))
        return qty

    def _compute_vega_ratio(self, snap_a: OptionSnapshot, snap_b: OptionSnapshot) -> float:
        if snap_b.vega == 0:
            return 1.0
        return max(0.1, snap_a.vega / abs(snap_b.vega))

    def _compute_z_score(self, spread: float) -> float:
        if self.spread_mean is None or self.spread_std in (None, 0):
            raise RuntimeError("Spread statistics are not initialised")
        return (spread - self.spread_mean) / self.spread_std

    def _maybe_refresh_spread_stats(self) -> None:
        if self._last_stat_refresh is None:
            self._init_reference_distribution()
            return
        elapsed = datetime.now(UTC) - self._last_stat_refresh
        if elapsed >= timedelta(days=self.stat_refresh_days):
            self._init_reference_distribution()

    def _init_reference_distribution(self) -> None:
        start = self._iso_days_ago(self.lookback_days)
        end = self._iso_days_ago(0)
        option_prices = self._build_option_series(start, end, self.timeframe)
        if option_prices.empty:
            raise RuntimeError("Unable to bootstrap option spread statistics")
        spread = option_prices["spread"]
        self.spread_mean = float(spread.mean())
        self.spread_std = float(spread.std(ddof=0)) or 1.0
        self._last_stat_refresh = datetime.now(UTC)

    def _build_option_series(self, start: str, end: str, timeframe: str) -> pd.DataFrame:
        prices = self._fetch_close_frame(start, end, timeframe)
        if prices.empty:
            return pd.DataFrame()

        iv_a = self.option_data.estimate_historical_vol(self.symbol_a)
        iv_b = self.option_data.estimate_historical_vol(self.symbol_b)
        ttm = max(self.days_to_expiry / 252, 1e-4)
        greeks = self.option_data.greeks
        strike_a = greeks.find_strike_for_delta(self.target_delta, self.option_type, float(prices[self.symbol_a].iloc[-1]), ttm, iv_a)
        strike_b = greeks.find_strike_for_delta(self.target_delta, self.option_type, float(prices[self.symbol_b].iloc[-1]), ttm, iv_b)

        opt_a = greeks.price_series(self.option_type, prices[self.symbol_a], strike_a, ttm, iv_a)
        opt_b = greeks.price_series(self.option_type, prices[self.symbol_b], strike_b, ttm, iv_b)
        df = pd.DataFrame(
            {
                "price_a": opt_a["price"],
                "price_b": opt_b["price"],
                "vega_a": opt_a["vega"],
                "vega_b": opt_b["vega"],
            }
        )
        df["vega_ratio"] = df.apply(lambda row: max(0.1, row.vega_a / max(row.vega_b, 1e-6)), axis=1)
        df["spread"] = df["price_a"] - df["vega_ratio"] * df["price_b"]
        window = max(10, int(len(df) * 0.2))
        df["spread_mean"] = df["spread"].rolling(window=window, min_periods=max(5, window // 2)).mean()
        df["spread_std"] = df["spread"].rolling(window=window, min_periods=max(5, window // 2)).std(ddof=0)
        df["z_score"] = (df["spread"] - df["spread_mean"]) / df["spread_std"]
        df = df.replace([pd.NA, pd.NaT, float("inf"), float("-inf")], pd.NA).dropna(subset=["z_score"])
        return df

    def _fetch_close_frame(self, start_date: str, end_date: str, timeframe: str) -> pd.DataFrame:
        data = self.data_handler.get_historical_bars([self.symbol_a, self.symbol_b], timeframe, start=start_date, end=end_date)
        if not data:
            return pd.DataFrame()
        frames = []
        for symbol in (self.symbol_a, self.symbol_b):
            df = data.get(symbol)
            if df is None or df.empty:
                continue
            tmp = df.copy()
            tmp.index = pd.to_datetime(tmp.index)
            if getattr(tmp.index, "tz", None) is not None:
                tmp.index = tmp.index.tz_convert("UTC").tz_localize(None)
            frames.append(tmp[["close"]].rename(columns={"close": symbol}))
        if len(frames) != 2:
            return pd.DataFrame()
        merged = pd.concat(frames, axis=1).dropna()
        return merged

    @staticmethod
    def _compute_sharpe(returns: pd.Series, timeframe: str) -> float:
        if returns.empty or returns.std() == 0:
            return 0.0
        periods = OptionPairsStrategy._periods_per_year(timeframe)
        return float((returns.mean() / returns.std()) * (periods ** 0.5))

    @staticmethod
    def _compute_max_drawdown(equity: pd.Series) -> float:
        if equity.empty:
            return 0.0
        running_max = equity.cummax()
        drawdown = (equity / running_max) - 1
        return float(abs(drawdown.min()))

    @staticmethod
    def _periods_per_year(timeframe: str) -> int:
        tf = timeframe.strip().upper()
        if tf.endswith("MIN"):
            minutes = int(tf[:-3])
        elif tf.endswith("H"):
            minutes = int(tf[:-1]) * 60
        elif tf.endswith("D"):
            minutes = int(tf[:-1]) * 1440
        else:
            mapping = {"1D": 1440, "1H": 60, "4H": 240, "15MIN": 15, "5MIN": 5, "1MIN": 1}
            minutes = mapping.get(tf, 1440)
        periods_per_day = max(1, int(1440 / minutes))
        return periods_per_day * 252

    @staticmethod
    def _iso_days_ago(days: int) -> str:
        return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()

    def reconcile(self, positions_map: Dict[str, object]):
        """
        Checks if the bot is already in a trade for this pair.
        """
        # Check if we hold the option legs
        # Note: This is tricky for options because symbols change (e.g. MSFT230519C00300000)
        # We check if any key in positions_map STARTS with self.symbol_a or self.symbol_b
        
        found_legs = []
        
        for symbol, position in positions_map.items():
            # Basic check: does the position symbol start with our underlying?
            # This assumes standard OCC option symbology where underlying is at the start
            if symbol.startswith(self.symbol_a) or symbol.startswith(self.symbol_b):
                # Verify it's an option (length check or other heuristic if needed)
                # For now, we assume if it matches and we are an option strategy, it's ours.
                # In a real production system, we'd check the 'asset_class' attribute of the position.
                if getattr(position, 'asset_class', 'us_equity') == 'us_option':
                    found_legs.append(symbol)
        
        if found_legs:
            logger.info(f"[{self.strategy_id}] Found existing option positions: {found_legs}")
            self.position = "invested"
            # Store them if we want to manage them specifically
            # self.active_legs = found_legs 
        else:
            self.position = "flat"
            logger.info(f"[{self.strategy_id}] No existing positions found.")

    def kill_switch(self):
        """
        Closes all option positions related to this strategy's symbols.
        """
        logger.warning(f"[{self.strategy_id}] KILL SWITCH: Closing positions for {self.symbol_a}/{self.symbol_b}")
        
        # We need to find the positions again to close them
        # Since we don't store them persistently, we query the execution handler
        try:
            all_positions = self.execution_handler.get_all_positions()
            for position in all_positions:
                symbol = position.symbol
                if (symbol.startswith(self.symbol_a) or symbol.startswith(self.symbol_b)) and \
                   getattr(position, 'asset_class', 'us_equity') == 'us_option':
                    
                    logger.info(f"[{self.strategy_id}] Closing position: {symbol}")
                    self.execution_handler.close_position(symbol)
                    
            self.position = "flat"
            
        except Exception as e:
            logger.error(f"[{self.strategy_id}] Kill switch failed: {e}")


__all__ = ["OptionPairsStrategy"]
