"""FastAPI backend — replaces the Motoko/ICP actor.

Run with:  uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import SystemConfig, ProcessingState
from routers import news, config, dashboard
import database
import db_models

# Create tables
db_models.Base.metadata.create_all(bind=database.engine)

# ─── In-memory application state (volatile/cached) ────────────────────────────

class AppState:
    """Global mutable state container — some parts now backed by Postgres."""

    def __init__(self):
        # We still keep these for quick access or default values if DB is empty
        self.config = SystemConfig()
        self.proc_state = ProcessingState()


app_state = AppState()


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

@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.1.0", "database": "connected"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
