import httpx
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any

import db_models
from database import get_db
from models import NewsArticleRef, PaginatedNewsResponse
from store import _get_store

router = APIRouter(prefix="/api/news", tags=["news"])

@router.get("", response_model=PaginatedNewsResponse)
def get_news(
    page: int = 0, 
    page_size: int = 20, 
    symbol: str = None, 
    category: str = None,
    min_impact: float = 5.0,
    db: Session = Depends(get_db)
):
    """Get news articles with pagination and filtering."""
    query = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.impact_score >= min_impact)
    
    if symbol:
        query = query.filter(db_models.NewsArticle.affected_symbols.any(symbol))
    if category:
        query = query.filter(db_models.NewsArticle.news_category == category)
        
    total = query.count()
    articles = query.order_by(db_models.NewsArticle.published_at.desc())\
                    .offset(page * page_size)\
                    .limit(page_size)\
                    .all()
                    
    has_more = total > (page + 1) * page_size
    
    return {
        "items": articles,
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": has_more
    }

@router.get("/grouped")
def get_news_grouped(db: Session = Depends(get_db)):
    """Return news articles grouped by stock symbols."""
    articles = db.query(db_models.NewsArticle).order_by(db_models.NewsArticle.published_at.desc()).all()
    
    grouped = {}
    for a in articles:
        data = {
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "source": a.source,
            "published_at": a.published_at,
            "analyzed_at": a.analyzed_at,
            "impact_score": a.impact_score,
            "impact_summary": a.impact_summary,
            "executive_summary": a.executive_summary,
            "news_category": a.news_category,
            "news_relevance": a.news_relevance,
            "affected_symbols": a.affected_symbols,
            "raw_analysis_data": a.raw_analysis_data,
            "processing_status": a.processing_status
        }
        
        symbols = a.affected_symbols if a.affected_symbols else ["GENERAL"]
        for sym in symbols:
            if sym not in grouped:
                grouped[sym] = []
            grouped[sym].append(data)
            
    print(f"DEBUG: Grouped {len(articles)} articles into {len(grouped)} groups.")
    return grouped

@router.get("/{news_id}", response_model=NewsArticleRef)
def get_news_by_id(news_id: str, db: Session = Depends(get_db)):
    """Get a single news article by ID."""
    article = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.id == news_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="News article not found")
    return article

@router.post("/fetch")
def fetch_news(db: Session = Depends(get_db)):
    """Trigger a news fetch (loads mock data or fetches from live endpoint)."""
    state = _get_store()

    if state.config.use_mock_data:
        from mock_data import get_mock_articles
        articles_data = get_mock_articles()
        
        saved_count = 0
        skipped_count = 0
        for art in articles_data:
            if art.impact_score < 5.0:
                skipped_count += 1
                continue

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
                saved_count += 1
        db.commit()
        print(f"DEBUG: Mock fetch. Saved {saved_count} articles.")
        return {"message": f"Loaded {saved_count} new mock articles."}
    else:
        url = state.config.news_endpoint_url
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url)
                response.raise_for_status()
                json_res = response.json()
                
                articles_list = json_res if isinstance(json_res, list) else json_res.get("items", json_res.get("articles", []))
                
                saved_count = 0
                skipped_count = 0
                for item in articles_list:
                    if not isinstance(item, dict): continue
                        
                    impact_score = float(item.get("impact_score", 0))
                    if impact_score < 5.0:
                        skipped_count += 1
                        continue
                    
                    raw_data = item.get("raw_analysis_data", {})

                    existing = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.id == item["id"]).first()
                    if not existing:
                        new_article = db_models.NewsArticle(
                            id=item["id"],
                            title=item["title"],
                            description=item.get("description", ""),
                            source=item["source"],
                            published_at=item["published_at"],
                            analyzed_at=item.get("analyzed_at"),
                            impact_score=impact_score,
                            impact_summary=item.get("impact_summary", ""),
                            executive_summary=item.get("executive_summary", ""),
                            news_category=item.get("news_category", ""),
                            news_relevance=item.get("news_relevance", ""),
                            affected_symbols=item.get("affected_symbols", []),
                            raw_analysis_data=raw_data,
                            processing_status=item.get("processing_status", "analyzed")
                        )
                        db.add(new_article)
                        saved_count += 1
                
                db.commit()
                print(f"DEBUG: Live fetch. Saved {saved_count} articles (skipped {skipped_count} low-impact).")
                return {"status": "success", "message": f"Saved {saved_count} new articles."}
        except Exception as e:
            print(f"ERROR: Fetch failed: {str(e)[:100]}")
            raise HTTPException(status_code=500, detail="Fetch operation failed.")
