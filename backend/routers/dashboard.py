"""Dashboard API router."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
import db_models
import time

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _get_store():
    from main import app_state
    return app_state


@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    state = _get_store()
    
    total = db.query(db_models.NewsArticle).count()

    # last 24 hours in milliseconds
    h24_ms = 86_400_000
    now_ms = int(time.time() * 1000)

    processed_today = db.query(db_models.NewsArticle).filter(
        db_models.NewsArticle.analyzed_at >= now_ms - h24_ms
    ).count()
    
    pending_count = db.query(db_models.NewsArticle).filter(
        db_models.NewsArticle.processing_status == "pending"
    ).count()

    endpoint_status = "mock" if state.config.use_mock_data else "live"

    return {
        "total_articles_consumed": total,
        "articles_processed_today": processed_today,
        "pending_candidates": pending_count,
        "active_opportunities": 0,
        "no_trade_count": 0,
        "system_mode": state.config.processing_mode,
        "last_refresh": state.proc_state.last_poll_timestamp,
        "endpoint_status": endpoint_status,
    }


@router.get("/processing-state")
def get_processing_state(db: Session = Depends(get_db)):
    # For now, processing state can remain in-memory or we can pull from DB
    # Let's pull from DB to be consistent
    ps = db.query(db_models.DBProcessingState).first()
    if not ps:
        ps = db_models.DBProcessingState()
        db.add(ps)
        db.commit()
        db.refresh(ps)
    
    return {
        "last_processed_article_id": ps.last_processed_article_id,
        "last_poll_timestamp": ps.last_poll_timestamp,
        "total_articles_processed": ps.total_articles_processed,
        "current_mode": ps.current_mode,
        "is_polling_active": ps.is_polling_active,
        "articles_in_queue": ps.articles_in_queue,
    }
