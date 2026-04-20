"""Execution Agent — Phase 3 of the trading pipeline.

Runs after Agent 2 (Confirmation Agent).
Takes validated trades (confirmation_status = 'confirmed') and generates
a precise execution plan using LIVE market data.
"""

import time
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from agent.data_collector import fetch_stock_data_for_symbols
from agent.gemini_executor import plan_execution

IST = timezone(timedelta(hours=5, minutes=30))


def _market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def run_execution_planner(db: Session = None) -> dict:
    """
    Execute the Execution Planner pipeline (Agent 3).

    Fetches all confirmed signals for today, gets live market data,
    and uses Gemini to plan the exact execution levels.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        market_date = _market_date_str()
        run_id = f"exec-{market_date}-{uuid.uuid4().hex[:8]}"
        started_at = _now_ms()

        print(f"\n{'='*60}")
        print(f"[AGENT 3] EXECUTION PLANNER -- Run ID: {run_id}")
        print(f"   Market Date: {market_date}")
        print(f"   Time: {datetime.now(IST).strftime('%H:%M:%S IST')}")
        print(f"{'='*60}")

        # -- Step 1: Get today's confirmed but un-executed signals --
        pending_signals = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.market_date == market_date)
            .filter(db_models.DBTradeSignal.confirmation_status == "confirmed")
            .filter(db_models.DBTradeSignal.execution_status == "pending")
            .all()
        )

        if not pending_signals:
            print("\n[WARN] No confirmed signals pending execution found for today.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "executed_at": _now_ms(),
                "total_checked": 0,
                "summary": {"planned": 0, "avoided": 0, "skipped": 0},
                "results": [],
                "duration_ms": 0,
            }

        # -- Step 2: Fetch LIVE stock data --
        symbols = list(set(s.symbol for s in pending_signals))
        live_data_map = fetch_stock_data_for_symbols(symbols)

        # -- Step 3: Process each signal --
        results = []
        summary = {"planned": 0, "avoided": 0, "skipped": 0}

        for sig in pending_signals:
            live_data = live_data_map.get(sig.symbol)
            if not live_data:
                sig.execution_status = "skipped"
                sig.executed_at = _now_ms()
                sig.execution_data = {
                    "action": "AVOID",
                    "execution_decision": "NO TRADE",
                    "why_now_or_why_wait": "No live data available — cannot plan execution.",
                    "_source": "no_data_skip"
                }
                summary["skipped"] += 1
                continue

            print(f"\n   -- Planning Execution for {sig.symbol} --")

            # 1. Agent 2 View
            agent2_view = sig.confirmation_data if isinstance(sig.confirmation_data, dict) else {}
            
            # Map confirmation data to Agent 2 expected input structure
            agent2_input_view = {
                "decision": agent2_view.get("decision", "TRADE"),
                "trade_mode": agent2_view.get("trade_mode", sig.trade_mode),
                "direction": agent2_view.get("direction", "NEUTRAL"),
                "remaining_impact": agent2_view.get("remaining_impact", "UNCLEAR"),
                "priced_in_status": agent2_view.get("priced_in_status", "UNCLEAR"),
                "priority": agent2_view.get("priority", "LOW"),
                "confidence": agent2_view.get("confidence", 0),
                "why_tradable_or_not": agent2_view.get("why_tradable_or_not", ""),
                "key_confirmations": agent2_view.get("key_confirmations", []),
                "warning_flags": agent2_view.get("warning_flags", []),
                "invalid_if": agent2_view.get("invalid_if", []),
                "final_summary": agent2_view.get("final_summary", "")
            }

            # 2. Live Execution Context
            snapshot = sig.stock_snapshot if isinstance(sig.stock_snapshot, dict) else {}
            prev_close = snapshot.get("last_close") or live_data.get("last_close") or 0
            open_price = live_data.get("today_open", 0)
            high_price = live_data.get("today_high", 0)
            low_price = live_data.get("today_low", 0)
            ltp = live_data.get("ltp", open_price)
            vwap = live_data.get("vwap", 0)
            current_vol = live_data.get("current_volume", 0)
            
            gap_pct = round(((open_price - prev_close) / prev_close * 100), 2) if prev_close else 0
            change_pct = round(live_data.get("current_change_pct") or 0, 2)
            
            # Distance calculations
            dist_from_vwap_pct = round(((ltp - vwap) / vwap * 100), 2) if vwap else 0
            dist_from_high_pct = round(((high_price - ltp) / ltp * 100), 2) if high_price and ltp else 0
            dist_from_low_pct = round(((ltp - low_price) / low_price * 100), 2) if low_price and ltp else 0
            price_move_pct = round(((ltp - prev_close) / prev_close * 100), 2) if prev_close else 0

            # Move Quality
            move_quality = "WEAK"
            if open_price and prev_close:
                if gap_pct > 0.3 and ltp < open_price * 0.995:
                    move_quality = "REVERSING"
                elif gap_pct < -0.3 and ltp > open_price * 1.005:
                    move_quality = "REVERSING"
                elif (gap_pct > 0.5 and change_pct < -0.3) or (gap_pct < -0.5 and change_pct > 0.3):
                    move_quality = "FADING"
                elif (gap_pct > 0 and change_pct > 0.2) or (gap_pct < 0 and change_pct < -0.2):
                    move_quality = "STRONG"
                elif abs(change_pct) <= 0.5:
                    move_quality = "HOLDING"

            # Intraday Structure approximation
            intraday_structure = "UNCLEAR"
            if ltp >= high_price * 0.998 and change_pct > 0.5:
                intraday_structure = "BREAKOUT_HIGH"
            elif ltp <= low_price * 1.002 and change_pct < -0.5:
                intraday_structure = "BREAKDOWN_LOW"
            elif move_quality == "STRONG" and abs(change_pct) > 1.0:
                intraday_structure = "TRENDING"
            elif move_quality == "FADING":
                intraday_structure = "PULLBACK"
            elif move_quality == "REVERSING":
                intraday_structure = "REVERSAL"
            elif move_quality == "HOLDING":
                intraday_structure = "RANGE"

            # Volume Context
            avg_vol_20d = snapshot.get("avg_volume_20d")
            vol_vs_avg = round(current_vol / avg_vol_20d, 2) if avg_vol_20d and avg_vol_20d > 0 else 0

            live_execution_context = {
                "previous_close": prev_close,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "ltp": ltp,
                "vwap": vwap,
                "above_vwap": ltp > vwap if vwap else False,
                "distance_from_vwap_percent": dist_from_vwap_pct,
                "gap_percent": gap_pct,
                "change_percent": change_pct,
                "price_move_percent": price_move_pct,
                "volume": current_vol,
                "volume_vs_avg_20d": vol_vs_avg,
                "opening_move_quality": move_quality,
                "intraday_structure": intraday_structure,
                "distance_from_day_high_percent": dist_from_high_pct,
                "distance_from_day_low_percent": dist_from_low_pct
            }

            # 3. Build Agent 3 Input
            agent3_input = {
                "symbol": sig.symbol,
                "company_name": sig.symbol,
                "agent2_view": agent2_input_view,
                "live_execution_context": live_execution_context
            }

            # 4. Call Agent 3 (Gemini Executor)
            print(f"      [GEMINI] Agent 3 planning {sig.symbol}...")
            execution_plan = plan_execution(agent3_input)

            action = execution_plan.get("action", "AVOID").upper()
            exec_dec = execution_plan.get("execution_decision", "NO TRADE").upper()
            print(f"      [RESULT] {action} | {exec_dec} | Confidence: {execution_plan.get('confidence')}")

            # Update DB
            if exec_dec == "NO TRADE":
                sig.execution_status = "skipped"
                sig.status = "invalidated"
            elif exec_dec == "AVOID CHASE":
                sig.execution_status = "skipped"
                sig.status = "confirmed"  # Edge is valid, just skipping execution for now
            else:
                sig.execution_status = "planned"
                sig.status = "planned"
            
            sig.executed_at = _now_ms()
            sig.execution_data = execution_plan
            
            # Map top-level columns if planning
            if sig.execution_status == "planned":
                ep = execution_plan.get("entry_plan", {})
                sl = execution_plan.get("stop_loss", {})
                tg = execution_plan.get("target", {})
                
                sig.signal_type = "BUY" if action == "BUY" else "SELL" if action == "SELL" else "WATCH"
                sig.entry_price = ep.get("entry_price")
                sig.stop_loss = sl.get("price")
                sig.target_price = tg.get("price")
                summary["planned"] += 1
            else:
                summary["avoided"] += 1

            results.append({
                "symbol": sig.symbol,
                "action": action,
                "execution_decision": exec_dec,
                "confidence": execution_plan.get("confidence", 0),
                "why": execution_plan.get("why_now_or_why_wait", "")
            })

        db.commit()
        duration = _now_ms() - started_at
        
        print(f"\n{'='*60}")
        print(f"[DONE] Agent 3 Pipeline Complete")
        print(f"   Duration: {duration}ms")
        print(f"{'='*60}\n")

        return {
            "run_id": run_id,
            "market_date": market_date,
            "executed_at": _now_ms(),
            "total_checked": len(pending_signals),
            "summary": summary,
            "results": results,
            "duration_ms": duration,
        }

    finally:
        if own_session:
            db.close()
