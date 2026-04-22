"""Risk Monitor Agent (Agent 4) — Post-entry trade protection engine.

This is the main orchestrator for the live risk monitoring system.
It continuously evaluates every open (planned) trade and produces
HOLD / HOLD_WITH_CAUTION / TIGHTEN_STOPLOSS / PARTIAL_EXIT / EXIT_NOW decisions.

Pipeline for each monitored trade:
  1. Fetch live quote + intraday candles + market depth
  2. Extract normalized risk features (risk_features.py)
  3. Run hard invalidation checks (risk_rules.py)
  4. If no hard invalidation → compute weighted risk score (risk_rules.py)
  5. Determine base decision from rule engine (risk_rules.py)
  6. For borderline cases (risk_score 30-70) → optionally use Gemini (gemini_risk_monitor.py)
  7. Merge final decision and persist to DB

Integration points:
  - Reads from: DBTradeSignal where execution_status='planned'
  - Writes to: risk_monitor_status, risk_monitor_data, risk_last_checked_at columns
  - Triggered by: APScheduler interval job (every 30s during market hours)
  - Exposed via: /api/agent/risk-monitor endpoints
"""

import time
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
from agent.risk_rules import (
    check_hard_invalidations,
    compute_risk_score,
    determine_risk_decision,
)
from agent.gemini_risk_monitor import evaluate_risk_with_llm

IST = timezone(timedelta(hours=5, minutes=30))

# Minimum interval between checks for the same trade (seconds)
MIN_CHECK_INTERVAL_SECONDS = 25

