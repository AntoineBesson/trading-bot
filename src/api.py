from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional
import logging
import os
import numpy as np
from src.engine import TradingEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Engine Instance
engine = None
startup_error = None

# Global Risk Limits (configurable)
risk_limits = {
    "max_position_pct": 10,
    "max_var_threshold": -5.0,
    "max_sector_concentration": 30,
    "max_drawdown_threshold": -20.0
}

# Pydantic models for request bodies
class AllocationUpdate(BaseModel):
    equity: float
    leverage: Optional[float] = 1.0

class RiskLimitsUpdate(BaseModel):
    max_position_pct: Optional[float] = None
    max_var_threshold: Optional[float] = None
    max_sector_concentration: Optional[float] = None
    max_drawdown_threshold: Optional[float] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, startup_error
    # Startup
    try:
        logger.info("Initializing Trading Engine...")
        engine = TradingEngine()
        logger.info("Starting Trading Engine...")
        engine.start()
    except Exception as e:
        logger.error(f"Failed to start engine: {e}")
        startup_error = str(e)
    
    yield
    # Shutdown
    if engine:
        logger.info("Stopping Trading Engine...")
        engine.stop()

app = FastAPI(lifespan=lifespan)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now (dev mode)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoints ---
@app.get("/api/status") # Support both /status and /api/status for flexibility
@app.get("/status")
def get_status():
    if startup_error:
        return {"status": "error", "message": startup_error}
    if not engine:
        return {"status": "initializing"}
        
    status = engine.get_status()
    # Add regime info
    try:
        regime = engine.sm.regime_detector.get_current_regime()
        status["regime"] = "Volatile" if regime == 1 else "Calm"
    except Exception as e:
        logger.error(f"Failed to get regime: {e}")
        status["regime"] = "Unknown"
    return status

@app.get("/api/strategies")
@app.get("/strategies")
def get_strategies():
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    status = engine.get_status()
    return status["strategies"]

@app.post("/api/strategies/{strategy_id}/toggle")
@app.post("/strategies/{strategy_id}/toggle")
def toggle_strategy(strategy_id: str):
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
        
    strategies = engine.sm.strategies
    if strategy_id not in strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    strategy = strategies[strategy_id]
    
    # Toggle active state
    # Ensure the strategy has the 'active' attribute (BaseStrategy should have it now)
    if not hasattr(strategy, 'active'):
        strategy.active = True # Default to True if missing
        
    strategy.active = not strategy.active
    
    return {
        "id": strategy_id,
        "active": strategy.active,
        "message": f"Strategy {strategy_id} is now {'active' if strategy.active else 'inactive'}"
    }

@app.post("/api/strategies/{strategy_id}/stop")
@app.post("/strategies/{strategy_id}/stop")
def stop_strategy(strategy_id: str):
    """Pauses a specific strategy."""
    success = engine.sm.stop_strategy(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "stopped", "id": strategy_id}

@app.post("/api/strategies/{strategy_id}/start")
@app.post("/strategies/{strategy_id}/start")
def start_strategy(strategy_id: str):
    """Resumes a specific strategy."""
    success = engine.sm.start_strategy(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "started", "id": strategy_id}

@app.post("/api/strategies/{strategy_id}/kill")
@app.post("/strategies/{strategy_id}/kill")
def kill_strategy(strategy_id: str):
    """Emergency kill switch - closes all positions for a strategy."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    strategies = engine.sm.strategies
    if strategy_id not in strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    strategy = strategies[strategy_id]
    
    try:
        # First deactivate the strategy
        strategy.active = False
        
        # Call kill_switch if available
        if hasattr(strategy, 'kill_switch'):
            strategy.kill_switch()
            logger.warning(f"Kill switch activated for {strategy_id}")
        
        return {
            "status": "killed",
            "id": strategy_id,
            "message": f"Strategy {strategy_id} killed and positions closed"
        }
    except Exception as e:
        logger.error(f"Failed to kill strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/emergency/kill-all")
@app.post("/emergency/kill-all")
def kill_all_strategies():
    """Global emergency kill switch - closes all positions across all strategies."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    try:
        killed = []
        for strat_id, strategy in engine.sm.strategies.items():
            strategy.active = False
            if hasattr(strategy, 'kill_switch'):
                strategy.kill_switch()
            killed.append(strat_id)
        
        logger.critical("GLOBAL KILL SWITCH ACTIVATED - All strategies killed")
        
        return {
            "status": "all_killed",
            "strategies": killed,
            "message": "All strategies killed and positions closed"
        }
    except Exception as e:
        logger.error(f"Failed to execute global kill: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/allocations")
