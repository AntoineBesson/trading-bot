from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import logging
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

@app.get("/strategies")
def get_strategies():
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    status = engine.get_status()
    return status["strategies"]

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=True)

@app.post("/strategies/{strategy_id}/stop")
def stop_strategy(strategy_id: str):
    """Pauses a specific strategy."""
    success = engine.sm.stop_strategy(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "stopped", "id": strategy_id}

@app.post("/strategies/{strategy_id}/start")
def start_strategy(strategy_id: str):
    """Resumes a specific strategy."""
    success = engine.sm.start_strategy(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "started", "id": strategy_id}