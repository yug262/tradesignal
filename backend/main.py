from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys

# ── Agent logging setup ───────────────────────────────────────────────────────
# Uvicorn (especially with reload=True) configures the root logger before
# main.py runs, making logging.basicConfig() a no-op.
# Fix: give each agent logger its own StreamHandler(stdout) + propagate=False,
# so they bypass the root logger entirely and always print to the terminal.

_LOG_FMT = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def _setup_agent_logger(name: str) -> None:
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in lg.handlers):
        _h = logging.StreamHandler(sys.stdout)
        _h.setFormatter(_LOG_FMT)
        lg.addHandler(_h)
    lg.propagate = False  # Don't bubble up to Uvicorn's root logger

for _agent_logger in [
    "agent.confirmation_agent",
    "agent.gemini_confirmer",
    "agent.technical_analysis_agent",
    "agent.gemini_technical_analyzer",
    "agent.execution_agent",
    "agent.gemini_executor",
    "agent.live_news_agent",
    "agent.risk_monitor",
    "agent.signal_generator",
    "agent.paper_trading_engine",
]:
    _setup_agent_logger(_agent_logger)

# Silence noisy third-party loggers (keep access logs ON so we see API calls)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)   # ← show GET/POST hits
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)

from models import SystemConfig, ProcessingState
from routers import news, config, dashboard, stocks, agent, paper_trading
import database
import db_models

# Create tables
db_models.Base.metadata.create_all(bind=database.engine)

# ─── In-memory application state (volatile/cached) ────────────────────────────

from store import _store as app_state


# ─── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="TradeSignal API",
    description="Trading signal news intelligence backend with PostgreSQL",
    version="1.1.0",
)

# CORS — allow the Vite dev server and any local origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(news.router)
app.include_router(config.router)
app.include_router(dashboard.router)
app.include_router(stocks.router)
app.include_router(agent.router)
app.include_router(paper_trading.router)


# ─── Lifecycle events ─────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    from agent.scheduler import init_scheduler
    init_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    from agent.scheduler import shutdown_scheduler
    shutdown_scheduler()


@app.get("/api/health")
def health_check():
    db_status = "connected"
    try:
        from sqlalchemy import text
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "ok", 
        "version": "2.1.0", 
        "database": db_status, 
        "agent": "active"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info", access_log=True)
