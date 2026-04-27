"""Market Open Confirmation Agent — Phase 2 of the trading pipeline.

Runs at 9:20 AM IST (5 minutes after NSE market open).
Takes Agent 1's Discovery assessments (pending_confirmation) and validates
them against LIVE market-open data using the Market Reality Validator.

Pipeline:
  1. Query DB for today's signals where confirmation_status = 'pending'
  2. For each WATCH signal:
     a. Fetch LIVE stock data (current price, volume, open, high/low)
     b. Build Agent 2 input: agent_1_view + market_data + technical_context
     c. Send to Market Reality Validator (Gemini or fallback)
     d. Update signal: confirmation_status, confirmation_data
  3. Return summary of all validations

Agent 2 does NOT generate trades — it only validates and filters.
"""

import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from agent.data_collector import fetch_stock_data_for_symbols
from agent.gemini_confirmer import confirm_signal_v2

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _build_agent2_input(sig, live_data: dict, discovery_output: dict, snapshot: dict) -> dict:
    """
    Build the standardised Agent 2 input contract from DB signal + live data.

    Returns the new-schema input:
    {
      stock: { symbol, company_name, exchange },
      agent_1_view: { final_bias, final_confidence, combined_trading_thesis, ... },
      market_data: { previous_close, open_price, ltp, ..., technical_context: {...} }
    }
    """
    symbol = sig.symbol

    # Extract Agent 1 combined_view
    cv = discovery_output.get("combined_view", {})
    reasoning = cv.get("reasoning", {})

    agent_1_view = {
        "final_bias": cv.get("final_bias", "NEUTRAL"),
        "final_confidence": cv.get("final_confidence", "LOW"),
        "executive_summary": cv.get("executive_summary", ""),
        "why_this_stock_is_important_today": cv.get("why_this_stock_is_important_today", ""),
        "combined_trading_thesis": cv.get("combined_trading_thesis", ""),
        "combined_invalidation": cv.get("combined_invalidation", ""),
        "key_risks": cv.get("key_risks", []),
        "reasoning": {
            "why_agent_gave_this_view": reasoning.get("why_agent_gave_this_view", ""),
            "main_driver": reasoning.get("main_driver", ""),
            "supporting_points": reasoning.get("supporting_points", []),
            "risk_points": reasoning.get("risk_points", []),
            "confidence_reason": reasoning.get("confidence_reason", ""),
            "what_agent_2_should_validate": reasoning.get("what_agent_2_should_validate", []),
        },
    }

    # Build market_data from live prices
    prev_close = snapshot.get("last_close") or live_data.get("last_close") or 0
    open_price = live_data.get("today_open", 0) or 0
    ltp = live_data.get("ltp", open_price) or 0
    day_high = live_data.get("today_high", 0) or 0
    day_low = live_data.get("today_low", 0) or 0

    gap_pct = round(((open_price - prev_close) / prev_close * 100), 2) if prev_close else 0.0

    # Volume ratio
    avg_vol = snapshot.get("avg_volume_20d") or 0
    current_vol = live_data.get("current_volume", 0) or 0
    volume_ratio = round(current_vol / avg_vol, 2) if avg_vol and avg_vol > 0 else 0.0

    # Time since open (approx)
    now = datetime.now(IST)
    market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    time_since_open = max(0, round((now - market_open_time).total_seconds() / 60, 1))

    # Build technical_context from snapshot if available
    # This is a placeholder — in production, these come from a levels service
    technical_context = _build_technical_context(ltp, prev_close, day_high, day_low, snapshot)

    market_data = {
        "previous_close": prev_close,
        "open_price": open_price,
        "ltp": ltp,
        "day_high": day_high,
        "day_low": day_low,
        "gap_percent": gap_pct,
        "volume": current_vol,
        "average_volume_20d": avg_vol,
        "volume_ratio": volume_ratio,
        "volume_confirmation": "STRONG" if volume_ratio > 2.0 else "NORMAL" if volume_ratio > 0.8 else "WEAK",
        "time_since_open_minutes": time_since_open,
        "technical_context": technical_context,
    }

    return {
        "stock": {
            "symbol": symbol,
            "company_name": live_data.get("company_name", symbol),
            "exchange": "NSE",
        },
        "agent_1_view": agent_1_view,
        "market_data": market_data,
    }


