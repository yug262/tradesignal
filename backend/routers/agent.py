"""Agent API router -- exposes trading signals, manual triggers, and scheduler status."""

import time
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import db_models
from database import get_db
from agent.signal_generator import run_full_analysis
from agent.confirmation_agent import run_market_open_confirmation
from agent.market_calendar import is_trading_day, get_news_fetch_window

router = APIRouter(prefix="/api/agent", tags=["agent"])

IST = timezone(timedelta(hours=5, minutes=30))


@router.post("/run")
def trigger_agent_run(db: Session = Depends(get_db)):
    """Manually trigger a full agent analysis run (Agent 1: pre-market)."""
    result = run_full_analysis(db)
    return result


@router.post("/confirm")
def trigger_confirmation_run(db: Session = Depends(get_db)):
    """Manually trigger Market Open Confirmation (Agent 2).
    
    Fetches live market data and confirms/revises/invalidates
    today's pending signals from Agent 1.
    """
    result = run_market_open_confirmation(db)
    return result


from agent.execution_agent import run_execution_planner

@router.post("/execute")
def trigger_execution_run(db: Session = Depends(get_db)):
    """Manually trigger Execution Planner (Agent 3).
    
    Fetches confirmed signals and live market data to
    plan exact execution levels and strategies.
    """
    result = run_execution_planner(db)
    return result


@router.post("/run-full-pipeline")
def trigger_full_pipeline(db: Session = Depends(get_db)):
    """Run Agent 1 + Agent 2 + Agent 3 back-to-back.
    
    Useful for manual runs when you want
    the complete analysis + confirmation + execution in one click.
    """
    # Phase 1: Pre-market analysis
    agent1_result = run_full_analysis(db)
    
    # Phase 2: Confirmation with live data
    agent2_result = run_market_open_confirmation(db)
    
    # Phase 3: Execution Planner
    agent3_result = run_execution_planner(db)
    
    return {
        "agent1_pre_market": agent1_result,
        "agent2_confirmation": agent2_result,
        "agent3_execution": agent3_result,
    }


@router.post("/fetch-news")
def trigger_manual_news_fetch(db: Session = Depends(get_db)):
    """Manually trigger a news fetch from the configured endpoint."""
    from store import _get_store
    from agent.data_collector import trigger_news_fetch

    config = _get_store().config

    if not config.news_endpoint_url:
        return {"status": "error", "message": "No news endpoint URL configured"}

    new_count = trigger_news_fetch(config.news_endpoint_url, db)

    # Count total articles in DB
    total_in_db = db.query(db_models.NewsArticle).count()

    return {
        "status": "success",
        "new_articles_saved": new_count,
        "total_articles_in_db": total_in_db,
    }


@router.post("/cleanup")
def trigger_manual_cleanup(db: Session = Depends(get_db)):
    """Manually trigger DB cleanup (delete news older than 5 days)."""
    five_days_ago_ms = int((time.time() - 5 * 24 * 3600) * 1000)

    old_news = (
        db.query(db_models.NewsArticle)
        .filter(db_models.NewsArticle.published_at < five_days_ago_ms)
    )
    news_count = old_news.count()
    if news_count > 0:
        old_news.delete(synchronize_session=False)

    thirty_days_ago_ms = int((time.time() - 30 * 24 * 3600) * 1000)
    old_signals = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.generated_at < thirty_days_ago_ms)
    )
    sig_count = old_signals.count()
    if sig_count > 0:
        old_signals.delete(synchronize_session=False)

    db.commit()

    return {
        "status": "success",
        "deleted_news": news_count,
        "deleted_signals": sig_count,
    }


