"""Pydantic models mirroring the Motoko types/trading.mo definitions.

Timestamps are in MILLISECONDS (epoch ms) for safe JS number handling.
"""

from pydantic import BaseModel
from typing import Optional


class NewsArticleRef(BaseModel):
    id: str
    title: str
    description: str
    source: str
    published_at: int          # milliseconds since epoch
    analyzed_at: int           # milliseconds since epoch
    image_url: Optional[str] = None
    impact_score: float        # 1.0–10.0
    impact_summary: str
    executive_summary: str
    news_relevance: str        # "high" | "medium" | "low"
    news_category: str         # "earnings" | "merger" | "regulatory" | "macro" | "product"
    affected_symbols: list[str]
    processing_status: str     # "pending" | "processed" | "skipped"
    raw_analysis_data: str     # JSON string


class SystemConfig(BaseModel):
    capital: float = 100_000.0
    risk_per_trade_pct: float = 1.0
    max_open_positions: int = 5
    max_daily_loss_pct: float = 3.0
    min_rr: float = 1.5
    news_endpoint_url: str = "https://api.example.com/news"
    polling_interval_mins: int = 5
    use_mock_data: bool = True
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
