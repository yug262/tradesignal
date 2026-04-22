"""Paper Trading Engine — creates, monitors, and closes simulated trades.

Core responsibilities:
  1. Create paper trade from Agent 3 BUY signal (or manually)
  2. Monitor open positions — fetch live prices, check SL/target
  3. Auto-close positions when exit conditions met
  4. Update portfolio balance after each trade
  5. Log all actions to agent_logs

Integration points:
  - Called by execution_agent.py when Agent 3 outputs ENTER NOW + BUY
  - Called by scheduler every 15s during market hours
  - Called by risk_monitor.py when EXIT_NOW is triggered
  - Exposed via /api/paper-trading/ endpoints
"""

import time
import uuid
import traceback
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal

IST = timezone(timedelta(hours=5, minutes=30))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _is_market_open() -> bool:
    """Check if current time is within Indian market hours (09:15 to 15:30) and on a weekday."""
    now = datetime.now(IST)
    if now.weekday() > 4:  # 5=Saturday, 6=Sunday
        return False
    current_minutes = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= current_minutes < (15 * 60 + 30)


def _log_action(db: Session, agent_name: str, symbol: str, signal: str,
                message: str, confidence: float = 0.0, trade_id: str = None,
                details: dict = None):
    """Write a structured log entry to agent_logs table."""
    log = db_models.DBAgentLog(
        agent_name=agent_name,
        symbol=symbol,
        signal=signal,
        confidence=confidence,
        message=message,
        details=details,
        trade_id=trade_id,
        created_at=_now_ms(),
    )
    db.add(log)


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def get_or_create_portfolio(db: Session) -> db_models.DBPortfolio:
    """Get existing portfolio or create with defaults from system_config."""
    portfolio = db.query(db_models.DBPortfolio).first()
    if not portfolio:
        # Seed from system_config capital
        cfg = db.query(db_models.DBSystemConfig).first()
        initial_capital = cfg.capital if cfg else 100000.0

        portfolio = db_models.DBPortfolio(
            total_capital=initial_capital,
            available_cash=initial_capital,
            used_cash=0.0,
            total_profit=0.0,
            total_loss=0.0,
            total_pnl=0.0,
            win_rate=0.0,
            total_trades=0,
            open_trades=0,
            closed_trades=0,
            winning_trades=0,
            losing_trades=0,
            todays_pnl=0.0,
            todays_date=_market_date_str(),
            updated_at=_now_ms(),
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def _refresh_daily_pnl(portfolio: db_models.DBPortfolio):
    """Reset today's P&L if the date has changed."""
    today = _market_date_str()
    if portfolio.todays_date != today:
        portfolio.todays_pnl = 0.0
        portfolio.todays_date = today


def update_portfolio_stats(db: Session):
    """Recalculate portfolio stats from all paper trades."""
    portfolio = get_or_create_portfolio(db)
    _refresh_daily_pnl(portfolio)

    # Count trades
    open_trades = db.query(db_models.DBPaperTrade).filter(
        db_models.DBPaperTrade.status == "OPEN"
    ).all()

    closed_trades = db.query(db_models.DBPaperTrade).filter(
        db_models.DBPaperTrade.status == "CLOSED"
    ).all()

    # Calculate used cash (sum of open position values)
    used_cash = sum(t.position_value for t in open_trades)

    # Calculate total P&L from closed trades
    total_pnl = sum(t.pnl for t in closed_trades)
    total_profit = sum(t.pnl for t in closed_trades if t.pnl > 0)
    total_loss = sum(t.pnl for t in closed_trades if t.pnl < 0)

    winning = sum(1 for t in closed_trades if t.pnl > 0)
    losing = sum(1 for t in closed_trades if t.pnl <= 0)
    total_closed = len(closed_trades)

    # Today's closed trades P&L
    today = _market_date_str()
    today_start_ms = int(datetime.now(IST).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp() * 1000)
    todays_closed = [t for t in closed_trades
                     if t.exit_time and t.exit_time >= today_start_ms]
    todays_pnl = sum(t.pnl for t in todays_closed)

    # Available cash = initial capital + total P&L from closed - currently used
    portfolio.available_cash = portfolio.total_capital + total_pnl - used_cash
    portfolio.used_cash = round(used_cash, 2)
    portfolio.total_profit = round(total_profit, 2)
    portfolio.total_loss = round(total_loss, 2)
    portfolio.total_pnl = round(total_pnl, 2)
    portfolio.win_rate = round((winning / total_closed * 100), 2) if total_closed > 0 else 0.0
    portfolio.total_trades = len(open_trades) + total_closed
    portfolio.open_trades = len(open_trades)
    portfolio.closed_trades = total_closed
    portfolio.winning_trades = winning
    portfolio.losing_trades = losing
    portfolio.todays_pnl = round(todays_pnl, 2)
    portfolio.todays_date = today
    portfolio.updated_at = _now_ms()

    db.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# CREATE PAPER TRADE
# ═══════════════════════════════════════════════════════════════════════════════

def create_paper_trade(
    db: Session,
    symbol: str,
    entry_price: float,
    stop_loss: float,
    target_price: float,
    quantity: int,
    action: str = "BUY",
    trade_mode: str = "INTRADAY",
    confidence_score: float = 0.0,
    risk_level: str = "MEDIUM",
    trade_reason: str = "",
    signal_id: str = None,
    risk_reward: str = None,
    max_loss_at_sl: float = 0.0,
) -> dict:
    """Create a new paper trade and update portfolio."""

    if not _is_market_open():
        return {
            "success": False,
            "error": "Market is closed. Trading is only allowed on weekdays between 09:15 and 15:30 IST."
        }

    portfolio = get_or_create_portfolio(db)
    position_value = round(quantity * entry_price, 2)

    # Check available cash
    if position_value > portfolio.available_cash:
        return {
            "success": False,
            "error": f"Insufficient cash. Need Rs.{position_value:,.2f} but only Rs.{portfolio.available_cash:,.2f} available."
        }

    # Check for duplicate (same symbol + signal_id already open)
    if signal_id:
        existing = db.query(db_models.DBPaperTrade).filter(
            db_models.DBPaperTrade.signal_id == signal_id,
            db_models.DBPaperTrade.status == "OPEN",
        ).first()
        if existing:
            return {
                "success": False,
                "error": f"Paper trade already exists for signal {signal_id}",
                "trade_id": existing.id,
            }

    now = _now_ms()
    trade_id = f"pt-{symbol}-{datetime.now(IST).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    trade = db_models.DBPaperTrade(
        id=trade_id,
        symbol=symbol,
        action=action,
        entry_price=entry_price,
        exit_price=None,
        quantity=quantity,
        stop_loss=stop_loss,
        target_price=target_price,
        current_price=entry_price,
        pnl=0.0,
        pnl_percentage=0.0,
        status="OPEN",
        confidence_score=confidence_score,
        risk_level=risk_level,
        trade_reason=trade_reason,
        exit_reason=None,
        signal_id=signal_id,
        trade_mode=trade_mode,
        risk_reward=risk_reward,
        position_value=position_value,
        max_loss_at_sl=max_loss_at_sl,
        entry_time=now,
        exit_time=None,
        created_at=now,
        updated_at=now,
    )
    db.add(trade)

    # Log the action
    _log_action(
        db, "PAPER_TRADING", symbol, "BUY_EXECUTED",
        f"Paper {action} executed: {quantity} shares @ Rs.{entry_price:.2f} "
        f"(SL: {stop_loss:.2f}, Target: {target_price:.2f})",
        confidence=confidence_score, trade_id=trade_id,
        details={"entry_price": entry_price, "quantity": quantity,
                 "stop_loss": stop_loss, "target_price": target_price}
    )

    # Update portfolio
    update_portfolio_stats(db)
    db.commit()

    print(f"  [PAPER TRADE] CREATED: {trade_id} | {action} {quantity}x {symbol} @ Rs.{entry_price:.2f}")

    return {
        "success": True,
        "trade_id": trade_id,
        "symbol": symbol,
        "action": action,
        "entry_price": entry_price,
        "quantity": quantity,
        "position_value": position_value,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLOSE PAPER TRADE
# ═══════════════════════════════════════════════════════════════════════════════

def close_paper_trade(
    db: Session,
    trade_id: str,
    exit_price: float,
    exit_reason: str = "MANUAL_EXIT",
) -> dict:
    """Close an open paper trade and calculate P&L."""

    trade = db.query(db_models.DBPaperTrade).filter(
        db_models.DBPaperTrade.id == trade_id,
        db_models.DBPaperTrade.status == "OPEN",
    ).first()

    if not trade:
        return {"success": False, "error": f"No open trade found with id {trade_id}"}

    now = _now_ms()

    # Calculate P&L
    if trade.action == "BUY":
        pnl = (exit_price - trade.entry_price) * trade.quantity
    else:
        pnl = (trade.entry_price - exit_price) * trade.quantity

    pnl_pct = (pnl / trade.position_value * 100) if trade.position_value > 0 else 0.0

    trade.exit_price = exit_price
    trade.current_price = exit_price
    trade.pnl = round(pnl, 2)
    trade.pnl_percentage = round(pnl_pct, 2)
    trade.status = "CLOSED"
    trade.exit_reason = exit_reason
    trade.exit_time = now
    trade.updated_at = now

    # Log the action
    signal_label = {
        "TARGET_HIT": "TARGET_ACHIEVED",
        "STOP_LOSS_HIT": "STOP_LOSS_TRIGGERED",
        "AGENT_SELL_SIGNAL": "AGENT_SELL",
        "MANUAL_EXIT": "MANUAL_EXIT",
    }.get(exit_reason, exit_reason)

    pnl_str = f"+Rs.{pnl:.2f}" if pnl >= 0 else f"-Rs.{abs(pnl):.2f}"
    _log_action(
        db, "PAPER_TRADING", trade.symbol, signal_label,
        f"Trade closed ({exit_reason}): {trade.quantity} shares @ Rs.{exit_price:.2f} | P&L: {pnl_str} ({pnl_pct:+.2f}%)",
        trade_id=trade_id,
        details={"exit_price": exit_price, "pnl": round(pnl, 2),
                 "pnl_percentage": round(pnl_pct, 2), "exit_reason": exit_reason}
    )

    # Update portfolio
    update_portfolio_stats(db)
    db.commit()

    print(f"  [PAPER TRADE] CLOSED: {trade_id} | {exit_reason} | P&L: {pnl_str}")

    return {
        "success": True,
        "trade_id": trade_id,
        "symbol": trade.symbol,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "pnl": round(pnl, 2),
        "pnl_percentage": round(pnl_pct, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LIVE PRICE FETCH
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_live_price(symbol: str) -> float | None:
    """Fetch latest price for a symbol from Groww API."""
    clean = symbol.replace(".NS", "").strip().upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        url = (
            f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/"
            f"exchange/NSE/segment/CASH/{clean}/latest"
        )
        with httpx.Client(timeout=8.0, headers=headers) as client:
            res = client.get(url)
            if res.status_code == 200:
                data = res.json()
                ltp = data.get("ltp") or data.get("close")
                return round(float(ltp), 2) if ltp is not None else None
    except Exception as e:
        print(f"  [WARN] Live price fetch failed for {symbol}: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# POSITION MONITOR — called every 15s by scheduler
# ═══════════════════════════════════════════════════════════════════════════════

def monitor_open_positions(db: Session = None) -> dict:
    """
    Monitor all open paper trades:
      1. Fetch live price for each
      2. Check if target hit
      3. Check if stop loss hit
      4. Auto-close if conditions met
      5. Update current_price and unrealized P&L

    Returns summary of actions taken.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        open_trades = db.query(db_models.DBPaperTrade).filter(
            db_models.DBPaperTrade.status == "OPEN"
        ).all()

        if not open_trades:
            return {"status": "no_open_trades", "total": 0, "actions": []}

        actions = []
        now = _now_ms()

        for trade in sorted(open_trades, key=lambda x: x.symbol): # Sort to prevent deadlocks
            try:
                live_price = _fetch_live_price(trade.symbol)
                if live_price is None:
                    continue

                # Update current price and unrealized P&L
                if trade.action == "BUY":
                    unrealized_pnl = (live_price - trade.entry_price) * trade.quantity
                else:
                    unrealized_pnl = (trade.entry_price - live_price) * trade.quantity

                pnl_pct = (unrealized_pnl / trade.position_value * 100) if trade.position_value > 0 else 0.0

                trade.current_price = live_price
                trade.pnl = round(unrealized_pnl, 2)
                trade.pnl_percentage = round(pnl_pct, 2)
                trade.updated_at = now

                # Check exit conditions
                exit_reason = None
                
                # Auto square-off INTRADAY trades at or after 15:20 (3:20 PM)
                ist_now = datetime.now(IST)
                is_intraday_cutoff = (
                    trade.trade_mode == "INTRADAY" 
                    and (ist_now.hour > 15 or (ist_now.hour == 15 and ist_now.minute >= 20))
                )

                if is_intraday_cutoff:
                    exit_reason = "TIME_SQUARE_OFF"
                elif trade.action == "BUY":
                    if live_price >= trade.target_price:
                        exit_reason = "TARGET_HIT"
                    elif live_price <= trade.stop_loss:
                        exit_reason = "STOP_LOSS_HIT"
                else:  # SELL/SHORT
                    if live_price <= trade.target_price:
                        exit_reason = "TARGET_HIT"
                    elif live_price >= trade.stop_loss:
                        exit_reason = "STOP_LOSS_HIT"

                if exit_reason:
                    result = close_paper_trade(db, trade.id, live_price, exit_reason)
                    actions.append({
                        "trade_id": trade.id,
                        "symbol": trade.symbol,
                        "action": exit_reason,
                        "exit_price": live_price,
                        "pnl": result.get("pnl", 0),
                    })
                
                # Commit after each trade to minimize lock contention and avoid deadlocks
                db.commit()

            except Exception as e:
                db.rollback()
                print(f"  [WARN] Monitor error for {trade.symbol}: {e}")
                traceback.print_exc()

        update_portfolio_stats(db)
        db.commit()

        return {
            "status": "completed",
            "total_monitored": len(open_trades),
            "actions_taken": len(actions),
            "actions": actions,
            "checked_at": now,
        }

    except Exception as e:
        print(f"[PAPER TRADE MONITOR] Error: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}
    finally:
        if own_session:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-CREATE FROM AGENT 3
# ═══════════════════════════════════════════════════════════════════════════════

def auto_create_from_execution(db: Session, signal: db_models.DBTradeSignal) -> dict | None:
    """
    Automatically create a paper trade when Agent 3 outputs ENTER NOW + BUY/SELL.

    Called from execution_agent.py after a signal is marked as 'planned'.
    Returns the create result, or None if conditions not met.
    """
    exec_data = signal.execution_data if isinstance(signal.execution_data, dict) else {}

    action = exec_data.get("action", "AVOID").upper()
    exec_decision = exec_data.get("execution_decision", "NO TRADE").upper()

    # Only create for ENTER NOW decisions
    if exec_decision != "ENTER NOW" or action not in ("BUY", "SELL"):
        return None

    entry_plan = exec_data.get("entry_plan", {})
    stop_loss = exec_data.get("stop_loss", {})
    target = exec_data.get("target", {})
    sizing = exec_data.get("position_sizing", {})

    entry_price = entry_plan.get("entry_price", 0)
    sl_price = stop_loss.get("price", 0)
    target_price = target.get("price", 0)
    quantity = sizing.get("position_size_shares", 0)

    if entry_price <= 0 or sl_price <= 0 or target_price <= 0 or quantity <= 0:
        return None

    # Determine risk level from confidence
    confidence = exec_data.get("confidence", 0)
    if confidence >= 70:
        risk_level = "LOW"
    elif confidence >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return create_paper_trade(
        db=db,
        symbol=signal.symbol,
        entry_price=entry_price,
        stop_loss=sl_price,
        target_price=target_price,
        quantity=quantity,
        action=action,
        trade_mode=signal.trade_mode or "INTRADAY",
        confidence_score=confidence,
        risk_level=risk_level,
        trade_reason=exec_data.get("final_summary", "Agent 3 auto-execution"),
        signal_id=signal.id,
        risk_reward=exec_data.get("risk_reward", ""),
        max_loss_at_sl=sizing.get("max_loss_at_sl", 0),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# QUERY HELPERS (used by API router)
# ═══════════════════════════════════════════════════════════════════════════════

def get_open_positions(db: Session) -> list[dict]:
    """Get all open paper trades with current prices."""
    trades = db.query(db_models.DBPaperTrade).filter(
        db_models.DBPaperTrade.status == "OPEN"
    ).order_by(db_models.DBPaperTrade.entry_time.desc()).all()

    return [_trade_to_dict(t) for t in trades]


def get_closed_positions(db: Session, limit: int = 50) -> list[dict]:
    """Get closed paper trades, most recent first."""
    trades = db.query(db_models.DBPaperTrade).filter(
        db_models.DBPaperTrade.status == "CLOSED"
    ).order_by(db_models.DBPaperTrade.exit_time.desc()).limit(limit).all()

    return [_trade_to_dict(t) for t in trades]


def get_all_trades(db: Session, symbol: str = None, status: str = None,
                   limit: int = 100) -> list[dict]:
    """Get trades with optional filters."""
    query = db.query(db_models.DBPaperTrade)

    if symbol:
        query = query.filter(db_models.DBPaperTrade.symbol == symbol.upper())
    if status:
        query = query.filter(db_models.DBPaperTrade.status == status.upper())

    trades = query.order_by(db_models.DBPaperTrade.created_at.desc()).limit(limit).all()
    return [_trade_to_dict(t) for t in trades]


def get_trade_logs(db: Session, symbol: str = None, limit: int = 50) -> list[dict]:
    """Get agent activity logs."""
    query = db.query(db_models.DBAgentLog)

    if symbol:
        query = query.filter(db_models.DBAgentLog.symbol == symbol.upper())

    logs = query.order_by(db_models.DBAgentLog.created_at.desc()).limit(limit).all()

    return [{
        "id": l.id,
        "agent_name": l.agent_name,
        "symbol": l.symbol,
        "signal": l.signal,
        "confidence": l.confidence,
        "message": l.message,
        "details": l.details,
        "trade_id": l.trade_id,
        "created_at": l.created_at,
    } for l in logs]


def get_market_sentiment(db: Session, date: str = None) -> list[dict]:
    """Get market sentiment data."""
    query = db.query(db_models.DBMarketSentiment)
    if date:
        query = query.filter(db_models.DBMarketSentiment.market_date == date)
    else:
        query = query.filter(db_models.DBMarketSentiment.market_date == _market_date_str())

    sentiments = query.order_by(db_models.DBMarketSentiment.confidence_score.desc()).all()

    return [{
        "id": s.id,
        "symbol": s.symbol,
        "sector": s.sector,
        "sentiment": s.sentiment,
        "confidence_score": s.confidence_score,
        "news_reason": s.news_reason,
        "event_strength": s.event_strength,
        "final_verdict": s.final_verdict,
        "market_date": s.market_date,
        "updated_at": s.updated_at,
    } for s in sentiments]


def get_analytics_data(db: Session) -> dict:
    """Get analytics data for charts."""
    all_closed = db.query(db_models.DBPaperTrade).filter(
        db_models.DBPaperTrade.status == "CLOSED"
    ).order_by(db_models.DBPaperTrade.exit_time.asc()).all()

    # Portfolio growth (cumulative P&L over time)
    cumulative_pnl = 0.0
    portfolio_growth = []
    daily_pnl_map = {}

    for t in all_closed:
        cumulative_pnl += t.pnl
        exit_date = datetime.fromtimestamp(
            t.exit_time / 1000, IST
        ).strftime("%Y-%m-%d") if t.exit_time else "unknown"

        portfolio_growth.append({
            "date": exit_date,
            "cumulative_pnl": round(cumulative_pnl, 2),
            "trade_pnl": round(t.pnl, 2),
            "symbol": t.symbol,
        })

        # Daily P&L aggregation
        if exit_date not in daily_pnl_map:
            daily_pnl_map[exit_date] = 0.0
        daily_pnl_map[exit_date] += t.pnl

    daily_pnl = [{"date": d, "pnl": round(p, 2)} for d, p in sorted(daily_pnl_map.items())]

    # Win/Loss distribution
    wins = sum(1 for t in all_closed if t.pnl > 0)
    losses = sum(1 for t in all_closed if t.pnl <= 0)

    # Exit reason distribution
    exit_reasons = {}
    for t in all_closed:
        reason = t.exit_reason or "UNKNOWN"
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    # Sector/symbol performance
    symbol_perf = {}
    for t in all_closed:
        if t.symbol not in symbol_perf:
            symbol_perf[t.symbol] = {"pnl": 0.0, "trades": 0, "wins": 0}
        symbol_perf[t.symbol]["pnl"] += t.pnl
        symbol_perf[t.symbol]["trades"] += 1
        if t.pnl > 0:
            symbol_perf[t.symbol]["wins"] += 1

    symbol_performance = [
        {"symbol": s, "pnl": round(d["pnl"], 2), "trades": d["trades"], "wins": d["wins"]}
        for s, d in sorted(symbol_perf.items(), key=lambda x: x[1]["pnl"], reverse=True)
    ]

    return {
        "portfolio_growth": portfolio_growth,
        "daily_pnl": daily_pnl,
        "win_loss": {"wins": wins, "losses": losses, "total": wins + losses},
        "exit_reasons": exit_reasons,
        "symbol_performance": symbol_performance,
    }


def _trade_to_dict(t: db_models.DBPaperTrade) -> dict:
    """Convert a paper trade ORM object to a dict."""
    # Calculate trade duration
    duration_ms = None
    if t.entry_time and t.exit_time:
        duration_ms = t.exit_time - t.entry_time

    return {
        "id": t.id,
        "symbol": t.symbol,
        "action": t.action,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "quantity": t.quantity,
        "stop_loss": t.stop_loss,
        "target_price": t.target_price,
        "current_price": t.current_price,
        "pnl": t.pnl,
        "pnl_percentage": t.pnl_percentage,
        "status": t.status,
        "confidence_score": t.confidence_score,
        "risk_level": t.risk_level,
        "trade_reason": t.trade_reason,
        "exit_reason": t.exit_reason,
        "signal_id": t.signal_id,
        "trade_mode": t.trade_mode,
        "risk_reward": t.risk_reward,
        "position_value": t.position_value,
        "max_loss_at_sl": t.max_loss_at_sl,
        "entry_time": t.entry_time,
        "exit_time": t.exit_time,
        "duration_ms": duration_ms,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }
