"""Agent API router — exposes pipeline triggers, trading signals, and scheduler status.

Five-layer pipeline:
  Agent 1   (Discovery)          — /api/agent/run
  Agent 2   (Market Open Conf.)  — /api/agent/confirm
  Agent 2.5 (Technical Analysis) — /api/agent/technical-analysis
  Agent 3   (Execution Planner)  — /api/agent/execute
  Agent 4   (Risk Monitor)       — /api/agent/risk-monitor
  Full pipeline                  — /api/agent/run-full-pipeline
"""

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
    """Manually trigger Agent 1 (Discovery) — reads news, understands events, saves assessments."""
    result = run_full_analysis(db)
    return result


@router.post("/confirm")
def trigger_confirmation_run(db: Session = Depends(get_db)):
    """Manually trigger Agent 2 (Market Open Confirmation).

    Takes today's pending Discovery assessments and validates them
    against live market-open data.  Does NOT produce entry/stop/target.
    """
    result = run_market_open_confirmation(db)
    return result


from agent.execution_agent import run_execution_planner

@router.post("/execute")
def trigger_execution_run(db: Session = Depends(get_db)):
    """Manually trigger Agent 3 (Execution Planner).

    Takes confirmed signals from Agent 2 and live price context.
    Produces entry, stop, target, and position sizing with hard risk constraints.
    """
    result = run_execution_planner(db)
    return result


from agent.technical_analysis_agent import run_technical_analysis

@router.post("/technical-analysis")
def trigger_technical_analysis(db: Session = Depends(get_db)):
    """Manually trigger Agent 2.5 (Technical Analysis).

    Takes confirmed signals and produces structured technical intelligence
    for Agent 3. Does NOT generate trades.
    """
    result = run_technical_analysis(db)
    return result


from agent.risk_monitor import run_risk_monitor, get_risk_monitor_summary

@router.post("/risk-monitor")
def trigger_risk_monitor(db: Session = Depends(get_db)):
    """Manually trigger Agent 4 (Risk Monitor).

    Evaluates all active (planned) trades against live market data.
    Produces HOLD / TIGHTEN_STOPLOSS / PARTIAL_EXIT / EXIT_NOW.
    """
    result = run_risk_monitor(db, force=True)
    return result


@router.get("/risk-monitor")
def get_risk_monitor_state(db: Session = Depends(get_db)):
    """Get current risk monitor state for all active trades.

    Returns the last computed risk assessment for each planned trade
    without re-running the monitor.
    """
    return get_risk_monitor_summary(db)


@router.post("/run-full-pipeline")
def trigger_full_pipeline(db: Session = Depends(get_db)):
    """Run the full pipeline back-to-back:

    1. Agent 1   (Discovery)          — news understanding
    2. Agent 2   (Market Open Conf.)  — thesis validation at open
    3. Agent 2.5 (Technical Analysis) — structured TA interpretation
    4. Agent 3   (Execution Planner)  — entry/stop/target with risk sizing

    Useful for manual end-to-end runs outside of scheduler windows.
    """
    # Layer 1: Discovery
    agent1_result = run_full_analysis(db)

    # Layer 2: Market Open Confirmation
    agent2_result = run_market_open_confirmation(db)

    # Layer 2.5: Technical Analysis (auto-triggers Agent 3)
    agent25_result = run_technical_analysis(db)

    return {
        "agent1_discovery": agent1_result,
        "agent2_confirmation": agent2_result,
        "agent25_technical_analysis": agent25_result,
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

    from sqlalchemy import case
    
    # Sort: WATCH signals first, then NO_TRADE. Within each group, sort by confidence descending.
    signals = query.order_by(
        case(
            (db_models.DBTradeSignal.signal_type == "WATCH", 0), 
            else_=1
        ).asc(),
        db_models.DBTradeSignal.confidence.desc()
    ).all()

    # Discovery summary (based on reasoning.final_verdict stored in reasoning JSON)
    watch_count = sum(1 for s in signals if s.signal_type == "WATCH")
    no_trade_count = sum(1 for s in signals if s.signal_type == "NO_TRADE")

    # Confirmation summary (Agent 2)
    confirmed_count = sum(1 for s in signals if s.confirmation_status == "confirmed")
    revised_count = sum(1 for s in signals if s.confirmation_status == "revised")
    invalidated_count = sum(1 for s in signals if s.confirmation_status == "invalidated")
    pending_count = sum(1 for s in signals if s.confirmation_status == "pending")

    return {
        "market_date": date,
        "total_signals": len(signals),
        "signals_summary": {
            # Agent 1 Discovery counts
            "watch": watch_count,           # IMPORTANT_EVENT → passed to Agent 2
            "no_trade": no_trade_count,     # MINOR_EVENT / NOISE → auto-skipped
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
                # agent_1_reasoning: dedicated column; fallback to combined_view.reasoning
                # inside the full reasoning JSON for old rows that lack the column.
                "agent_1_reasoning": (
                    s.agent_1_reasoning
                    or (s.reasoning or {}).get("combined_view", {}).get("reasoning")
                    or {
                        "why_agent_gave_this_view": "",
                        "main_driver": "",
                        "supporting_points": [],
                        "risk_points": [],
                        "confidence_reason": "",
                        "what_agent_2_should_validate": [],
                    }
                ),
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
                # Agent 4 risk monitor fields
                "risk_monitor_status": s.risk_monitor_status,
                "risk_monitor_data": s.risk_monitor_data,
                "risk_last_checked_at": s.risk_last_checked_at,
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