@router.get("/signals")
def get_signals(
    date: str = Query(default=None, description="Market date YYYY-MM-DD, defaults to today"),
    signal_type: str = Query(default=None, description="Filter: BUY, SELL, HOLD, NO_TRADE"),
    trade_mode: str = Query(default=None, description="Filter: INTRADAY, DELIVERY"),
    min_confidence: float = Query(default=0, description="Minimum confidence"),
    confirmation_status: str = Query(default=None, description="Filter: pending, confirmed, revised, invalidated"),
    db: Session = Depends(get_db),
):
    """Get trading signals, optionally filtered by date, type, mode, score, and confirmation status."""
    if not date:
        date = datetime.now(IST).strftime("%Y-%m-%d")

    query = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.market_date == date)
        .filter(db_models.DBTradeSignal.confidence >= min_confidence)
    )

    if signal_type:
        query = query.filter(db_models.DBTradeSignal.signal_type == signal_type.upper())
    if trade_mode:
        query = query.filter(db_models.DBTradeSignal.trade_mode == trade_mode.upper())
    if confirmation_status:
        query = query.filter(db_models.DBTradeSignal.confirmation_status == confirmation_status.lower())

    signals = query.order_by(db_models.DBTradeSignal.confidence.desc()).all()

    # Build summary
    buy_count = sum(1 for s in signals if s.signal_type == "BUY")
    sell_count = sum(1 for s in signals if s.signal_type == "SELL")
    hold_count = sum(1 for s in signals if s.signal_type == "HOLD")
    no_trade_count = sum(1 for s in signals if s.signal_type == "NO_TRADE")

    # Confirmation summary
    confirmed_count = sum(1 for s in signals if s.confirmation_status == "confirmed")
    revised_count = sum(1 for s in signals if s.confirmation_status == "revised")
    invalidated_count = sum(1 for s in signals if s.confirmation_status == "invalidated")
    pending_count = sum(1 for s in signals if s.confirmation_status == "pending")

    return {
        "market_date": date,
        "total_signals": len(signals),
        "signals_summary": {
            "buy": buy_count,
            "sell": sell_count,
            "hold": hold_count,
            "no_trade": no_trade_count,
        },
        "confirmation_summary": {
            "confirmed": confirmed_count,
            "revised": revised_count,
            "invalidated": invalidated_count,
            "pending": pending_count,
        },
        "signals": [
            {
                "id": s.id,
                "symbol": s.symbol,
                "signal_type": s.signal_type,
                "trade_mode": s.trade_mode,
                "entry_price": s.entry_price,
                "stop_loss": s.stop_loss,
                "target_price": s.target_price,
                "risk_reward": s.risk_reward,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
                "news_article_ids": s.news_article_ids,
                "stock_snapshot": s.stock_snapshot,
                "generated_at": s.generated_at,
                "market_date": s.market_date,
                "status": s.status,
                # Agent 2 confirmation fields
                "confirmation_status": s.confirmation_status,
                "confirmed_at": s.confirmed_at,
                "confirmation_data": s.confirmation_data,
                # Agent 3 execution fields
                "execution_status": s.execution_status,
                "executed_at": s.executed_at,
                "execution_data": s.execution_data,
            }
            for s in signals
        ],
    }


@router.get("/status")
def get_agent_status(db: Session = Depends(get_db)):
    """Get full status: last run, scheduler info, market calendar, DB stats."""
    from agent.scheduler import get_scheduler_status

    today = datetime.now(IST).strftime("%Y-%m-%d")
    today_date = datetime.now(IST).date()

    # Get latest signal for today
    latest = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.market_date == today)
        .order_by(db_models.DBTradeSignal.generated_at.desc())
        .first()
    )

    total_today = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.market_date == today)
        .count()
    )

    if latest:
        last_run_at = latest.generated_at
        last_run_time = datetime.fromtimestamp(last_run_at / 1000, tz=IST).strftime("%H:%M:%S IST")
    else:
        last_run_at = None
        last_run_time = "Never (today)"

    # Confirmation stats for today
    confirmed_count = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.market_date == today)
        .filter(db_models.DBTradeSignal.confirmation_status == "confirmed")
        .count()
    )
    pending_count = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.market_date == today)
        .filter(db_models.DBTradeSignal.confirmation_status == "pending")
        .count()
    )

    # Execution stats for today
    executed_count = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.market_date == today)
        .filter(db_models.DBTradeSignal.execution_status == "planned")
        .count()
    )
    exec_pending_count = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.market_date == today)
        .filter(db_models.DBTradeSignal.execution_status == "pending")
        .count()
    )

    # DB statistics
    total_news = db.query(db_models.NewsArticle).count()
    total_signals = db.query(db_models.DBTradeSignal).count()

    # Market calendar info
    _, _, window_info = get_news_fetch_window()

    # Scheduler job info
    sched_status = get_scheduler_status()

    return {
        "market_date": today,
        "last_run_at": last_run_at,
        "last_run_time": last_run_time,
        "total_signals_today": total_today,
        "confirmation_stats": {
            "confirmed": confirmed_count,
            "pending": pending_count,
        },
        "execution_stats": {
            "planned": executed_count,
            "pending": exec_pending_count,
        },
        "db_stats": {
            "total_news_articles": total_news,
            "total_trade_signals": total_signals,
        },
        "market_calendar": {
            "today_is_trading_day": is_trading_day(today_date),
            "today_weekday": window_info["today_weekday"],
            "last_trading_day": window_info["last_trading_day"],
            "news_window": f"{window_info['from_time']} -> {window_info['to_time']}",
            "window_hours": window_info["window_hours"],
        },
        "scheduler": sched_status,
    }
