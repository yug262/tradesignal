import httpx
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any

import db_models
from database import get_db
from models import NewsArticleRef, PaginatedNewsResponse

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
    query = db.query(db_models.NewsArticle)
    
    if min_impact > 0:
        query = query.filter(db_models.NewsArticle.impact_score >= min_impact)
    
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
    cfg = db.query(db_models.DBSystemConfig).first()
    if not cfg:
        from routers.config import _default_config
        defaults = _default_config()
        cfg = db_models.DBSystemConfig(**defaults.model_dump())
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    url = cfg.news_endpoint_url
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            json_res = response.json()
            
            # Check for different possible keys for articles
            articles_list = []
            if isinstance(json_res, list):
                articles_list = json_res
            elif isinstance(json_res, dict):
                articles_list = json_res.get("data", json_res.get("items", json_res.get("articles", [])))
            
            saved_count = 0
            skipped_count = 0
            
            from datetime import datetime
            
            for item in articles_list:
                if not isinstance(item, dict): continue
                
                # Extract ID as string
                item_id = str(item.get("id", ""))
                if not item_id: continue
                    
                impact_score = float(item.get("impact_score") or 0)
                # Lowered threshold to 0.0 to ensure data flows during setup
                if impact_score < 4: 
                    skipped_count += 1
                    continue
                
                # Map analysis data
                raw_data = item.get("analysis_data") or item.get("raw_analysis_data", {})
                
                # Convert ISO timestamp to milliseconds
                import time
                pub_at = item.get("published") or item.get("published_at")
                pub_at_ms = int(time.time() * 1000) # Default to now
                if pub_at:
                    try:
                        # Handle ISO format with offset
                        dt = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
                        pub_at_ms = int(dt.timestamp() * 1000)
                    except Exception:
                        pass
                
                # Convert analyzed_at if present
                ana_at = item.get("analyzed_at")
                ana_at_ms = None
                if ana_at:
                    try:
                        dt = datetime.fromisoformat(ana_at.replace("Z", "+00:00"))
                        ana_at_ms = int(dt.timestamp() * 1000)
                    except Exception:
                        ana_at_ms = None

                # Extract affected symbols from dict if needed
                affected = item.get("affected_symbols", [])
                if not affected and "affected_stocks" in item:
                    stocks = item["affected_stocks"]
                    if isinstance(stocks, dict):
                        affected = stocks.get("direct", []) + stocks.get("indirect", [])

                existing = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.id == item_id).first()
                if not existing:
                    new_article = db_models.NewsArticle(
                        id=item_id,
                        title=item.get("title", "No Title"),
                        description=item.get("description", ""),
                        source=item.get("source", "Unknown"),
                        published_at=pub_at_ms,
                        analyzed_at=ana_at_ms,
                        image_url=item.get("image_url"),
                        impact_score=impact_score,
                        impact_summary=item.get("impact_summary", ""),
                        executive_summary=item.get("executive_summary", ""),
                        news_category=item.get("news_category", ""),
                        news_relevance=item.get("news_relevance", ""),
                        affected_symbols=affected,
                        raw_analysis_data=raw_data,
                        processing_status=item.get("processing_status", "analyzed" if item.get("analyzed") else "pending")
                    )
                    db.add(new_article)
                    saved_count += 1
            
            db.commit()
            print(f"DEBUG: Live fetch. Processed {len(articles_list)} items. Saved {saved_count} new articles.")
            return {"status": "success", "message": f"Ingested {saved_count} new articles."}
    except httpx.ConnectError:
        print("ERROR: Could not connect to the news endpoint (DNS or connection failure).")
        raise HTTPException(
            status_code=503, 
            detail="News source unreachable. Please check the endpoint URL."
        )
    except httpx.HTTPStatusError as e:
        print(f"ERROR: News source returned an error: {e.response.status_code}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"News source error: {e.response.status_code}"
        )
    except Exception as e:
        print(f"ERROR: Fetch failed: {str(e)[:100]}")
        raise HTTPException(status_code=500, detail=f"Fetch operation failed: {str(e)[:50]}")
