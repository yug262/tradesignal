"""Risk Monitor Agent (Agent 4) — Post-entry live trade protection engine.

This is the main orchestrator for the live risk monitoring system.
It continuously evaluates every open trade and produces
HOLD / TIGHTEN_STOPLOSS / PARTIAL_EXIT / EXIT_NOW decisions.

NO Gemini/LLM in the execution path.
NO scoring engine. NO weighted buckets.
Pure deterministic rule engine.

Pipeline for each monitored trade:
  1. Fetch live quote + intraday candles + market depth
  2. Extract minimal risk features (risk_features.py)
  3. Run strict priority rule engine (risk_rules.py)
  4. Log decision + persist to DB (updates SL, or closes trade)

Integration points:
  - Reads from: DBPaperTrade where status='OPEN'
  - Writes to: DBTradeSignal (for status visibility) and DBPaperTrade (SL updates)
  - Triggered by: APScheduler interval job (every 30s during market hours)
  - Exposed via: /api/agent/risk-monitor endpoints
"""

import time
import logging
import traceback
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal

from agent.risk_features import (
    extract_risk_features,
    fetch_live_quote,
    fetch_intraday_candles,
    fetch_market_depth,
)
from agent.risk_rules import evaluate_trade
from agent.paper_trading_engine import close_paper_trade

logger = logging.getLogger("risk_monitor")

IST = timezone(timedelta(hours=5, minutes=30))

# Minimum interval between checks for the same trade (seconds)
MIN_CHECK_INTERVAL_SECONDS = 25


def _now_ms() -> int:
    return int(time.time() * 1000)


def _market_is_open() -> bool:
    """Check if NSE market is currently open."""
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Weekend
        return False
    hhmm = now.hour * 100 + now.minute
    return 915 <= hhmm <= 1530


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURED LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