# Use LLM for borderline risk scores within this range
LLM_BORDERLINE_LOW = 30
LLM_BORDERLINE_HIGH = 70


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
# MAIN MONITOR LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_risk_monitor(db: Session = None, force: bool = False) -> dict:
    """Run the risk monitor for all active (planned) trades.

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

        # ── Step 1: Get all active (planned) trades ──────────────────────
        today = now.strftime("%Y-%m-%d")
        active_trades = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.execution_status == "planned")
            .filter(db_models.DBTradeSignal.market_date == today)
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
            "hold_with_caution": 0,
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
                    "symbol": trade.symbol,
                    "signal_id": trade.id,
                    "decision": decision,
                    "confidence": result.get("confidence", 0),
                    "risk_score": result.get("risk_score", 0),
                    "thesis_status": result.get("thesis_status", "unknown"),
                    "exit_urgency": result.get("exit_urgency", "none"),
                    "primary_reason": result.get("primary_reason", ""),
                    "triggered_risks": result.get("triggered_risks", []),
                    "source": result.get("_source", "unknown"),
                })

                # ── Persist to DB ────────────────────────────────────────
                trade.risk_monitor_status = decision
                trade.risk_monitor_data = result
                trade.risk_last_checked_at = _now_ms()
                db.flush()

            except Exception as e:
                print(f"  [ERROR] Risk monitor failed for {trade.symbol}: {e}")
                traceback.print_exc()
                summary["errors"] += 1
                results.append({
                    "symbol": trade.symbol,
                    "signal_id": trade.id,
                    "decision": "ERROR",
                    "error": str(e),
                })

        db.commit()
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

def _evaluate_single_trade(trade, db: Session) -> dict | None:
    """Evaluate risk for a single active trade.

    Returns:
        Risk monitor output dict, or None if skipped (too soon since last check).
    """
    symbol = trade.symbol

    # ── Throttle: skip if checked too recently ────────────────────────────
    last_check = trade.risk_last_checked_at or 0
    now_ms = _now_ms()
    elapsed = (now_ms - last_check) / 1000
    if elapsed < MIN_CHECK_INTERVAL_SECONDS:
        return None

    # ── Build signal dict for feature extraction ─────────────────────────
    signal_dict = {
        "symbol": symbol,
        "trade_mode": trade.trade_mode,
        "execution_data": trade.execution_data if isinstance(trade.execution_data, dict) else {},
        "reasoning": trade.reasoning if isinstance(trade.reasoning, dict) else {},
        "confirmation_data": trade.confirmation_data if isinstance(trade.confirmation_data, dict) else {},
        "executed_at": trade.executed_at,
        "entry_price": trade.entry_price,
        "stop_loss": trade.stop_loss,
        "target_price": trade.target_price,
    }

    # ── Step 1: Fetch live data ──────────────────────────────────────────
    live_quote = fetch_live_quote(symbol)
    if live_quote.get("error"):
        print(f"    [WARN] {symbol}: Live quote error: {live_quote['error']}")
        # Don't crash — return a safe HOLD with low confidence
        return {
            "decision": "HOLD",
            "confidence": 30,
            "risk_score": 0,
            "thesis_status": "unknown",
            "exit_urgency": "none",
            "primary_reason": f"Live data unavailable: {live_quote['error']}. Defaulting to HOLD.",
            "triggered_risks": ["data_unavailable"],
            "execution_note": "Monitor manually. Live data fetch failed.",
            "next_review_priority": "high",
            "_source": "data_error_fallback",
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

    # ── Step 3: Hard invalidation check ──────────────────────────────────
    hard_result = check_hard_invalidations(features)

    # ── Step 4: Soft risk scoring ────────────────────────────────────────
    risk_scoring = compute_risk_score(features)

    # ── Step 5: Base decision from rule engine ───────────────────────────
    rule_decision = determine_risk_decision(
        features=features,
        risk_scoring=risk_scoring,
        hard_invalidation=hard_result,
    )

    # ── Step 6: Optional LLM overlay for borderline cases ────────────────
    composite = risk_scoring["composite_score"]
    use_llm = (
        hard_result is None  # No hard invalidation
        and LLM_BORDERLINE_LOW <= composite <= LLM_BORDERLINE_HIGH  # Borderline score
    )

    if use_llm:
        llm_result = evaluate_risk_with_llm(
            signal=signal_dict,
            features=features,
            rule_engine_result=rule_decision,
        )

        # Merge: LLM can upgrade or downgrade by at most 1 level
        final_result = _merge_decisions(rule_decision, llm_result)
    else:
        final_result = rule_decision

    return final_result


# ═══════════════════════════════════════════════════════════════════════════════
# DECISION MERGING
# ═══════════════════════════════════════════════════════════════════════════════

DECISION_SEVERITY = {
    "HOLD": 0,
    "HOLD_WITH_CAUTION": 1,
    "TIGHTEN_STOPLOSS": 2,
    "PARTIAL_EXIT": 3,
    "EXIT_NOW": 4,
}


def _merge_decisions(rule_result: dict, llm_result: dict) -> dict:
    """Merge rule engine and LLM decisions.

    Rules:
    - If both agree, use LLM result (better reasoning)
    - If LLM is more conservative (higher severity), trust LLM
    - If LLM is more aggressive (lower severity), limit downgrade to 1 level
    - Always preserve hard invalidation from rule engine
    """
    rule_dec = rule_result.get("decision", "HOLD")
    llm_dec = llm_result.get("decision", "HOLD")

    rule_sev = DECISION_SEVERITY.get(rule_dec, 0)
    llm_sev = DECISION_SEVERITY.get(llm_dec, 0)

    if rule_sev == llm_sev:
        # Agreement — use LLM (better reasoning)
        final = dict(llm_result)
        final["_merge_strategy"] = "agreement"
    elif llm_sev > rule_sev:
        # LLM is more conservative — trust it
        final = dict(llm_result)
        final["_merge_strategy"] = "llm_escalated"
    else:
        # LLM wants to downgrade — limit to 1 level
        max_downgrade_sev = max(0, rule_sev - 1)
        effective_sev = max(max_downgrade_sev, llm_sev)

        # Find the decision name for effective severity
        sev_to_dec = {v: k for k, v in DECISION_SEVERITY.items()}
        effective_dec = sev_to_dec.get(effective_sev, rule_dec)

        if effective_sev == llm_sev:
            final = dict(llm_result)
            final["decision"] = effective_dec
        else:
            final = dict(rule_result)
            final["decision"] = effective_dec

        final["_merge_strategy"] = "llm_downgrade_limited"

    final["_rule_engine_decision"] = rule_dec
    final["_llm_decision"] = llm_dec
    final["_source"] = "merged"
    return final


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_risk_monitor_summary(db: Session = None) -> dict:
    """Get current risk monitor state for all active trades.

    Returns a summary for dashboard/API display without re-running the monitor.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        today = datetime.now(IST).strftime("%Y-%m-%d")
        active_trades = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.execution_status == "planned")
            .filter(db_models.DBTradeSignal.market_date == today)
            .all()
        )

        trades = []
        for t in active_trades:
            rm_data = t.risk_monitor_data if isinstance(t.risk_monitor_data, dict) else {}
            trades.append({
                "signal_id": t.id,
                "symbol": t.symbol,
                "trade_mode": t.trade_mode,
                "entry_price": t.entry_price,
                "stop_loss": t.stop_loss,
                "target_price": t.target_price,
                "risk_monitor_status": t.risk_monitor_status or "not_checked",
                "risk_score": rm_data.get("risk_score", 0),
                "confidence": rm_data.get("confidence", 0),
                "thesis_status": rm_data.get("thesis_status", "unknown"),
                "exit_urgency": rm_data.get("exit_urgency", "none"),
                "primary_reason": rm_data.get("primary_reason", ""),
                "triggered_risks": rm_data.get("triggered_risks", []),
                "last_checked_at": t.risk_last_checked_at,
                "source": rm_data.get("_source", "not_checked"),
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
