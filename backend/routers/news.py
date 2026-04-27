import httpx
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import time
from datetime import datetime, timezone

import db_models
from database import get_db
from models import NewsArticleRef, PaginatedNewsResponse

router = APIRouter(prefix="/api/news", tags=["news"])

def _parse_timestamp(item: dict, keys: List[str], default_now: bool = True) -> Optional[int]:
    """Robustly parse timestamp from various field names and formats."""
    val = None
    for k in keys:
        if k in item and item[k] is not None:
            val = item[k]
            break
            
    if val is None:
        return int(time.time() * 1000) if default_now else None
        
    # Case 1: Already an integer/float (assume seconds or ms)
    if isinstance(val, (int, float)):
        if val > 1e12: # Milliseconds
            return int(val)
        if val > 1e8: # Likely seconds
            return int(val * 1000)
        return int(time.time() * 1000) if default_now else None
        
    # Case 2: String
    if isinstance(val, str):
        # Try numeric string
        try:
            num = float(val)
            if num > 1e12: return int(num)
            if num > 1e8: return int(num * 1000)
        except ValueError:
            pass
            
        # Try ISO format
        try:
            # handle 'Z' or '+0000' or space
            clean_val = val.replace("Z", "+00:00").replace(" ", "T")
            dt = datetime.fromisoformat(clean_val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            parsed = int(dt.timestamp() * 1000)
            # Log successful parse
            with open("news_parse_log.txt", "a") as f:
                f.write(f"SUCCESS: {val} -> {parsed} (ISO)\n")
            return parsed
        except Exception as e:
            with open("news_parse_log.txt", "a") as f:
                f.write(f"ERROR ISO: {val} -> {e}\n")
            pass
            
        # Try common formats
        for fmt in ["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"]:
            try:
                dt = datetime.strptime(val, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed = int(dt.timestamp() * 1000)
                with open("news_parse_log.txt", "a") as f:
                    f.write(f"SUCCESS: {val} -> {parsed} (STRPTIME {fmt})\n")
                return parsed
            except Exception:
                continue
                
    fallback = int(time.time() * 1000) if default_now else None
    with open("news_parse_log.txt", "a") as f:
        f.write(f"FALLBACK: {val} -> {fallback}\n")
    return fallback

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
            "processing_status": a.processing_status,
            "link": a.link,
            "market_bias": a.market_bias,
            "signal_bucket": a.signal_bucket,
            "primary_symbol": a.primary_symbol,
            "affected_sectors": a.affected_sectors,
            "affected_stocks": a.affected_stocks,
            "raw_full_data": a.raw_full_data,
            "news_impact_level": a.news_impact_level,
            "news_reason": a.news_reason,
            "event_id": a.event_id,
            "event_title": a.event_title,
            "confidence": a.confidence,
            "horizon": a.horizon
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
            
            for i, item in enumerate(articles_list):
                if not isinstance(item, dict): continue
                if i == 0:
                    print(f"DEBUG: First article keys: {list(item.keys())}")
                    print(f"DEBUG: First article sample values: published={item.get('published')}, published_at={item.get('published_at')}, timestamp={item.get('timestamp')}")
                
                # Extract ID as string
                item_id = str(item.get("id", ""))
                if not item_id: continue
                    
                # Map analysis data
                raw_data = item.get("analysis_data") or item.get("raw_analysis_data", {})
                core_view = raw_data.get("core_view", {}) if isinstance(raw_data, dict) else {}
                
                # Intelligence Fallbacks (if top-level is null, check analysis_data.core_view)
                impact_score = float(item.get("impact_score") if item.get("impact_score") is not None else core_view.get("impact_score", 0))
                market_bias = item.get("market_bias") or core_view.get("market_bias")
                confidence = item.get("confidence") if item.get("confidence") is not None else core_view.get("confidence", 0)
                horizon = item.get("horizon") or core_view.get("horizon")
                exec_summary = item.get("executive_summary") or raw_data.get("executive_summary") or item.get("description", "")
                
                # Event fallbacks
                event_data = raw_data.get("event", {}) if isinstance(raw_data, dict) else {}
                event_id = item.get("event_id") or event_data.get("id") or item_id
                event_title = item.get("event_title") or event_data.get("title") or item.get("title")
                news_reason = item.get("news_reason") or raw_data.get("decision_trace", {}).get("tradeability_reasoning")
                
                # Filter by impact score (> 4.0)
                if impact_score < 4.0:
                    skipped_count += 1
                    continue
                
                # Robust timestamp parsing
                pub_keys = ["published", "published_at", "publishedAt", "timestamp", "pubDate", "date", "created_at"]
                pub_at_ms = _parse_timestamp(item, pub_keys)
                
                # If it's analyzed, maybe there's a better timestamp in analysis_data
                if not pub_at_ms or pub_at_ms > int(time.time() * 1000): # If missing or in future
                     pub_at_ms = _parse_timestamp(raw_data, ["analysis_timestamp_utc", "timestamp"]) or pub_at_ms
                
                # Parse analysis time
                ana_at_ms = _parse_timestamp(item, ["analyzed_at", "analyzedAt", "analyzed"], default_now=False)
                if not ana_at_ms:
                    ana_at_ms = _parse_timestamp(raw_data, ["analysis_timestamp_utc"])

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
                        executive_summary=exec_summary,
                        news_category=item.get("news_category", ""),
                        news_relevance=item.get("news_relevance", ""),
                        affected_symbols=affected,
                        raw_analysis_data=raw_data,
                        processing_status=item.get("processing_status", "analyzed" if item.get("analyzed") else "pending"),
                        link=item.get("link"),
                        market_bias=market_bias,
                        signal_bucket=item.get("signal_bucket"),
                        primary_symbol=item.get("primary_symbol"),
                        affected_sectors=item.get("affected_sectors", []),
                        affected_stocks=item.get("affected_stocks"),
                        raw_full_data=item,
                        news_impact_level=item.get("news_impact_level"),
                        news_reason=news_reason,
                        event_id=event_id,
                        event_title=event_title,
                        confidence=confidence,
                        horizon=horizon
                    )
                    db.add(new_article)
                    saved_count += 1
                else:
                    # Force update if basic data changed OR if new intelligence fields are missing (backfill)
                    needs_update = (
                        existing.published_at != pub_at_ms or 
                        not existing.raw_full_data or 
                        existing.news_reason is None or 
                        existing.horizon is None
                    )
                    
                    if needs_update:
                        if i == 0:
                            print(f"DEBUG: Updating existing article {existing.id}. New Bias: {market_bias}, Reason: {news_reason}")
                        
                        existing.published_at = pub_at_ms
                        existing.analyzed_at = ana_at_ms or existing.analyzed_at
                        existing.link = item.get("link") or existing.link
                        
                        # Use explicit 'is not None' to handle 0 or empty strings
                        if market_bias is not None: existing.market_bias = market_bias
                        if item.get("signal_bucket") is not None: existing.signal_bucket = item.get("signal_bucket")
                        if item.get("primary_symbol") is not None: existing.primary_symbol = item.get("primary_symbol")
                        if item.get("affected_sectors") is not None: existing.affected_sectors = item.get("affected_sectors")
                        if item.get("affected_stocks") is not None: existing.affected_stocks = item.get("affected_stocks")
                        
                        if item.get("news_impact_level") is not None: existing.news_impact_level = item.get("news_impact_level")
                        if news_reason is not None: existing.news_reason = news_reason
                        if event_id is not None: existing.event_id = event_id
                        if event_title is not None: existing.event_title = event_title
                        if confidence is not None: existing.confidence = confidence
                        if horizon is not None: existing.horizon = horizon
                        if impact_score is not None: existing.impact_score = impact_score
                        if exec_summary is not None: existing.executive_summary = exec_summary
                        
                        existing.raw_full_data = item
                        
                        # Also update status if it changed
                        new_status = item.get("processing_status")
                        if new_status:
                            existing.processing_status = new_status
            
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
