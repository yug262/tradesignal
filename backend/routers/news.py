"""News API router — merged filter + pagination endpoint."""

import httpx
import json
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from database import get_db
import db_models
from models import NewsArticleRef

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
    db: Session = Depends(get_db)
):
    """Return a paginated, optionally filtered list of news articles sorted by published_at desc."""
    query = db.query(db_models.NewsArticle)

    # Apply filters
    if symbol:
        query = query.filter(db_models.NewsArticle.affected_symbols.any(symbol))
    if category:
        query = query.filter(db_models.NewsArticle.news_category == category)
    if min_impact is not None:
        query = query.filter(db_models.NewsArticle.impact_score >= min_impact)

    # Count total
    total = query.count()
    
    # Sort and paginate
    articles = query.order_by(db_models.NewsArticle.published_at.desc()) \
                    .offset(page * page_size) \
                    .limit(page_size) \
                    .all()

    items = []
    for a in articles:
        # Convert DB model to Pydantic
        items.append({
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "source": a.source,
            "published_at": a.published_at,
            "analyzed_at": a.analyzed_at,
            "image_url": a.image_url,
            "impact_score": a.impact_score,
            "impact_summary": a.impact_summary,
            "executive_summary": a.executive_summary,
            "news_relevance": a.news_relevance,
            "news_category": a.news_category,
            "affected_symbols": a.affected_symbols,
            "processing_status": a.processing_status,
            "raw_analysis_data": a.raw_analysis_data if isinstance(a.raw_analysis_data, str) else json.dumps(a.raw_analysis_data)
        })

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": (page + 1) * page_size < total,
    }


@router.get("/count")
def get_total_news_count(db: Session = Depends(get_db)):
    """Return total count of stored articles."""
    count = db.query(db_models.NewsArticle).count()
    return {"count": count}


@router.get("/{article_id}")
def get_news_by_id(article_id: str, db: Session = Depends(get_db)):
    """Lookup a single article by id."""
    article = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.id == article_id).first()
    if article is None:
        return None
    
    return {
        "id": article.id,
        "title": article.title,
        "description": article.description,
        "source": article.source,
        "published_at": article.published_at,
        "analyzed_at": article.analyzed_at,
        "image_url": article.image_url,
        "impact_score": article.impact_score,
        "impact_summary": article.impact_summary,
        "executive_summary": article.executive_summary,
        "news_relevance": article.news_relevance,
        "news_category": article.news_category,
        "affected_symbols": article.affected_symbols,
        "processing_status": article.processing_status,
        "raw_analysis_data": article.raw_analysis_data if isinstance(article.raw_analysis_data, str) else json.dumps(article.raw_analysis_data)
    }


@router.post("/fetch")
def fetch_news(db: Session = Depends(get_db)):
    """Trigger a news fetch (loads mock data or fetches from live endpoint)."""
    state = _get_store()

    if state.config.use_mock_data:
        from mock_data import get_mock_articles
        articles_data = get_mock_articles()
        count = 0
        for art in articles_data:
            # Filter by impact score >= 5
            if art.impact_score < 5.0:
                continue

            # Check if exists
            existing = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.id == art.id).first()
            if not existing:
                db_art = db_models.NewsArticle(
                    id=art.id,
                    title=art.title,
                    description=art.description,
                    source=art.source,
                    published_at=art.published_at,
                    analyzed_at=art.analyzed_at,
                    image_url=art.image_url,
                    impact_score=art.impact_score,
                    impact_summary=art.impact_summary,
                    executive_summary=art.executive_summary,
                    news_relevance=art.news_relevance,
                    news_category=art.news_category,
                    affected_symbols=art.affected_symbols,
                    processing_status=art.processing_status,
                    raw_analysis_data=art.raw_analysis_data
                )
                db.add(db_art)
                count += 1
        db.commit()
        return {"message": f"Loaded {count} new mock articles (Impact >= 5.0) to database"}
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
                    # Filter by impact score >= 5
                    impact_score = float(item.get("impact_score") or 0.0)
                    if impact_score < 5.0:
                        continue

                    article_id = str(item.get("id"))
                    # Check if exists
                    existing = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.id == article_id).first()
                    if existing:
                        continue

                    # Map external fields to NewsArticle
                    affected_stocks = item.get("affected_stocks", {})
                    symbols = list(set(
                        affected_stocks.get("direct", []) + 
                        affected_stocks.get("indirect", [])
                    ))
                    
                    db_art = db_models.NewsArticle(
                        id=article_id,
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        source=item.get("source", ""),
                        published_at=iso_to_ms(item.get("published")),
                        analyzed_at=iso_to_ms(item.get("analyzed_at")),
                        image_url=item.get("image_url"),
                        impact_score=impact_score,
                        impact_summary=item.get("impact_summary") or "",
                        executive_summary=item.get("executive_summary") or "",
                        news_relevance=item.get("news_relevance", "unknown"),
                        news_category=item.get("news_category", "other"),
                        affected_symbols=symbols,
                        processing_status="analyzed" if item.get("analyzed") else "new",
                        raw_analysis_data=item.get("analysis_data") # SQLAlchemy handles JSON
                    )
                    db.add(db_art)
                    count += 1
                
                db.commit()
                return {"message": f"Successfully fetched and saved {count} new articles to database"}
        except Exception as e:
            db.rollback()
            return {"message": f"Error fetching from live endpoint: {str(e)}"}