@app.get("/allocations")
def get_allocations():
    """Returns all strategy allocations with current exposure details."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    try:
        total_equity = engine.pm.get_total_equity()
        allocations = engine.pm.allocations
        
        # Enrich with strategy status and exposure
        enriched = {}
        for strat_id, alloc in allocations.items():
            strategy = engine.sm.strategies.get(strat_id)
            exposure = alloc.get('equity', 0) * alloc.get('leverage', 1)
            
            enriched[strat_id] = {
                "equity": alloc.get('equity', 0),
                "leverage": alloc.get('leverage', 1),
                "exposure": exposure,
                "active": getattr(strategy, 'active', False) if strategy else False,
                "symbols": strategy.symbols if strategy else [],
                "remaining_budget": engine.pm.get_remaining_budget(strat_id)
            }
        
        return {
            "total_equity": total_equity,
            "allocations": enriched
        }
    except Exception as e:
        logger.error(f"Failed to get allocations: {e}")
        return {"total_equity": 0, "allocations": {}}

@app.put("/api/allocations/{strategy_id}")
@app.put("/allocations/{strategy_id}")
def update_allocation(strategy_id: str, update: AllocationUpdate):
    """Update allocation for a specific strategy."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    if strategy_id not in engine.sm.strategies:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    try:
        # Validate inputs
        if update.equity < 0:
            raise HTTPException(status_code=400, detail="Equity must be non-negative")
        if update.leverage < 0.1 or update.leverage > 10:
            raise HTTPException(status_code=400, detail="Leverage must be between 0.1 and 10")
        
        # Update allocation
        engine.pm.set_allocation(strategy_id, update.equity, update.leverage)
        
        logger.info(f"Allocation updated: {strategy_id} -> ${update.equity} @ {update.leverage}x")
        
        return {
            "status": "updated",
            "id": strategy_id,
            "equity": update.equity,
            "leverage": update.leverage,
            "exposure": update.equity * update.leverage
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update allocation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/risk/limits")
@app.get("/risk/limits")
def get_risk_limits():
    """Returns configurable risk limits."""
    return risk_limits

@app.put("/api/risk/limits")
@app.put("/risk/limits")
def update_risk_limits(update: RiskLimitsUpdate):
    """Update risk limits."""
    global risk_limits
    
    if update.max_position_pct is not None:
        risk_limits["max_position_pct"] = update.max_position_pct
    if update.max_var_threshold is not None:
        risk_limits["max_var_threshold"] = update.max_var_threshold
    if update.max_sector_concentration is not None:
        risk_limits["max_sector_concentration"] = update.max_sector_concentration
    if update.max_drawdown_threshold is not None:
        risk_limits["max_drawdown_threshold"] = update.max_drawdown_threshold
    
    logger.info(f"Risk limits updated: {risk_limits}")
    return risk_limits

@app.get("/api/capital")
@app.get("/capital")
def get_capital():
    """Returns capital allocation per strategy."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    try:
        total_equity = engine.pm.get_total_equity()
        allocations = engine.pm.allocations
        
        return {
            "total_equity": total_equity,
            "allocations": allocations
        }
    except Exception as e:
        logger.error(f"Failed to get capital: {e}")
        return {"total_equity": 0, "allocations": {}}

@app.get("/api/performance")
@app.get("/performance")
def get_performance():
    """Returns performance metrics calculated from equity history."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    try:
        history = engine.equity_history
        if len(history) < 2:
            return {"error": "Not enough data"}
        
        # Extract values
        values = [h['value'] for h in history]
        returns = np.diff(values) / values[:-1] if len(values) > 1 else []
        
        # Calculate metrics
        total_return = (values[-1] - values[0]) / values[0] if values[0] > 0 else 0
        
        # Sharpe Ratio (annualized, assuming ~252 trading days)
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
        else:
            sharpe = 0
        
        # Sortino Ratio (downside deviation)
        downside_returns = [r for r in returns if r < 0]
        if len(downside_returns) > 1:
            downside_std = np.std(downside_returns)
            sortino = (np.mean(returns) / downside_std) * np.sqrt(252) if downside_std > 0 else 0
        else:
            sortino = 0
        
        # Max Drawdown
        peak = values[0]
        max_dd = 0
        for v in values:
            if v > peak:
                peak = v
            dd = (v - peak) / peak if peak > 0 else 0
            if dd < max_dd:
                max_dd = dd
        
        # Calmar Ratio
        calmar = total_return / abs(max_dd) if max_dd != 0 else 0
        
        # Win rate (simple: positive returns)
        winning = len([r for r in returns if r > 0])
        losing = len([r for r in returns if r < 0])
        total_trades = winning + losing
        win_rate = winning / total_trades if total_trades > 0 else 0
        
        # Average win/loss
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]
        avg_win = np.mean(wins) * values[-1] if wins else 0
        avg_loss = abs(np.mean(losses) * values[-1]) if losses else 0
        
        # Profit factor
        gross_profit = sum([r for r in returns if r > 0]) * values[-1]
        gross_loss = abs(sum([r for r in returns if r < 0]) * values[-1])
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return {
            "total_return": total_return,
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "calmar_ratio": float(calmar),
            "max_drawdown": float(max_dd),
            "win_rate": float(win_rate),
            "total_trades": total_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            "profit_factor": float(profit_factor),
            "information_ratio": None  # Would need benchmark data
        }
    except Exception as e:
        logger.error(f"Failed to calculate performance: {e}")
        return {"error": str(e)}

