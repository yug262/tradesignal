"""Paper Trading API router — exposes paper trading dashboard, positions, and analytics.

Endpoints:
  GET  /api/paper-trading/dashboard        — Full dashboard summary
  GET  /api/paper-trading/positions/open    — Open positions with live prices
  GET  /api/paper-trading/positions/closed  — Closed positions with P&L
  GET  /api/paper-trading/portfolio         — Portfolio performance
  GET  /api/paper-trading/trades            — All trades with filters
  POST /api/paper-trading/trade             — Create paper trade manually
  POST /api/paper-trading/trade/{id}/close  — Close a trade manually
  GET  /api/paper-trading/logs              — Agent activity logs
  GET  /api/paper-trading/sentiment         — Market sentiment data
  GET  /api/paper-trading/analytics         — Charts/analytics data
  POST /api/paper-trading/refresh-prices    — Trigger live price refresh
  POST /api/paper-trading/monitor           — Trigger position monitor manually
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import CreatePaperTradeRequest, ClosePaperTradeRequest
from agent.paper_trading_engine import (
    create_paper_trade,
    close_paper_trade,
    monitor_open_positions,
    get_or_create_portfolio,
    update_portfolio_stats,
    get_open_positions,
    get_closed_positions,
    get_all_trades,
    get_trade_logs,
    get_market_sentiment,
    get_analytics_data,
    _fetch_live_price,
    _now_ms,
)
import db_models

router = APIRouter(prefix="/api/paper-trading", tags=["paper-trading"])


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    """Get complete paper trading dashboard summary."""
    portfolio = get_or_create_portfolio(db)
    open_positions = get_open_positions(db)
    recent_closed = get_closed_positions(db, limit=10)
    recent_logs = get_trade_logs(db, limit=20)

    return {
        "portfolio": {
            "total_capital": portfolio.total_capital,
            "available_cash": round(portfolio.available_cash, 2),
            "used_cash": portfolio.used_cash,
            "total_profit": portfolio.total_profit,
            "total_loss": portfolio.total_loss,
            "total_pnl": portfolio.total_pnl,
            "todays_pnl": portfolio.todays_pnl,
            "win_rate": portfolio.win_rate,
            "total_trades": portfolio.total_trades,
            "open_trades": portfolio.open_trades,
            "closed_trades": portfolio.closed_trades,
            "winning_trades": portfolio.winning_trades,
            "losing_trades": portfolio.losing_trades,
            "updated_at": portfolio.updated_at,
        },
        "open_positions": open_positions,
        "recent_closed": recent_closed,
        "recent_activity": recent_logs,
    }


@router.get("/positions/open")
def get_open(db: Session = Depends(get_db)):
    """Get all open paper trade positions."""
    positions = get_open_positions(db)
    return {"positions": positions, "total": len(positions)}


@router.get("/positions/closed")
def get_closed(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """Get closed paper trade positions."""
    positions = get_closed_positions(db, limit=limit)
    return {"positions": positions, "total": len(positions)}


@router.get("/portfolio")
def get_portfolio(db: Session = Depends(get_db)):
    """Get portfolio performance summary."""
    portfolio = get_or_create_portfolio(db)
    return {
        "total_capital": portfolio.total_capital,
        "available_cash": round(portfolio.available_cash, 2),
        "used_cash": portfolio.used_cash,
        "total_profit": portfolio.total_profit,
        "total_loss": portfolio.total_loss,
        "total_pnl": portfolio.total_pnl,
        "todays_pnl": portfolio.todays_pnl,
        "win_rate": portfolio.win_rate,
        "total_trades": portfolio.total_trades,
        "open_trades": portfolio.open_trades,
        "closed_trades": portfolio.closed_trades,
        "winning_trades": portfolio.winning_trades,
        "losing_trades": portfolio.losing_trades,
        "updated_at": portfolio.updated_at,
    }


@router.get("/trades")
def get_trades(
    symbol: str = Query(default=None),
    status: str = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    """Get all trades with optional filters."""
    trades = get_all_trades(db, symbol=symbol, status=status, limit=limit)
    return {"trades": trades, "total": len(trades)}


@router.post("/trade")
def create_trade(req: CreatePaperTradeRequest, db: Session = Depends(get_db)):
    """Manually create a paper trade."""
    result = create_paper_trade(
        db=db,
        symbol=req.symbol.upper(),
        entry_price=req.entry_price,
        stop_loss=req.stop_loss,
        target_price=req.target_price,
        quantity=req.quantity,
        action=req.action.upper(),
        trade_mode=req.trade_mode.upper(),
        confidence_score=req.confidence_score,
        risk_level=req.risk_level.upper(),
        trade_reason=req.trade_reason,
        signal_id=req.signal_id,
        risk_reward=req.risk_reward,
    )
    return result


@router.post("/trade/{trade_id}/close")
def close_trade(trade_id: str, req: ClosePaperTradeRequest, db: Session = Depends(get_db)):
    """Manually close a paper trade."""
    result = close_paper_trade(
        db=db,
        trade_id=trade_id,
        exit_price=req.exit_price,
        exit_reason=req.exit_reason,
    )
    return result


@router.get("/logs")
def get_logs(
    symbol: str = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """Get agent activity logs."""
    logs = get_trade_logs(db, symbol=symbol, limit=limit)
    return {"logs": logs, "total": len(logs)}


@router.get("/sentiment")
def get_sentiment(
    date: str = Query(default=None),
    db: Session = Depends(get_db),
):
    """Get market sentiment data from Agent 1 analysis."""
    sentiments = get_market_sentiment(db, date=date)
    return {"sentiments": sentiments, "total": len(sentiments)}


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """Get analytics data for charts."""
    return get_analytics_data(db)


@router.post("/refresh-prices")
def refresh_prices(db: Session = Depends(get_db)):
    """Trigger a manual live price refresh for all open positions."""
    open_trades = db.query(db_models.DBPaperTrade).filter(
        db_models.DBPaperTrade.status.in_(["OPEN", "PENDING"])
    ).all()

    updated = 0
    now = _now_ms()

    for trade in open_trades:
        price = _fetch_live_price(trade.symbol)
        if price is not None:
            trade.current_price = price
            if trade.status == "PENDING":
                trade.pnl = 0.0
                trade.pnl_percentage = 0.0
            else:
                if trade.action == "BUY":
                    trade.pnl = round((price - trade.entry_price) * trade.quantity, 2)
                else:
                    trade.pnl = round((trade.entry_price - price) * trade.quantity, 2)
                trade.pnl_percentage = round(
                    (trade.pnl / trade.position_value * 100) if trade.position_value > 0 else 0.0, 2
                )
            trade.updated_at = now
            updated += 1

    db.commit()

    # Recalculate portfolio totals (todays_pnl, total_pnl) to include new unrealized PnL
    update_portfolio_stats(db)
    db.commit()

    return {"status": "success", "updated": updated, "total": len(open_trades)}


@router.post("/monitor")
def trigger_monitor(db: Session = Depends(get_db)):
    """Manually trigger position monitor (checks SL/target and auto-closes)."""
    result = monitor_open_positions(db)
    return result
