"""FastAPI backend — replaces the Motoko/ICP actor.

Run with:  uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import SystemConfig, ProcessingState
from routers import news, config, dashboard, stocks, agent
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
    return {"status": "ok", "version": "2.0.0", "database": "connected", "agent": "active"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
