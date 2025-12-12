from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import logging
from src.engine import TradingEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Engine Instance
engine = TradingEngine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Trading Engine...")
    engine.start()
    yield
    # Shutdown
    logger.info("Stopping Trading Engine...")
    engine.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/status")
def get_status():
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
    status = engine.get_status()
    return status["strategies"]

@app.post("/strategies/{strategy_id}/toggle")
def toggle_strategy(strategy_id: str):
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
