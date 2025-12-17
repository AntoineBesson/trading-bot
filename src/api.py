from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os
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

@app.get("/history")
def get_history():
    """Returns the equity curve data for the chart."""
    return engine.equity_history