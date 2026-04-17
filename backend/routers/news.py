"""News API router — merged filter + pagination endpoint."""

import httpx
import json
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api/news", tags=["news"])


def _get_store():
    from main import app_state
    return app_state


def iso_to_ms(iso_str: Optional[str]) -> int:
    if not iso_str:
        return 0
    try:
        # Handle the format like "2026-04-17T16:00:00+05:30"
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


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
    """Trigger a news fetch (loads mock data or fetches from live endpoint)."""
    state = _get_store()
    from models import NewsArticleRef

    if state.config.use_mock_data:
        from mock_data import get_mock_articles
        articles = get_mock_articles()
        for art in articles:
            state.news_store[art.id] = art
        return {"message": f"Loaded {len(articles)} mock articles"}
    else:
        url = state.config.news_endpoint_url
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
                
                external_articles = data.get("data", [])
                count = 0
                for item in external_articles:
                    # Filter by relevance: only "High Useful" and "Useful"
                    relevance = item.get("news_relevance", "unknown")
                    if relevance not in ["High Useful", "Useful"]:
                        continue

                    # Map external fields to NewsArticleRef
                    affected_stocks = item.get("affected_stocks", {})
                    symbols = list(set(
                        affected_stocks.get("direct", []) + 
                        affected_stocks.get("indirect", [])
                    ))
                    
                    art = NewsArticleRef(
                        id=str(item.get("id")),
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        source=item.get("source", ""),
                        published_at=iso_to_ms(item.get("published")),
                        analyzed_at=iso_to_ms(item.get("analyzed_at")),
                        image_url=item.get("image_url"),
                        impact_score=float(item.get("impact_score") or 0.0),
                        impact_summary=item.get("impact_summary") or "",
                        executive_summary=item.get("executive_summary") or "",
                        news_relevance=item.get("news_relevance", "unknown"),
                        news_category=item.get("news_category", "other"),
                        affected_symbols=symbols,
                        processing_status="analyzed" if item.get("analyzed") else "new",
                        raw_analysis_data=json.dumps(item.get("analysis_data"))
                    )
                    state.news_store[art.id] = art
                    count += 1
                
                return {"message": f"Successfully fetched {count} articles from live endpoint"}
        except Exception as e:
            return {"message": f"Error fetching from live endpoint: {str(e)}"}
