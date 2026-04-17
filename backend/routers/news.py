"""News API router — merged filter + pagination endpoint."""

from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter(prefix="/api/news", tags=["news"])


def _get_store():
    from main import app_state
    return app_state


@router.get("")
def get_news(
    page: int = Query(0, ge=0),
    page_size: int = Query(20, ge=1, le=100),
    symbol: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    min_impact: Optional[float] = Query(None),
):
    """Return a paginated, optionally filtered list of news articles sorted by published_at desc."""
    state = _get_store()
    articles = list(state.news_store.values())

    # Apply filters
    if symbol:
        articles = [a for a in articles if symbol in a.affected_symbols]
    if category:
        articles = [a for a in articles if a.news_category == category]
    if min_impact is not None:
        articles = [a for a in articles if a.impact_score >= min_impact]

    # Sort by published_at descending
    articles.sort(key=lambda a: a.published_at, reverse=True)

    total = len(articles)
    start = page * page_size
    if start >= total:
        return {"items": [], "page": page, "page_size": page_size, "total": total, "has_more": False}

    end = min(start + page_size, total)
    items = articles[start:end]
    return {
        "items": [a.model_dump() for a in items],
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": end < total,
    }


@router.get("/count")
def get_total_news_count():
    """Return total count of stored articles."""
    state = _get_store()
    return {"count": len(state.news_store)}


@router.get("/{article_id}")
def get_news_by_id(article_id: str):
    """Lookup a single article by id."""
    state = _get_store()
    article = state.news_store.get(article_id)
    if article is None:
        return None
    return article.model_dump()


@router.post("/fetch")
def fetch_news():
    """Trigger a news fetch (loads mock data or returns live-endpoint placeholder)."""
    state = _get_store()
    if state.config.use_mock_data:
        from mock_data import get_mock_articles
        articles = get_mock_articles()
        for art in articles:
            state.news_store[art.id] = art
        return {"message": f"Loaded {len(articles)} mock articles"}
    else:
        return {"message": "Live endpoint not configured"}
