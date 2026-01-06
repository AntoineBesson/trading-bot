from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
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
    """Returns risk metrics."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    try:
        history = engine.equity_history
        values = [h['value'] for h in history] if history else []
        returns = np.diff(values) / values[:-1] if len(values) > 1 else []
        
        # VaR (95% confidence)
        var_95 = float(np.percentile(returns, 5)) * 100 if len(returns) > 5 else None
        
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
        
        # Risk alerts
        alerts = []
        if var_95 and var_95 < -5:
            alerts.append({"severity": "high", "message": "VaR exceeds 5% daily risk threshold"})
        
        # Max position concentration
        max_position_pct = 10  # Limit
        current_max = max(exposure_by_strategy.values()) / total_exposure * 100 if total_exposure > 0 else 0
        if current_max > max_position_pct:
            alerts.append({"severity": "medium", "message": f"Position concentration ({current_max:.1f}%) exceeds limit"})
        
        return {
            "var_95": var_95,
            "total_exposure": total_exposure,
            "exposure_by_strategy": exposure_by_strategy,
            "greeks": greeks,
            "alerts": alerts,
            "max_position_pct": max_position_pct,
            "current_max_position": current_max,
            "sector_concentration": 0  # Would need sector data
        }
    except Exception as e:
        logger.error(f"Failed to calculate risk: {e}")
        return {"error": str(e)}

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