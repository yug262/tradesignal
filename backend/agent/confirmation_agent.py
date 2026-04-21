"""Market Open Confirmation Agent — Phase 2 of the trading pipeline.

Runs at 9:20 AM IST (5 minutes after NSE market open).
Takes Agent 1's pre-market watchlist assessments (pending_confirmation)
and validates them against LIVE market-open data.

Pipeline:
  1. Query DB for today's signals where confirmation_status = 'pending'
  2. For each WATCH signal:
     a. Fetch LIVE stock data (current price, volume, open, high/low)
     b. Cross-reference opening behavior with Agent 1's expectations
     c. Send to Gemini for edge confirmation
     d. Update signal: confirmation_status, confirmation_data
  3. Return summary of all confirmations
"""

import time
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from agent.data_collector import fetch_stock_data_for_symbols
from agent.gemini_confirmer import confirm_signal


IST = timezone(timedelta(hours=5, minutes=30))


def _market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def run_market_open_confirmation(db: Session = None) -> dict:
    """
    Execute the Market Open Confirmation pipeline (Agent 2).

    Fetches all pending_confirmation signals for today, aggregates related news,
    maps Agent 1 views, gets live market data, and uses Gemini to confirm each one.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        market_date = _market_date_str()
        run_id = f"confirm-{market_date}-{uuid.uuid4().hex[:8]}"
        started_at = _now_ms()

        print(f"\n{'='*60}")
        print(f"[AGENT 2] MARKET OPEN CONFIRMATION -- Run ID: {run_id}")
        print(f"   Market Date: {market_date}")
        print(f"   Time: {datetime.now(IST).strftime('%H:%M:%S IST')}")
        print(f"{'='*60}")

        # -- Step 1: Get today's pending signals ----------------------------
        pending_signals = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.market_date == market_date)
            .filter(db_models.DBTradeSignal.confirmation_status == "pending")
            .all()
        )

        if not pending_signals:
            print("\n[WARN] No pending signals found for today.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "confirmed_at": _now_ms(),
                "total_checked": 0,
                "summary": {"confirmed": 0, "revised": 0, "invalidated": 0, "skipped": 0},
                "results": [],
                "duration_ms": 0,
            }

        # Filter tradable (WATCH only)
        tradable_signals = [s for s in pending_signals if s.signal_type == "WATCH"]
        skip_signals = [s for s in pending_signals if s.signal_type != "WATCH"]

        # Auto-skip non-tradable signals
        for sig in skip_signals:
            sig.confirmation_status = "invalidated"
            sig.confirmed_at = _now_ms()
            sig.confirmation_data = {
                "decision": "NO TRADE",
                "why_tradable_or_not": f"Auto-skipped: original signal was {sig.signal_type}",
                "_source": "auto_skip",
            }

        # -- Step 2: Fetch LIVE stock data ------------------
        symbols = list(set(s.symbol for s in tradable_signals))
        live_data_map = fetch_stock_data_for_symbols(symbols)

        # -- Step 3: Process each signal -----------------------
        results = []
        summary = {"confirmed": 0, "revised": 0, "invalidated": 0, "skipped": 0}

        for sig in tradable_signals:
            live_data = live_data_map.get(sig.symbol)
            if not live_data:
                sig.confirmation_status = "invalidated"
                sig.confirmed_at = _now_ms()
                sig.status = "invalidated"
                sig.confirmation_data = {"decision": "NO TRADE", "why_tradable_or_not": "No live data available — cannot validate edge.", "_source": "no_data_skip"}
                summary["skipped"] += 1
                continue

            print(f"\n   -- Analyzing {sig.symbol} --")

            # 1. Fetch News Bundle from DB
            article_ids = sig.news_article_ids if isinstance(sig.news_article_ids, list) else []
            articles = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.id.in_(article_ids)).all()
            
            news_bundle = []
            for a in articles:
                news_bundle.append({
                    "title": a.title,
                    "description": a.description or a.executive_summary or "",
                    "published_at": datetime.fromtimestamp(a.published_at / 1000, IST).isoformat() if a.published_at else ""
                })

            # 2. Bundle Meta
            times = [a.published_at for a in articles if a.published_at]
            distinct_event_count = len(set(a.impact_summary for a in articles if a.impact_summary))
            has_multiple_catalysts = distinct_event_count > 1
            bundle_meta = {
                "article_count": len(articles),
                "distinct_event_count": distinct_event_count,
                "has_multiple_catalysts": has_multiple_catalysts,
                "latest_article_time": datetime.fromtimestamp(max(times) / 1000, IST).isoformat() if times else "",
                "earliest_article_time": datetime.fromtimestamp(min(times) / 1000, IST).isoformat() if times else ""
            }

            # 3. Agent 1 View — use raw reasoning as source of truth
            reasoning = sig.reasoning if isinstance(sig.reasoning, dict) else {}

            agent1_view = {
                "decision": reasoning.get("decision", "STALE NO EDGE"),
                "trade_preference": reasoning.get("trade_preference", "NONE"),
                "direction_bias": reasoning.get("direction_bias", "NEUTRAL"),
                "gap_expectation": reasoning.get("gap_expectation", "UNCLEAR"),
                "priority": reasoning.get("priority", "LOW"),
                "confidence": reasoning.get("confidence", 0),
                "event_summary": reasoning.get("event_summary", ""),
                "event_strength": reasoning.get("event_strength", "WEAK"),
                "directness": reasoning.get("directness", "NONE"),
                "why_it_matters": reasoning.get("why_it_matters", ""),
                "key_drivers": reasoning.get("key_drivers", []),
                "risks": reasoning.get("risks", []),
                "open_expectation": reasoning.get("open_expectation", ""),
                "open_confirmation_needed": reasoning.get("open_confirmation_needed", []),
                "invalid_if": reasoning.get("invalid_if", []),
                "final_summary": reasoning.get("final_summary", ""),
            }

            # 4. Live Market Context
            snapshot = sig.stock_snapshot if isinstance(sig.stock_snapshot, dict) else {}
            prev_close = snapshot.get("last_close") or live_data.get("last_close") or 0
            open_price = live_data.get("today_open", 0)
            gap_pct = round(((open_price - prev_close) / prev_close * 100), 2) if prev_close else 0
            change_pct = round(live_data.get("current_change_pct") or 0, 2)
            ltp = live_data.get("ltp", open_price)

            # Opening move quality — mutually exclusive, priority ordered
            move_quality = "WEAK"
            if open_price and prev_close:
                # P1: REVERSING — price crossed back through open against gap
                if gap_pct > 0.3 and ltp < open_price * 0.995:
                    move_quality = "REVERSING"
                elif gap_pct < -0.3 and ltp > open_price * 1.005:
                    move_quality = "REVERSING"
                # P2: FADING — retracing toward previous close
                elif (gap_pct > 0.5 and change_pct < -0.3) or (gap_pct < -0.5 and change_pct > 0.3):
                    move_quality = "FADING"
                # P3: STRONG — continuing in gap direction
                elif (gap_pct > 0 and change_pct > 0.2) or (gap_pct < 0 and change_pct < -0.2):
                    move_quality = "STRONG"
                # P4: HOLDING — gap held, minimal drift
                elif abs(change_pct) <= 0.5:
                    move_quality = "HOLDING"

            live_market_context = {
                "previous_close": prev_close,
                "open": open_price,
                "high": live_data.get("today_high", 0),
                "low": live_data.get("today_low", 0),
                "ltp": ltp,
                "gap_percent": gap_pct,
                "change_percent": change_pct,
                "volume": live_data.get("current_volume", 0),
                "opening_move_quality": move_quality,
            }

            # Lightweight relative volume context (if baseline available)
            avg_vol_20d = snapshot.get("avg_volume_20d")
            current_vol = live_data.get("current_volume", 0)
            if avg_vol_20d and avg_vol_20d > 0 and current_vol:
                live_market_context["volume_vs_avg_20d"] = round(current_vol / avg_vol_20d, 2)

            # Normalized price move from previous close
            if prev_close and ltp:
                live_market_context["price_move_percent"] = round((ltp - prev_close) / prev_close * 100, 2)

            # 5. Build Agent 2 Input
            agent2_input = {
                "symbol": sig.symbol,
                "company_name": sig.symbol,
                "news_bundle": news_bundle,
                "bundle_meta": bundle_meta,
                "agent1_view": agent1_view,
                "live_market_context": live_market_context
            }

            # 6. Call Agent 2 (Gemini Confirmer)
            from agent.gemini_confirmer import confirm_signal_v2
            print(f"      [GEMINI] Agent 2 confirming {sig.symbol}...")
            confirmation = confirm_signal_v2(agent2_input, market_date)

            decision = confirmation.get("decision", "NO TRADE").upper()
            print(f"      [RESULT] {decision} | Confidence: {confirmation.get('confidence')}")

            # Update DB
            is_trade = (decision == "TRADE")
            sig.confirmation_status = "confirmed" if is_trade else "invalidated"
            sig.confirmed_at = _now_ms()
            sig.confirmation_data = confirmation
            sig.status = "confirmed" if is_trade else "invalidated"
            
            # Update confidence with Agent 2's integer scale output
            sig.confidence = confirmation.get("confidence", agent1_view.get("confidence", 0))

            summary["confirmed" if is_trade else "invalidated"] += 1
            results.append({
                "symbol": sig.symbol,
                "decision": decision,
                "confidence": sig.confidence,
                "why": confirmation.get("why_tradable_or_not", "")
            })

        db.commit()
        duration = _now_ms() - started_at
        
        print(f"\n{'='*60}")
        print(f"[DONE] Agent 2 Pipeline Complete")
        print(f"   Duration: {duration}ms")
        print(f"{'='*60}\n")

        return {
            "run_id": run_id,
            "market_date": market_date,
            "confirmed_at": _now_ms(),
            "total_checked": len(tradable_signals),
            "summary": summary,
            "results": results,
            "duration_ms": duration,
        }

    finally:
        if own_session:
            db.close()