def _log_decision(trade_id: str, symbol: str, features: dict, result: dict, old_sl: float):
    """Log every risk decision in a structured format."""
    new_sl = result.get("updated_stop_loss")
    decision = result.get("decision", "HOLD")
    reason_code = result.get("reason_code", "")
    pnl_pct = features.get("pnl_percent", 0)
    pnl_rupees_total = features.get("pnl_rupees_total", 0)
    ltp = features.get("ltp", 0)
    entry = features.get("entry_price", 0)
    qty = features.get("quantity", 0)
    mfe_pct = features.get("mfe_pct", 0)
    mae_pct = features.get("mae_pct", 0)
    time_in_trade = features.get("time_in_trade_seconds", 0)
    triggered = result.get("triggered_rules", [])

    mins = int(time_in_trade // 60)
    sl_change = f"₹{old_sl:.2f} → ₹{new_sl:.2f}" if new_sl else f"₹{old_sl:.2f} (unch)"

    print(
        f"  [RISK] {symbol:<10} | {decision:<16} | "
        f"Reason: {reason_code:<25} | "
        f"LTP: ₹{ltp:.2f} | Entry: ₹{entry:.2f} | Qty: {qty} | "
        f"PnL: {pnl_pct:+.1f}% (₹{pnl_rupees_total:+.0f}) | "
        f"MFE: +{mfe_pct:.1f}% | MAE: {mae_pct:.1f}% | "
        f"SL: {sl_change} | "
        f"Time: {mins}m | Rules: {triggered}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN MONITOR LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_risk_monitor(db: Session = None, force: bool = False) -> dict:
    """Run the risk monitor for all truly open trades.

    Args:
        db: SQLAlchemy session (creates own if None)
        force: If True, skip market-hours check

    Returns:
        Summary dict with results for each monitored trade.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        now = datetime.now(IST)
        run_started = _now_ms()

        # Skip if market is closed (unless forced)
        if not force and not _market_is_open():
            return {
                "status": "skipped",
                "reason": "market_closed",
                "checked_at": run_started,
                "time": now.strftime("%H:%M:%S IST"),
                "results": [],
            }

        # ── Step 1: Get all active (open) trades ─────────────────────────
        # We monitor DBPaperTrade (status == "OPEN") since this represents
        # actual live positions with real entry prices and quantities.
        active_trades = (
            db.query(db_models.DBPaperTrade)
            .filter(db_models.DBPaperTrade.status == "OPEN")
            .order_by(db_models.DBPaperTrade.symbol)
            .all()
        )

        if not active_trades:
            return {
                "status": "no_active_trades",
                "checked_at": run_started,
                "time": now.strftime("%H:%M:%S IST"),
                "total_monitored": 0,
                "results": [],
            }

        # ── Step 2: Evaluate each trade ──────────────────────────────────
        results = []
        summary = {
            "hold": 0,
            "tighten_stoploss": 0,
            "partial_exit": 0,
            "exit_now": 0,
            "skipped": 0,
            "errors": 0,
        }

        for trade in active_trades:
            try:
                result = _evaluate_single_trade(trade, db)
                if result is None:
                    summary["skipped"] += 1
                    continue

                decision = result.get("decision", "HOLD")
                decision_key = decision.lower()
                if decision_key in summary:
                    summary[decision_key] += 1

                results.append({
                    "trade_id": trade.id,
                    "symbol": trade.symbol,
                    "signal_id": trade.signal_id,
                    "decision": decision,
                    "reason_code": result.get("reason_code", ""),
                    "confidence": result.get("confidence", 0),
                    "primary_reason": result.get("primary_reason", ""),
                    "updated_stop_loss": result.get("updated_stop_loss"),
                    "exit_fraction": result.get("exit_fraction", 0.0),
                    "triggered_rules": result.get("triggered_rules", []),
                    "pnl_percent": result.get("pnl_percent", 0),
                    "pnl_rupees_total": result.get("pnl_rupees_total", 0),
                })

                # ── Persist to DB ────────────────────────────────────────
                trade.updated_at = _now_ms()

                # If SL was tightened, update the trade's stop_loss natively
                new_sl = result.get("updated_stop_loss")
                if new_sl is not None and decision == "TIGHTEN_STOPLOSS":
                    trade.stop_loss = new_sl

                # If EXIT_NOW, close the paper trade immediately
                if decision == "EXIT_NOW":
                    ltp = result.get("_features_snapshot", {}).get("ltp") or trade.current_price
                    close_paper_trade(db, trade.id, ltp, "RISK_MONITOR_EXIT")

                # Also update DBTradeSignal to keep dashboard UI in sync
                if trade.signal_id:
                    sig = db.query(db_models.DBTradeSignal).filter_by(id=trade.signal_id).first()
                    if sig:
                        sig.risk_monitor_status = decision
                        sig.risk_monitor_data = result
                        sig.risk_last_checked_at = _now_ms()
                        # Ensure signal's stop_loss stays in sync with the paper trade
                        if new_sl is not None and decision == "TIGHTEN_STOPLOSS":
                            sig.stop_loss = new_sl

                db.commit()

            except Exception as e:
                db.rollback()
                print(f"  [ERROR] Risk monitor failed for {trade.symbol}: {e}")
                traceback.print_exc()
                summary["errors"] += 1
                results.append({
                    "symbol": trade.symbol,
                    "trade_id": trade.id,
                    "decision": "ERROR",
                    "error": str(e),
                })

        duration = _now_ms() - run_started

        return {
            "status": "completed",
            "checked_at": run_started,
            "time": now.strftime("%H:%M:%S IST"),
            "total_monitored": len(active_trades),
            "summary": summary,
            "results": results,
            "duration_ms": duration,
        }

    except Exception as e:
        print(f"[RISK MONITOR] Critical error: {e}")
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "checked_at": _now_ms(),
        }
    finally:
        if own_session:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE TRADE EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_single_trade(trade: db_models.DBPaperTrade, db: Session) -> dict | None:
    """Evaluate risk for a single truly open trade.

    Returns:
        Risk monitor output dict, or None if skipped (too soon since last check).
    """
    symbol = trade.symbol

    # ── Throttle: skip if checked too recently ────────────────────────────
    # For paper trades, we use updated_at as proxy for last check, 
    # but to be safe we'll use DBTradeSignal.risk_last_checked_at if linked
    last_check = trade.updated_at
    if trade.signal_id:
        sig = db.query(db_models.DBTradeSignal).filter_by(id=trade.signal_id).first()
        if sig and sig.risk_last_checked_at:
            last_check = sig.risk_last_checked_at

    now_ms = _now_ms()
    elapsed = (now_ms - last_check) / 1000
    if elapsed < MIN_CHECK_INTERVAL_SECONDS:
        return None

    # ── Build flattened signal dict for feature extraction ───────────────
    signal_dict = {
        "symbol": symbol,
        "trade_mode": trade.trade_mode,
        "direction": trade.action,
        "quantity": trade.quantity,
        "executed_at": trade.entry_time,
        "entry_price": trade.entry_price,
        "stop_loss": trade.stop_loss,
        "target_price": trade.target_price,
        "id": trade.id,
        "signal_id": trade.signal_id,
    }

    # ── Step 1: Fetch live data ──────────────────────────────────────────
    live_quote = fetch_live_quote(symbol)
    if live_quote.get("error"):
        print(f"    [WARN] {symbol}: Live quote error: {live_quote['error']}")
        return {
            "decision": "HOLD",
            "reason_code": "DATA_UNAVAILABLE",
            "confidence": 30,
            "primary_reason": f"Live data unavailable: {live_quote['error']}. Defaulting to HOLD.",
            "triggered_rules": ["data_unavailable"],
            "updated_stop_loss": None,
            "exit_fraction": 0.0,
            "pnl_percent": 0,
            "time_in_trade_seconds": 0,
            "pnl_rupees_total": 0,
            "_features_snapshot": {},
        }

    candles = fetch_intraday_candles(symbol, interval_minutes=5)
    depth = fetch_market_depth(symbol)

    # ── Step 2: Extract features ─────────────────────────────────────────
    features = extract_risk_features(
        signal=signal_dict,
        live_quote=live_quote,
        candles=candles,
        depth=depth,
    )

    # ── Step 3: Run rule engine (strict priority, no scoring) ────────────
    old_sl = trade.stop_loss or 0
    result = evaluate_trade(features)

    # ── Step 4: Log decision ─────────────────────────────────────────────
    _log_decision(trade.id, symbol, features, result, old_sl)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_risk_monitor_summary(db: Session = None) -> dict:
    """Get current risk monitor state for all active (open) trades.

    Returns a summary for dashboard/API display without re-running the monitor.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        today = datetime.now(IST).strftime("%Y-%m-%d")
        
        # Pull from DBPaperTrade directly since it is the source of truth for open trades
        open_trades = (
            db.query(db_models.DBPaperTrade)
            .filter(db_models.DBPaperTrade.status == "OPEN")
            .all()
        )

        trades = []
        for t in open_trades:
            # We also get the DBTradeSignal for the enriched RM data if available
            rm_data = {}
            rm_status = "not_checked"
            last_check = t.updated_at
            
            if t.signal_id:
                sig = db.query(db_models.DBTradeSignal).filter_by(id=t.signal_id).first()
                if sig:
                    rm_data = sig.risk_monitor_data if isinstance(sig.risk_monitor_data, dict) else {}
                    rm_status = sig.risk_monitor_status or "not_checked"
                    last_check = sig.risk_last_checked_at or t.updated_at
            
            trades.append({
                "trade_id": t.id,
                "signal_id": t.signal_id,
                "symbol": t.symbol,
                "trade_mode": t.trade_mode,
                "entry_price": t.entry_price,
                "quantity": t.quantity,
                "stop_loss": t.stop_loss,
                "target_price": t.target_price,
                "risk_monitor_status": rm_status,
                "reason_code": rm_data.get("reason_code", ""),
                "confidence": rm_data.get("confidence", 0),
                "primary_reason": rm_data.get("primary_reason", ""),
                "triggered_rules": rm_data.get("triggered_rules", []),
                "pnl_percent": rm_data.get("pnl_percent", 0),
                "pnl_rupees_total": rm_data.get("pnl_rupees_total", 0),
                "updated_stop_loss": rm_data.get("updated_stop_loss"),
                "last_checked_at": last_check,
            })

        return {
            "market_date": today,
            "total_active_trades": len(trades),
            "market_open": _market_is_open(),
            "trades": trades,
        }

    finally:
        if own_session:
            db.close()
