"""Risk Monitor Agent (Agent 4) — Agent-led live trade protection engine.

This is the main orchestrator for the live risk monitoring system.
It evaluates every open trade using an LLM-powered risk agent,
validates the output through guardrails, and persists the decision.

Architecture:
  Live Data → Feature Extraction → Risk Agent (LLM) → Validator → Persist → Log

Fallback hierarchy:
  1. LLM agent produces a judgment
  2. Validator sanitizes and enforces safety rules
  3. If LLM fails entirely, deterministic rule engine runs as backup
  4. Validator still runs on rule engine output (same safety guarantees)
  5. Hard overrides always fire regardless of decision source

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

from .risk_features import (
    extract_risk_features,
    fetch_live_quote,
    fetch_intraday_candles,
    fetch_market_depth,
)
from .gemini_risk_monitor import (
    evaluate_risk_with_llm,
    is_agent_available,
)
from agent.execution.risk_agent_validator import validate_agent_output
from .risk_rules import evaluate_trade as evaluate_trade_deterministic
from agent.paper_trading_engine import close_paper_trade

logger = logging.getLogger("agent.risk.risk_monitor")

IST = timezone(timedelta(hours=5, minutes=30))

# Minimum interval between checks for the same trade (seconds)
MIN_CHECK_INTERVAL_SECONDS = 25

# ═══════════════════════════════════════════════════════════════════════════════
# DECISION MEMORY — tracks last decision per trade for flip-flop detection
# ═══════════════════════════════════════════════════════════════════════════════

# In-memory cache: trade_id -> { decision, timestamp_ms, validated_result }
_decision_memory: dict[str, dict] = {}

# Flip-flop thresholds
FLIP_FLOP_WINDOW_MS = 120_000       # 2 minutes — if decision reverses within this window
FLIP_FLOP_MAX_REVERSALS = 3         # Max allowed reversals before flagging

# Aggressive decision pairs that constitute a "flip-flop"
_FLIP_PAIRS = {
    ("EXIT_NOW", "HOLD"),
    ("HOLD", "EXIT_NOW"),
    ("PARTIAL_EXIT", "HOLD"),
    ("HOLD", "PARTIAL_EXIT"),
    ("EXIT_NOW", "TIGHTEN_STOPLOSS"),
    ("TIGHTEN_STOPLOSS", "EXIT_NOW"),
}


def _record_decision(trade_id: str, validated_result: dict):
    """Store the latest decision for a trade in memory."""
    now_ms = _now_ms()
    entry = _decision_memory.get(trade_id)

    reversals = 0
    if entry:
        old_decision = entry.get("decision", "HOLD")
        new_decision = validated_result.get("decision", "HOLD")
        old_reversals = entry.get("reversals", 0)
        old_ts = entry.get("timestamp_ms", 0)

        # Check if this is a flip-flop (aggressive reversal within the window)
        if (old_decision, new_decision) in _FLIP_PAIRS:
            if (now_ms - old_ts) < FLIP_FLOP_WINDOW_MS:
                reversals = old_reversals + 1
            else:
                reversals = 0

    _decision_memory[trade_id] = {
        "decision": validated_result.get("decision", "HOLD"),
        "timestamp_ms": now_ms,
        "validated_result": validated_result,
        "reversals": reversals,
    }


def _get_previous_state(trade_id: str) -> dict | None:
    """Get the previous validated result for a trade, if available."""
    entry = _decision_memory.get(trade_id)
    if entry:
        return entry.get("validated_result")
    return None


def _check_flip_flop(trade_id: str, validated_result: dict) -> list[str]:
    """Check if the new decision constitutes a flip-flop.

    Returns a list of risk flags to append if flip-flopping is detected.
    """
    flags = []
    entry = _decision_memory.get(trade_id)
    if not entry:
        return flags

    old_decision = entry.get("decision", "HOLD")
    new_decision = validated_result.get("decision", "HOLD")
    reversals = entry.get("reversals", 0)
    old_ts = entry.get("timestamp_ms", 0)
    now_ms = _now_ms()

    if (old_decision, new_decision) in _FLIP_PAIRS:
        elapsed_sec = (now_ms - old_ts) / 1000
        if elapsed_sec < (FLIP_FLOP_WINDOW_MS / 1000):
            flags.append(f"flip_flop:{old_decision}->{new_decision}")

            if reversals >= FLIP_FLOP_MAX_REVERSALS:
                flags.append("flip_flop_excessive")
                logger.warning(
                    f"{trade_id}: Excessive flip-flopping detected "
                    f"({reversals} reversals in {elapsed_sec:.0f}s). "
                    f"Latest: {old_decision} -> {new_decision}"
                )

    return flags


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

def _log_decision(
    trade_id: str,
    symbol: str,
    features: dict,
    result: dict,
    old_sl: float,
    decision_source: str,
):
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
    confidence = result.get("confidence", 0)
    thesis = result.get("thesis_status", "unknown")
    urgency = result.get("urgency", "unknown")
    validation_status = result.get("_validation_status", "unknown")
    overrides = result.get("_overrides_applied", [])
    triggered = result.get("triggered_factors", result.get("triggered_rules", []))

    mins = int(time_in_trade // 60)
    sl_change = f"Rs.{old_sl:.2f} -> Rs.{new_sl:.2f}" if new_sl else f"Rs.{old_sl:.2f} (unchanged)"

    print(f"\n{'-'*60}")
    print(f" [AGENT 4: RISK MONITOR — {decision_source.upper()}]")
    print(f"   Symbol:      {symbol}")
    print(f"   LTP:         Rs.{ltp:.2f} (Entry: Rs.{entry:.2f})")
    print(f"   PnL:         {pnl_pct:+.1f}% (Rs.{pnl_rupees_total:+.0f})")
    print(f"   MFE/MAE:     +{mfe_pct:.1f}% / {mae_pct:.1f}%")
    print(f"   Time:        {mins} mins")
    print(f"   Decision:    >> {decision} <<  [conf={confidence}, thesis={thesis}, urgency={urgency}]")
    print(f"   Reason:      {reason_code}")
    print(f"   Source:      {decision_source.upper()} [{result.get('_decision_source_label', '')}]")
    print(f"   Factors:     {triggered}")
    print(f"   SL:          {sl_change}")
    print(f"   Validation:  {validation_status}")
    if overrides:
        print(f"   Overrides:   {overrides}")
    print(f"{'-'*60}\n")

    # Also log to Python logger for file-based audit
    logger.info(
        f"RISK_DECISION | {symbol} | {decision} | {reason_code} | "
        f"pnl={pnl_pct:+.1f}% | conf={confidence} | thesis={thesis} | "
        f"urgency={urgency} | source={decision_source} | "
        f"validation={validation_status} | overrides={len(overrides)}"
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
                    "thesis_status": result.get("thesis_status", "unknown"),
                    "urgency": result.get("urgency", "unknown"),
                    "triggered_factors": result.get("triggered_factors", []),
                    "triggered_rules": result.get("triggered_rules", []),
                    "risk_flags": result.get("risk_flags", []),
                    "pnl_percent": result.get("pnl_percent", 0),
                    "pnl_rupees_total": result.get("pnl_rupees_total", 0),
                    "_decision_source": result.get("_decision_source", result.get("_source", "unknown")),
                    "_decision_source_label": result.get("_decision_source_label", ""),
                })

                # ══════════════════════════════════════════════════════════
                # DECISION EXECUTION — every decision type handled explicitly
                # ══════════════════════════════════════════════════════════
                trade.updated_at = _now_ms()
                new_sl = result.get("updated_stop_loss")
                ltp = result.get("_features_snapshot", {}).get("ltp") or trade.current_price

                # ── MARK-TO-MARKET UPDATE: update live price + PnL every risk cycle ──
                if ltp is not None and ltp > 0:
                    trade.current_price = round(float(ltp), 2)

                    if trade.action == "BUY":
                        trade.pnl = round((trade.current_price - trade.entry_price) * trade.quantity, 2)
                        trade.pnl_percent = round(
                            ((trade.current_price - trade.entry_price) / trade.entry_price) * 100,
                            2
                        ) if trade.entry_price else 0.0
                    else:
                        trade.pnl = round((trade.entry_price - trade.current_price) * trade.quantity, 2)
                        trade.pnl_percent = round(
                            ((trade.entry_price - trade.current_price) / trade.entry_price) * 100,
                            2
                        ) if trade.entry_price else 0.0

                # ── EXIT_NOW: close the entire position immediately ───────
                if decision == "EXIT_NOW":
                    close_result = close_paper_trade(db, trade.id, ltp, "RISK_MONITOR_EXIT")
                    if close_result.get("success") and trade.signal_id:
                        sig = db.query(db_models.DBTradeSignal).filter_by(id=trade.signal_id).first()
                        if sig:
                            sig.risk_monitor_data = result
                            db.commit()

                # ── PARTIAL_EXIT: close entire position (partial close removed) ─
                elif decision == "PARTIAL_EXIT":
                    close_result = close_paper_trade(db, trade.id, ltp, "RISK_MONITOR_PARTIAL_EXIT")
                    if close_result.get("success") and trade.signal_id:
                        sig = db.query(db_models.DBTradeSignal).filter_by(id=trade.signal_id).first()
                        if sig:
                            sig.risk_monitor_status = "PARTIAL_EXIT"
                            sig.risk_monitor_data = result
                            sig.risk_last_checked_at = _now_ms()
                    elif not close_result.get("success"):
                        print(f"  [WARN] Exit failed for {trade.symbol}: {close_result.get('error')}")

                # ── TIGHTEN_STOPLOSS: trail the stop loss upward ──────────
                elif decision == "TIGHTEN_STOPLOSS":
                    old_sl = trade.stop_loss
                    sl_updated = False

                    if new_sl is not None:
                        # Validator already ensures new_sl > old_sl for longs
                        # and new_sl < old_sl for shorts, but we double-check
                        is_long = (trade.action == "BUY")
                        sl_is_tighter = (new_sl > old_sl) if is_long else (new_sl < old_sl)

                        if sl_is_tighter:
                            trade.stop_loss = new_sl
                            trade.max_loss_at_sl = round(
                                abs(trade.entry_price - new_sl) * trade.quantity, 2
                            )
                            sl_updated = True

                            print(f"\n{'='*50}")
                            print(f" [AUTOMATION: STOP LOSS TRAILED]")
                            print(f"   Symbol:    {trade.symbol}")
                            print(f"   Old SL:    Rs.{old_sl:.2f}")
                            print(f"   New SL:    Rs.{new_sl:.2f}")
                            print(f"   Direction: {'UP' if is_long else 'DOWN'} (tighter)")
                            print(f"   Max Loss:  Rs.{trade.max_loss_at_sl:.2f}")
                            print(f"   Reason:    {result.get('reason_code', 'AGENT_TRAIL')}")
                            print(f"{'='*50}\n")

                    if not sl_updated:
                        print(f"  [INFO] {trade.symbol}: TIGHTEN_STOPLOSS decision but no valid SL change"
                              f" (proposed={new_sl}, current={old_sl})")

                    # Sync to signal
                    if trade.signal_id:
                        sig = db.query(db_models.DBTradeSignal).filter_by(id=trade.signal_id).first()
                        if sig:
                            sig.risk_monitor_status = decision
                            sig.risk_monitor_data = result
                            sig.risk_last_checked_at = _now_ms()
                            if sl_updated:
                                sig.stop_loss = new_sl

                # ── HOLD: no action, just update dashboard ────────────────
                elif decision == "HOLD":
                    if trade.signal_id:
                        sig = db.query(db_models.DBTradeSignal).filter_by(id=trade.signal_id).first()
                        if sig:
                            sig.risk_monitor_status = decision
                            sig.risk_monitor_data = result
                            sig.risk_last_checked_at = _now_ms()

                # ── HOLD_WITH_CAUTION: same as HOLD but flagged ───────────
                else:
                    # Covers HOLD_WITH_CAUTION and any unexpected decisions
                    if trade.signal_id:
                        sig = db.query(db_models.DBTradeSignal).filter_by(id=trade.signal_id).first()
                        if sig:
                            sig.risk_monitor_status = decision
                            sig.risk_monitor_data = result
                            sig.risk_last_checked_at = _now_ms()

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
            "agent_available": is_agent_available(),
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
# SINGLE TRADE EVALUATION — Agent-Led with Fallback
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_single_trade(trade: db_models.DBPaperTrade, db: Session) -> dict | None:
    """Evaluate risk for a single open trade using the agent-led pipeline.

    Pipeline:
      1. Throttle check (skip if too recent)
      2. Fetch live data (quote, candles, depth)
      3. Extract features
      4. Call LLM risk agent
      5. If LLM fails → run deterministic rule engine as fallback
      6. Validate output through guardrails
      7. Log raw + validated decision
      8. Return validated result

    Returns:
        Risk monitor output dict, or None if skipped (too soon since last check).
    """
    symbol = trade.symbol

    # ── Throttle: skip if checked too recently ────────────────────────────
    # We must use entry_time, NOT updated_at, because the 15s paper trading monitor
    # constantly refreshes updated_at, which would infinitely starve the 25s risk monitor.
    last_check = trade.entry_time or trade.created_at
    
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
            "thesis_status": "intact",
            "urgency": "low",
            "triggered_factors": ["data_unavailable"],
            "triggered_rules": ["data_unavailable"],
            "risk_flags": ["data_unavailable"],
            "monitoring_note": "Retry on next cycle when data is available.",
            "updated_stop_loss": None,
            "exit_fraction": 0.0,
            "pnl_percent": 0,
            "time_in_trade_seconds": 0,
            "pnl_rupees_total": 0,
            "_features_snapshot": {},
            "_source": "data_error",
            "_validation_status": "clean",
            "_overrides_applied": [],
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

    old_sl = trade.stop_loss or 0
    decision_source = "agent"

    # ── Retrieve previous state for delta/change detection ──────────────
    previous_state = _get_previous_state(trade.id)

    # ── Step 3: Call LLM risk agent ──────────────────────────────────────
    raw_agent_output = evaluate_risk_with_llm(
        features=features,
        depth=depth,
        previous_state=previous_state,
    )

    # ── Step 4: Determine if we need deterministic fallback ──────────────
    agent_source = raw_agent_output.get("_source", "unknown")
    agent_failed = agent_source in ("agent4_fallback", "agent4_parse_error")

    if agent_failed:
        # LLM failed — run deterministic rule engine as backup decision-maker
        decision_source = "rule_engine_fallback"
        logger.info(f"{symbol}: Agent failed ({agent_source}), running deterministic fallback")

        rule_result = evaluate_trade_deterministic(features)

        # Convert rule engine output to match agent schema
        raw_agent_output = _adapt_rule_engine_output(rule_result, raw_agent_output)

    # ── Step 5: Validate through guardrails ──────────────────────────────
    validated_result = validate_agent_output(
        raw_output=raw_agent_output,
        features=features,
        apply_hard_overrides=True,
    )

    # Preserve source info
    validated_result["_source"] = agent_source if not agent_failed else "rule_engine_fallback"

    # ── Step 6: Flip-flop detection ──────────────────────────────────────
    flip_flags = _check_flip_flop(trade.id, validated_result)
    if flip_flags:
        existing_flags = validated_result.get("risk_flags", [])
        validated_result["risk_flags"] = existing_flags + flip_flags
        validated_result["monitoring_note"] = (
            validated_result.get("monitoring_note", "") +
            f" | FLIP-FLOP DETECTED: {flip_flags}"
        ).strip(" | ")

    # ── Step 7: Record decision in memory ────────────────────────────────
    _record_decision(trade.id, validated_result)

    # ── Step 8: Log the decision ─────────────────────────────────────────
    _log_decision(trade.id, symbol, features, validated_result, old_sl, decision_source)

    return validated_result


def _adapt_rule_engine_output(rule_result: dict, failed_agent_output: dict) -> dict:
    """Adapt deterministic rule engine output to match the agent output schema.

    The rule engine uses 'triggered_rules' while the agent uses 'triggered_factors'.
    This function bridges the two schemas so the validator works uniformly.
    """
    # The rule engine already provides: decision, reason_code, primary_reason,
    # updated_stop_loss, exit_fraction, confidence, triggered_rules
    adapted = {
        "decision": rule_result.get("decision", "HOLD"),
        "reason_code": rule_result.get("reason_code", "RULE_ENGINE"),
        "primary_reason": rule_result.get("primary_reason", "Deterministic rule engine decision."),
        "updated_stop_loss": rule_result.get("updated_stop_loss"),
        "exit_fraction": rule_result.get("exit_fraction", 0.0),
        "confidence": rule_result.get("confidence", 70),
        "triggered_factors": rule_result.get("triggered_rules", []),
        "risk_flags": ["llm_unavailable", "rule_engine_used"],
        "monitoring_note": (
            f"Decision from deterministic fallback. "
            f"Agent error: {failed_agent_output.get('_error', 'unknown')}"
        ),
    }

    # Infer thesis_status from rule engine decision
    decision = adapted["decision"]
    if decision == "EXIT_NOW":
        adapted["thesis_status"] = "broken"
        adapted["urgency"] = "high"
    elif decision == "PARTIAL_EXIT":
        adapted["thesis_status"] = "weakening"
        adapted["urgency"] = "medium"
    elif decision == "TIGHTEN_STOPLOSS":
        adapted["thesis_status"] = "weakening"
        adapted["urgency"] = "medium"
    else:
        adapted["thesis_status"] = "intact"
        adapted["urgency"] = "low"

    # Preserve the source metadata from the failed agent call
    adapted["_source"] = "rule_engine_fallback"
    adapted["_model"] = failed_agent_output.get("_model", "rule_engine")
    adapted["_latency_ms"] = failed_agent_output.get("_latency_ms", 0)

    return adapted


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
                "thesis_status": rm_data.get("thesis_status", "unknown"),
                "urgency": rm_data.get("urgency", "unknown"),
                "triggered_rules": rm_data.get("triggered_rules", []),
                "triggered_factors": rm_data.get("triggered_factors", []),
                "risk_flags": rm_data.get("risk_flags", []),
                "pnl_percent": rm_data.get("pnl_percent", 0),
                "pnl_rupees_total": rm_data.get("pnl_rupees_total", 0),
                "updated_stop_loss": rm_data.get("updated_stop_loss"),
                "last_checked_at": last_check,
                "_decision_source": rm_data.get("_decision_source", rm_data.get("_source", "unknown")),
                "_decision_source_label": rm_data.get("_decision_source_label", ""),
            })

        return {
            "market_date": today,
            "total_active_trades": len(trades),
            "market_open": _market_is_open(),
            "agent_available": is_agent_available(),
            "trades": trades,
        }

    finally:
        if own_session:
            db.close()
