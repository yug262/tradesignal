"""FastAPI backend — replaces the Motoko/ICP actor.

Run with:  uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import SystemConfig, ProcessingState
from routers import news, config, dashboard


# ─── In-memory application state (replaces Motoko stable state) ────────────────

class AppState:
    """Global mutable state container — equivalent of the Motoko actor state."""

    def __init__(self):
        from models import NewsArticleRef
        self.news_store: dict[str, NewsArticleRef] = {}
        self.config = SystemConfig()
        self.proc_state = ProcessingState()


app_state = AppState()


# ─── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="TradeSignal API",
    description="Trading signal news intelligence backend",
    version="1.0.0",
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