def _build_technical_context(
    ltp: float, prev_close: float, day_high: float, day_low: float,
    snapshot: dict,
) -> dict:
    """
    Build technical_context for support/resistance validation.

    Uses snapshot data if available, otherwise derives basic levels
    from prev_close and day range as approximations.
    """
    # Try to use pre-computed levels from snapshot
    support = snapshot.get("nearest_support") or snapshot.get("support_level")
    resistance = snapshot.get("nearest_resistance") or snapshot.get("resistance_level")

    # Fallback: derive approximate levels from available data
    if not support and prev_close:
        # Use previous close as a rough support for a gap-up scenario
        # or day_low if available
        support = day_low if day_low and day_low > 0 else prev_close * 0.985

    if not resistance and prev_close:
        resistance = day_high if day_high and day_high > 0 else prev_close * 1.015

    support = float(support) if support else 0
    resistance = float(resistance) if resistance else 0

    if ltp and support and support > 0:
        sup_dist_pct = round(abs(ltp - support) / ltp * 100, 2)
        price_above_support = ltp > support
    else:
        sup_dist_pct = 99.0
        price_above_support = True

    if ltp and resistance and resistance > 0:
        res_dist_pct = round(abs(resistance - ltp) / ltp * 100, 2)
        price_below_resistance = ltp < resistance
    else:
        res_dist_pct = 99.0
        price_below_resistance = True

    return {
        "nearest_support": round(support, 2) if support else None,
        "nearest_resistance": round(resistance, 2) if resistance else None,
        "support_distance_percent": sup_dist_pct,
        "resistance_distance_percent": res_dist_pct,
        "price_above_support": price_above_support,
        "price_below_resistance": price_below_resistance,
    }