@app.get("/api/risk")
@app.get("/risk")
def get_risk():
    """Returns comprehensive risk metrics."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    try:
        history = engine.equity_history
        values = [h['value'] for h in history] if history else []
        returns = np.diff(values) / values[:-1] if len(values) > 1 else []
        
        # VaR (95% confidence)
        var_95 = float(np.percentile(returns, 5)) * 100 if len(returns) > 5 else None
        
        # VaR (99% confidence) - more conservative
        var_99 = float(np.percentile(returns, 1)) * 100 if len(returns) > 10 else None
        
        # CVaR / Expected Shortfall (average loss beyond VaR)
        if len(returns) > 5:
            var_threshold = np.percentile(returns, 5)
            tail_losses = [r for r in returns if r <= var_threshold]
            cvar_95 = float(np.mean(tail_losses)) * 100 if tail_losses else var_95
        else:
            cvar_95 = None
        
        # Get exposure by strategy from allocations
        allocations = engine.pm.allocations
        exposure_by_strategy = {}
        total_exposure = 0
        
        for strat_id, alloc in allocations.items():
            exposure = alloc.get('equity', 0) * alloc.get('leverage', 1)
            exposure_by_strategy[strat_id] = exposure
            total_exposure += exposure
        
        # Portfolio Greeks (aggregate from option strategies if available)
        greeks = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
        
        for strat_id, strategy in engine.sm.strategies.items():
            if hasattr(strategy, 'get_portfolio_greeks'):
                try:
                    strat_greeks = strategy.get_portfolio_greeks()
                    greeks['delta'] += strat_greeks.get('delta', 0)
                    greeks['gamma'] += strat_greeks.get('gamma', 0)
                    greeks['theta'] += strat_greeks.get('theta', 0)
                    greeks['vega'] += strat_greeks.get('vega', 0)
                except:
                    pass
        
        # Margin utilization from Alpaca
        margin_used = 0
        margin_available = 0
        buying_power = 0
        try:
            if engine.pm.trading_client:
                account = engine.pm.trading_client.get_account()
                buying_power = float(account.buying_power)
                margin_available = float(account.regt_buying_power) if hasattr(account, 'regt_buying_power') else buying_power
                # Estimate margin used as total exposure minus cash
                equity = float(account.equity)
                cash = float(account.cash)
                margin_used = max(0, total_exposure - cash)
        except Exception as e:
            logger.warning(f"Could not fetch margin info: {e}")
        
        margin_utilization = (margin_used / margin_available * 100) if margin_available > 0 else 0
        
        # Get current regime
        regime = "Unknown"
        regime_confidence = 0
        try:
            regime_val = engine.sm.regime_detector.get_current_regime()
            regime = "Volatile" if regime_val == 1 else "Calm"
            # Attempt to get confidence if available
            if hasattr(engine.sm.regime_detector, 'get_confidence'):
                regime_confidence = engine.sm.regime_detector.get_confidence()
            else:
                regime_confidence = 0.8  # Default confidence
        except:
            pass
        
        # Sector concentration (simplified - based on strategy types)
        strategy_types = {}
        for strat_id, strategy in engine.sm.strategies.items():
            stype = type(strategy).__name__
            if stype not in strategy_types:
                strategy_types[stype] = 0
            strategy_types[stype] += exposure_by_strategy.get(strat_id, 0)
        
        sector_concentration = 0
        if total_exposure > 0 and strategy_types:
            max_type_exposure = max(strategy_types.values())
            sector_concentration = (max_type_exposure / total_exposure) * 100
        
        # Calculate current and max drawdown
        max_dd = 0
        current_dd = 0
        if values:
            peak = values[0]
            for v in values:
                if v > peak:
                    peak = v
                dd = (v - peak) / peak if peak > 0 else 0
                if dd < max_dd:
                    max_dd = dd
            current_dd = (values[-1] - peak) / peak if peak > 0 else 0
        
        # Risk alerts
        alerts = []
        if var_95 and var_95 < risk_limits["max_var_threshold"]:
            alerts.append({"severity": "high", "message": f"VaR ({var_95:.1f}%) exceeds {risk_limits['max_var_threshold']}% threshold"})
        
        if max_dd * 100 < risk_limits["max_drawdown_threshold"]:
            alerts.append({"severity": "high", "message": f"Max drawdown ({max_dd*100:.1f}%) exceeds {risk_limits['max_drawdown_threshold']}% threshold"})
        
        # Max position concentration
        current_max = max(exposure_by_strategy.values()) / total_exposure * 100 if total_exposure > 0 and exposure_by_strategy else 0
        if current_max > risk_limits["max_position_pct"]:
            alerts.append({"severity": "medium", "message": f"Position concentration ({current_max:.1f}%) exceeds {risk_limits['max_position_pct']}% limit"})
        
        if margin_utilization > 80:
            alerts.append({"severity": "high", "message": f"Margin utilization ({margin_utilization:.1f}%) is critically high"})
        elif margin_utilization > 50:
            alerts.append({"severity": "medium", "message": f"Margin utilization ({margin_utilization:.1f}%) is elevated"})
        
        if regime == "Volatile":
            alerts.append({"severity": "medium", "message": "Market regime is VOLATILE - increased risk"})
        
        return {
            "var_95": var_95,
            "var_99": var_99,
            "cvar_95": cvar_95,
            "total_exposure": total_exposure,
            "exposure_by_strategy": exposure_by_strategy,
            "greeks": greeks,
            "alerts": alerts,
            "max_position_pct": risk_limits["max_position_pct"],
            "current_max_position": current_max,
            "sector_concentration": sector_concentration,
            "strategy_type_exposure": strategy_types,
            "margin": {
                "used": margin_used,
                "available": margin_available,
                "buying_power": buying_power,
                "utilization": margin_utilization
            },
            "regime": {
                "current": regime,
                "confidence": regime_confidence
            },
            "drawdown": {
                "current": current_dd * 100,
                "max": max_dd * 100
            },
            "limits": risk_limits
        }
    except Exception as e:
        logger.error(f"Failed to calculate risk: {e}")
        return {"error": str(e)}

# Monte Carlo simulation cache
monte_carlo_cache = {
    "last_updated": None,
    "results": None,
    "update_interval_hours": 24  # Recalculate every 24 hours
}

@app.get("/api/montecarlo")
@app.get("/montecarlo")
def get_monte_carlo(force_refresh: bool = False):
    """Returns Monte Carlo risk of ruin simulation results."""
    global monte_carlo_cache
    
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    from datetime import datetime, timedelta
    
    now = datetime.now()
    should_recalculate = (
        force_refresh or
        monte_carlo_cache["last_updated"] is None or
        (now - monte_carlo_cache["last_updated"]) > timedelta(hours=monte_carlo_cache["update_interval_hours"])
    )
    
    if not should_recalculate and monte_carlo_cache["results"] is not None:
        return monte_carlo_cache["results"]
    
    try:
        history = engine.equity_history
        if len(history) < 10:
            return {"error": "Not enough data for Monte Carlo simulation", "min_required": 10, "current": len(history)}
        
        values = [h['value'] for h in history]
        returns = list(np.diff(values) / values[:-1])
        
        if len(returns) < 5:
            return {"error": "Not enough return data"}
        
        initial_capital = values[-1]
        num_simulations = 1000
        num_trades = min(252, len(returns) * 2)  # 1 year or 2x history
        
        # Run Monte Carlo simulation
        random_returns = np.random.choice(returns, size=(num_simulations, num_trades), replace=True)
        cum_returns = np.cumprod(1 + random_returns, axis=1)
        equity_curves = initial_capital * cum_returns
        
        # Add starting point
        start_col = np.full((num_simulations, 1), initial_capital)
        simulations = np.hstack([start_col, equity_curves])
        
        final_values = simulations[:, -1]
        
        # Risk of ruin at different thresholds
        ruin_50 = np.sum(final_values < initial_capital * 0.5) / num_simulations * 100
        ruin_25 = np.sum(final_values < initial_capital * 0.75) / num_simulations * 100
        ruin_10 = np.sum(final_values < initial_capital * 0.9) / num_simulations * 100
        
        # Percentile cone (downsampled for charting)
        step = max(1, num_trades // 50)
        time_points = list(range(0, num_trades + 1, step))
        percentile_5 = np.percentile(simulations, 5, axis=0)[::step].tolist()
        percentile_25 = np.percentile(simulations, 25, axis=0)[::step].tolist()
        percentile_50 = np.percentile(simulations, 50, axis=0)[::step].tolist()
        percentile_75 = np.percentile(simulations, 75, axis=0)[::step].tolist()
        percentile_95 = np.percentile(simulations, 95, axis=0)[::step].tolist()
        
        # Sample paths (10 random simulations for visual)
        sample_indices = np.random.choice(num_simulations, min(10, num_simulations), replace=False)
        sample_paths = simulations[sample_indices, ::step].tolist()
        
        # Max drawdown distribution
        max_drawdowns = []
        for sim in simulations:
            peak = sim[0]
            max_dd = 0
            for v in sim:
                if v > peak:
                    peak = v
                dd = (v - peak) / peak
                if dd < max_dd:
                    max_dd = dd
            max_drawdowns.append(max_dd * 100)
        
        results = {
            "initial_capital": initial_capital,
            "num_simulations": num_simulations,
            "num_trades": num_trades,
            "risk_of_ruin": {
                "50_percent": round(ruin_50, 2),
                "25_percent": round(ruin_25, 2),
                "10_percent": round(ruin_10, 2)
            },
            "final_equity": {
                "median": round(float(np.median(final_values)), 2),
                "mean": round(float(np.mean(final_values)), 2),
                "worst_case_5pct": round(float(np.percentile(final_values, 5)), 2),
                "best_case_95pct": round(float(np.percentile(final_values, 95)), 2)
            },
            "max_drawdown": {
                "average": round(float(np.mean(max_drawdowns)), 2),
                "worst": round(float(np.min(max_drawdowns)), 2)
            },
            "cone": {
                "time_points": time_points,
                "p5": percentile_5,
                "p25": percentile_25,
                "p50": percentile_50,
                "p75": percentile_75,
                "p95": percentile_95
            },
            "sample_paths": sample_paths,
            "last_updated": now.isoformat(),
            "update_interval_hours": monte_carlo_cache["update_interval_hours"]
        }
        
        monte_carlo_cache["results"] = results
        monte_carlo_cache["last_updated"] = now
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to run Monte Carlo: {e}")
        return {"error": str(e)}

@app.put("/api/montecarlo/settings")
def update_monte_carlo_settings(interval_hours: int = 24):
    """Update Monte Carlo recalculation interval."""
    global monte_carlo_cache
    if interval_hours < 1:
        raise HTTPException(status_code=400, detail="Interval must be at least 1 hour")
    monte_carlo_cache["update_interval_hours"] = interval_hours
    return {"update_interval_hours": interval_hours}

@app.get("/api/positions")
@app.get("/positions")
def get_positions():
    """Returns all open positions with P&L data for heatmap."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    try:
        positions = engine.eh.get_all_positions()
        
        if not positions:
            return {"positions": [], "summary": {"total_pnl": 0, "total_value": 0, "position_count": 0}}
        
        position_list = []
        total_pnl = 0
        total_value = 0
        
        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            market_value = float(pos.market_value)
            cost_basis = float(pos.cost_basis)
            unrealized_pl = float(pos.unrealized_pl)
            unrealized_plpc = float(pos.unrealized_plpc) * 100
            current_price = float(pos.current_price)
            avg_entry_price = float(pos.avg_entry_price)
            side = pos.side
            
            # Try to find owning strategy
            owning_strategy = None
            for strat_id, strategy in engine.sm.strategies.items():
                if hasattr(strategy, 'symbols') and symbol in strategy.symbols:
                    owning_strategy = strat_id
                    break
            
            position_list.append({
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "unrealized_pnl": unrealized_pl,
                "unrealized_pnl_pct": round(unrealized_plpc, 2),
                "current_price": current_price,
                "avg_entry_price": avg_entry_price,
                "strategy": owning_strategy
            })
            
            total_pnl += unrealized_pl
            total_value += market_value
        
        # Sort by absolute P&L magnitude (largest first)
        position_list.sort(key=lambda x: abs(x['unrealized_pnl']), reverse=True)
        
        return {
            "positions": position_list,
            "summary": {
                "total_pnl": round(total_pnl, 2),
                "total_value": round(total_value, 2),
                "position_count": len(position_list)
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
        return {"positions": [], "summary": {"total_pnl": 0, "total_value": 0, "position_count": 0}, "error": str(e)}

@app.get("/api/history")
@app.get("/history")
def get_history():
    if not engine:
        return []
    return engine.equity_history

@app.get("/api/logs")
@app.get("/logs")
def get_logs():
    try:
        log_file = "trading_bot.log"
        if not os.path.exists(log_file):
             return {"logs": "Log file not found."}
        
        # Read last 100 lines
        with open(log_file, "r") as f:
            lines = f.readlines()
            return {"logs": "".join(lines[-100:])}
    except Exception as e:
        return {"logs": f"Error reading logs: {str(e)}"}

# --- Serve Frontend (Must be last) ---
# Mount the 'dist' folder (built frontend) to root
# We check if the folder exists to avoid crashing in dev mode without build
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
else:
    logger.warning(f"Frontend build not found at {frontend_path}. API only mode.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=True)