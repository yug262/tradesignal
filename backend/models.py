"""Pydantic models mirroring the Motoko types/trading.mo definitions.

Timestamps are in MILLISECONDS (epoch ms) for safe JS number handling.
"""

from pydantic import BaseModel
from typing import Optional, Any, List


class NewsArticleRef(BaseModel):
    id: str
    title: str
    description: Optional[str] = ""
    source: str
    published_at: int
    analyzed_at: Optional[int] = None
    image_url: Optional[str] = None
    impact_score: float = 0.0
    impact_summary: Optional[str] = ""
    executive_summary: Optional[str] = ""
    news_relevance: Optional[str] = "low"
    news_category: Optional[str] = "other"
    affected_symbols: Optional[List[str]] = []
    processing_status: str
    raw_analysis_data: Any = None


class SystemConfig(BaseModel):
    capital: float = 100_000.0
    risk_per_trade_pct: float = 1.0
    max_open_positions: int = 5
    max_daily_loss_pct: float = 3.0
    min_rr: float = 1.5
    news_endpoint_url: str = "https://destiny-luxury-douche.ngrok-free.dev/api/indian_news?limit=1000&today_only=false&exclude_noisy=false&analyzed_only=false&offset=0"
    polling_interval_mins: int = 5
    processing_mode: str = "pre_market"


class ProcessingState(BaseModel):
    last_processed_article_id: Optional[str] = None
    last_poll_timestamp: int = 0   # milliseconds since epoch
    total_articles_processed: int = 0
    current_mode: str = "pre_market"
    is_polling_active: bool = False
    articles_in_queue: int = 0


class DashboardSummary(BaseModel):
    total_articles_consumed: int = 0
    articles_processed_today: int = 0
    pending_candidates: int = 0
    active_opportunities: int = 0
    no_trade_count: int = 0
    system_mode: str = "pre_market"
    last_refresh: int = 0          # milliseconds since epoch
    endpoint_status: str = "mock"  # "connected" | "mock" | "error"


class PaginatedNewsResponse(BaseModel):
    items: list[NewsArticleRef]
    page: int
    page_size: int
    total: int
    has_more: bool