def run_market_open_confirmation(db: Session, debug_mode: bool = True) -> dict:
    """
    Execute the Market Open Confirmation pipeline (Agent 2).

    Fetches all pending_confirmation signals for today, builds the correct
    Agent 2 input, gets live market data, and validates each thesis.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        market_date = _market_date_str()
        run_id = f"confirm-{market_date}-{uuid.uuid4().hex[:8]}"
        started_at = _now_ms()

        logger.info("=" * 60)
        logger.info("[AGENT 2] MARKET REALITY VALIDATOR -- Run ID: %s", run_id)
        logger.info("   Market Date: %s", market_date)
        logger.info("   Time: %s", datetime.now(IST).strftime("%H:%M:%S IST"))
        logger.info("=" * 60)

        # -- Step 1: Get today's pending signals ----------------------------
        pending_signals = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.market_date == market_date)
            .filter(db_models.DBTradeSignal.confirmation_status == "pending")
            .order_by(db_models.DBTradeSignal.symbol)
            .all()
        )

        if not pending_signals:
            logger.warning("[AGENT 2] No pending signals found for today.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "confirmed_at": _now_ms(),
                "total_checked": 0,
                "summary": {"confirmed": 0, "weakened": 0, "invalidated": 0, "skipped": 0},
                "results": [],
                "duration_ms": 0,
            }

        # Filter tradable (WATCH only) — NO_TRADE signals are auto-skipped
        tradable_signals = [s for s in pending_signals if s.signal_type == "WATCH"]
        skip_signals = [s for s in pending_signals if s.signal_type != "WATCH"]

        # Auto-skip non-tradable signals
        results = []
        summary = {"confirmed": 0, "weakened": 0, "invalidated": 0, "skipped": 0}

        for sig in skip_signals:
            sig.confirmation_status = "invalidated"
            sig.confirmed_at = _now_ms()
            sig.status = "invalidated"
            sig.confirmation_data = {
                "validation": {"status": "INVALIDATED", "reason": f"Auto-skipped: signal_type={sig.signal_type}"},
                "decision": {"should_pass_to_agent_3": False, "agent_3_instruction": "DO_NOT_PROCEED"},
                "_source": "auto_skip",
            }
            results.append({
                "symbol": sig.symbol,
                "status": "SKIPPED",
                "reason": f"Auto-skipped: signal_type={sig.signal_type}",
            })
            summary["skipped"] += 1
            db.commit()

        if not tradable_signals:
            logger.info("[AGENT 2] No WATCH signals found to validate.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "confirmed_at": _now_ms(),
                "total_checked": len(pending_signals),
                "summary": summary,
                "results": results,
                "duration_ms": _now_ms() - started_at,
            }

        # -- Step 2: Fetch stock data (LIVE or SNAPSHOT debug) --------------
        symbols = list(set(s.symbol for s in tradable_signals))
        
        if debug_mode:
            logger.info("[AGENT 2] DEBUG MODE ENABLED — Using database snapshots instead of live fetch.")
            live_data_map = {}
            for sig in tradable_signals:
                snapshot = sig.stock_snapshot if isinstance(sig.stock_snapshot, dict) else {}
                # Map snapshot fields to live data format (using keys expected by _build_agent2_input)
                live_data_map[sig.symbol] = {
                    "ltp": snapshot.get("ltp") or snapshot.get("last_close", 0),
                    "today_open": snapshot.get("today_open", 0),
                    "today_high": snapshot.get("today_high", 0),
                    "today_low": snapshot.get("today_low", 0),
                    "current_volume": 50000000,
                    "previous_close": snapshot.get("previous_close", 0),
                    "last_close": snapshot.get("last_close", 0),
                    "vwap": snapshot.get("vwap", 0),
                    "volume_ratio": 4.5, # Strong volume confirmation
                    "_is_debug": True
                }
        else:
            live_data_map = fetch_stock_data_for_symbols(symbols)

        # Guard: total network outage
        if len(symbols) > 0 and len(live_data_map) == 0:
            logger.warning(
                "[AGENT 2] ABORTED: Live data fetch returned 0 of %d symbols. "
                "All signals remain PENDING for retry.", len(symbols)
            )
            return {
                "run_id": run_id,
                "market_date": market_date,
                "confirmed_at": _now_ms(),
                "total_checked": 0,
                "summary": summary,
                "results": [],
                "error": "network_outage",
                "error_detail": f"All {len(symbols)} live data fetches failed.",
                "duration_ms": _now_ms() - started_at,
            }

        # -- Step 3: Build inputs and run validation ------------------------
        logger.info("[AGENT 2] Validating %d signals...", len(tradable_signals))

        tasks = []
        for sig in tradable_signals:
            live_data = live_data_map.get(sig.symbol)
            if not live_data:
                sig.confirmation_status = "invalidated"
                sig.confirmed_at = _now_ms()
                sig.status = "invalidated"
                sig.confirmation_data = {
                    "validation": {"status": "INVALIDATED", "reason": "Live data unavailable"},
                    "decision": {"should_pass_to_agent_3": False, "agent_3_instruction": "DO_NOT_PROCEED"},
                    "_source": "no_data_skip",
                }
                summary["skipped"] += 1
                logger.warning("   [SKIP] %s: No live data — isolated fetch failure", sig.symbol)
                continue

            discovery_output = sig.reasoning if isinstance(sig.reasoning, dict) else {}
            snapshot = sig.stock_snapshot if isinstance(sig.stock_snapshot, dict) else {}

            agent2_input = _build_agent2_input(sig, live_data, discovery_output, snapshot)
            tasks.append((sig, agent2_input, discovery_output))

        db.commit()

        # Run Gemini calls concurrently
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _validate_one(symbol, inp):
            logger.info("   [GEMINI] Agent 2 validating %s...", symbol)
            try:
                res = confirm_signal_v2(inp, market_date)
                status = res.get("validation", {}).get("status", "WEAKENED")
                logger.info("   [OK] %s: status=%s", symbol, status)
                return symbol, res
            except Exception as e:
                logger.error("   [ERROR] %s: %s", symbol, e)
                return symbol, None

        results_map = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_validate_one, t[0].symbol, t[1]): t[0].symbol for t in tasks}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    s, result = future.result()
                    if result is not None:
                        results_map[s] = result
                except Exception as e:
                    logger.error("   [ERROR] Thread for %s failed: %s", sym, e)

        # Write results to DB sequentially
        for sig, _, discovery_output in tasks:
            confirmation = results_map.get(sig.symbol)
            if not confirmation:
                continue

            val = confirmation.get("validation", {})
            dec = confirmation.get("decision", {})
            status = val.get("status", "WEAKENED")
            should_pass = dec.get("should_pass_to_agent_3", False)

            # Map new status to DB confirmation_status
            if status == "CONFIRMED" and should_pass:
                sig.confirmation_status = "confirmed"
                sig.status = "confirmed"
                summary["confirmed"] += 1
            elif status == "INVALIDATED":
                sig.confirmation_status = "invalidated"
                sig.status = "invalidated"
                summary["invalidated"] += 1
            else:
                sig.confirmation_status = "invalidated"  # WEAKENED = not passed
                sig.status = "invalidated"
                summary["weakened"] += 1

            sig.confirmed_at = _now_ms()
            sig.confirmation_data = confirmation

            # Confidence: use Agent 1's confidence mapped to int
            cv = discovery_output.get("combined_view", {})
            conf_map = {"LOW": 20, "MEDIUM": 55, "HIGH": 80}
            sig.confidence = conf_map.get(cv.get("final_confidence", ""), 20)

            # --- LOGGING ---
            logger.info("=" * 40)
            logger.info("[AGENT 2 OUTPUT] %s", sig.symbol)
            logger.info("   status: %s", status)
            logger.info("   alignment: %s", confirmation.get("thesis_check", {}).get("alignment", "?"))
            logger.info("   behavior: %s", confirmation.get("market_behavior", {}).get("price_behavior", "?"))
            logger.info("   should_pass: %s", should_pass)
            logger.info("   instruction: %s", dec.get("agent_3_instruction", "?"))
            logger.info("   reason: %s", val.get("reason", ""))
            
            ts = confirmation.get("trade_suitability", {})
            logger.info("   [SUITABILITY] mode=%s | holding_logic=%s", 
                        ts.get("mode", "?"), ts.get("holding_logic", "?"))
            
            inds = confirmation.get("indicators_to_check", {})
            logger.info("   [INDICATORS] trend=%s | momentum=%s | volatility=%s | volume=%s | patterns=%s | sr=%s",
                        len(inds.get("trend", [])), len(inds.get("momentum", [])), 
                        len(inds.get("volatility", [])), len(inds.get("volume", [])),
                        len(inds.get("pattern_recognition", [])), len(inds.get("support_resistance", [])))
            logger.info("=" * 40)

            results.append({
                "symbol": sig.symbol,
                "status": status,
                "alignment": confirmation.get("thesis_check", {}).get("alignment", "?"),
                "should_pass": should_pass,
                "reason": val.get("reason", ""),
            })
            db.commit()

            # Trigger Agent 2.5 immediately if CONFIRMED and should_pass
            if status == "CONFIRMED" and should_pass and dec.get("agent_3_instruction") != "DO_NOT_PROCEED":
                logger.info("[TRIGGER] Agent 2 confirmed %s → Agent 2.5 starting", sig.symbol)
                try:
                    from agent.technical_analysis_agent import run_technical_analysis
                    run_technical_analysis(db=db, signal_ids=[sig.id])
                except Exception as e:
                    logger.error("[ERROR] Triggering Agent 2.5 failed for %s: %s", sig.symbol, e)

        duration = _now_ms() - started_at

        logger.info("=" * 60)
        logger.info("[DONE] Agent 2 Market Reality Validator Complete")
        logger.info("   Confirmed: %d | Weakened: %d | Invalidated: %d | Skipped: %d",
                     summary["confirmed"], summary["weakened"],
                     summary["invalidated"], summary["skipped"])
        logger.info("   Duration: %dms", duration)
        logger.info("=" * 60)

        return {
            "run_id": run_id,
            "market_date": market_date,
            "confirmed_at": _now_ms(),
            "total_checked": len(tradable_signals),
            "summary": summary,
            "results": results,
            "agent25_execution": None,
            "duration_ms": duration,
        }

    finally:
        if own_session:
            db.close()
