"""Signal Generator -- main orchestrator that runs the full Agent 1 pipeline.

Pipeline: Fetch News -> Group by Symbol -> Fetch Rich Market Context -> Gemini Analysis -> Save to DB.

Agent 1 OUTPUT is a WATCHLIST ASSESSMENT (not a trade signal).
It tells you WHAT to watch, WHY, and WHAT to expect at market open.
Agent 2 later confirms with live data and generates actual trade parameters.
"""

import time
import uuid
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from store import _get_store

from agent.data_collector import fetch_recent_news, trigger_news_fetch, fetch_stock_data_for_symbols
from agent.gemini_analyzer import analyze_stock
from agent.market_calendar import get_news_fetch_window, is_trading_day, IST as MARKET_IST


IST = timezone(timedelta(hours=5, minutes=30))


def _market_date_str() -> str:
    """Get today's date in IST as YYYY-MM-DD."""
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def run_full_analysis(db: Session = None) -> dict:
    """
    Execute the complete Agent 1 pre-market intelligence pipeline.

    Returns a summary dict with all watchlist assessments.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        market_date = _market_date_str()
        run_id = f"run-{market_date}-{uuid.uuid4().hex[:8]}"
        started_at = _now_ms()

        # -- Calculate market window FIRST --------------------------------
        from_dt, to_dt, window_info = get_news_fetch_window()

        print(f"\n{'='*60}")
        print(f"[AGENT 1] PRE-MARKET INTELLIGENCE -- Run ID: {run_id}")
        print(f"   Market Date: {market_date}")
        print(f"   Started: {datetime.now(IST).strftime('%H:%M:%S IST')}")
        print(f"   Today: {window_info['today_weekday']}")
        print(f"   Last Trading Day: {window_info['last_trading_day']} ({window_info['last_trading_day_weekday']})")
        print(f"   News Window: {window_info['from_time']} -> {window_info['to_time']}")
        print(f"   Window Size: {window_info['window_hours']} hours")
        if window_info['non_trading_days_between']:
            print(f"   Non-trading days skipped: {', '.join(window_info['non_trading_days_between'])}")
        print(f"{'='*60}")

        # -- Step 1: Optionally fetch fresh news --------------------------
        config = _get_store().config
        if config.news_endpoint_url:
            print("\n[STEP 1] Fetching fresh news from endpoint...")
            new_count = trigger_news_fetch(config.news_endpoint_url, db)
            print(f"   [OK] Saved {new_count} new articles")
        else:
            print("\n[STEP 1] Using existing news in DB (no endpoint)")

        # -- Step 2: Get recent news grouped by symbol --------------------
        print("\n[STEP 2] Collecting recent news from DB (smart calendar window)...")
        grouped_news = fetch_recent_news(db)
        symbols = list(grouped_news.keys())
        print(f"   [OK] Found {sum(len(v) for v in grouped_news.values())} articles across {len(symbols)} symbols")

        if not symbols:
            print("\n[WARN] No actionable news found. Agent run complete with 0 signals.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "generated_at": _now_ms(),
                "total_analyzed": 0,
                "signals_summary": _empty_summary(),
                "signals": [],
                "duration_ms": _now_ms() - started_at,
            }

        # -- Step 3: Fetch rich market context ----------------------------
        print(f"\n[STEP 3] Fetching rich market context for {len(symbols)} symbols...")
        stock_data_map = fetch_stock_data_for_symbols(symbols)
        print(f"   [OK] Got data for {len(stock_data_map)} symbols")

        # -- Step 4: Analyze each symbol ----------------------------------
        print(f"\n[STEP 4] Running Gemini pre-market intelligence...")
        signals = []
        summary = _empty_summary()

        for sym in symbols:
            articles = grouped_news.get(sym, [])
            stock = stock_data_map.get(sym)

            if not stock:
                print(f"   [SKIP] {sym}: No price data, skipping")
                continue

            print(f"\n   -- Analyzing {sym} ({len(articles)} articles) --")
            print(f"      [GEMINI] Running deep analysis...")
            gemini_result = analyze_stock(sym, articles, stock, market_date)
            print(f"      [OK] Source: {gemini_result.get('_source', 'unknown')}")

            # Extract Agent 1 output fields
            decision = gemini_result.get("decision", "STALE NO EDGE")
            trade_pref = gemini_result.get("trade_preference", "NONE")
            direction = gemini_result.get("direction_bias", "NEUTRAL")
            gap_exp = gemini_result.get("gap_expectation", "UNCLEAR")
            priority = gemini_result.get("priority", "LOW")
            confidence = gemini_result.get("confidence", 0.0)
            event_strength = gemini_result.get("event_strength", "WEAK")

            print(f"      Decision: {decision} | Direction: {direction} | Gap: {gap_exp}")
            print(f"      Priority: {priority} | Confidence: {confidence} | Strength: {event_strength}")

            # Map to DB-compatible signal_type
            signal_type = _decision_to_signal_type(decision, direction)
            trade_mode = _trade_pref_to_mode(trade_pref)

            # Build signal record
            signal_id = f"sig-{sym}-{market_date}-{uuid.uuid4().hex[:6]}"

            signal_record = {
                "id": signal_id,
                "symbol": sym,
                "signal_type": signal_type,
                "trade_mode": trade_mode,
                "entry_price": None,  # Agent 1 does NOT set trade levels
                "stop_loss": None,
                "target_price": None,
                "risk_reward": None,
                "confidence": confidence,
                "reasoning": {
                    "decision": decision,
                    "trade_preference": trade_pref,
                    "direction_bias": direction,
                    "gap_expectation": gap_exp,
                    "priority": priority,
                    "event_summary": gemini_result.get("event_summary", ""),
                    "event_strength": event_strength,
                    "directness": gemini_result.get("directness", "NONE"),
                    "why_it_matters": gemini_result.get("why_it_matters", ""),
                    "key_drivers": gemini_result.get("key_drivers", []),
                    "risks": gemini_result.get("risks", []),
                    "open_expectation": gemini_result.get("open_expectation", ""),
                    "open_confirmation_needed": gemini_result.get("open_confirmation_needed", []),
                    "invalid_if": gemini_result.get("invalid_if", []),
                    "final_summary": gemini_result.get("final_summary", ""),
                },
                "news_article_ids": [a["id"] for a in articles],
                "stock_snapshot": stock,
                "generated_at": _now_ms(),
                "market_date": market_date,
                "gemini_source": gemini_result.get("_source", "unknown"),
            }

            signals.append(signal_record)

            # Track summary
            _update_summary(summary, decision, priority)

            # Save to DB
            db.query(db_models.DBTradeSignal).filter(
                db_models.DBTradeSignal.symbol == sym,
                db_models.DBTradeSignal.market_date == market_date
            ).delete(synchronize_session=False)

            db_signal = db_models.DBTradeSignal(
                id=signal_id,
                symbol=sym,
                signal_type=signal_type,
                trade_mode=trade_mode,
                entry_price=None,
                stop_loss=None,
                target_price=None,
                risk_reward=None,
                confidence=confidence,
                reasoning=signal_record["reasoning"],
                news_article_ids=[a["id"] for a in articles],
                stock_snapshot=stock,
                generated_at=_now_ms(),
                market_date=market_date,
                status="pending_confirmation",
                confirmation_status="pending",
            )
            db.add(db_signal)

        db.commit()

        duration = _now_ms() - started_at
        print(f"\n{'='*60}")
        print(f"[DONE] Agent 1 run complete!")
        print(f"   Analyzed: {len(signals)} symbols")
        print(f"   WATCH: {summary['watch']} | IGNORE: {summary['ignore']} | STALE: {summary['stale']}")
        print(f"   HIGH priority: {summary['high']} | MEDIUM: {summary['medium']} | LOW: {summary['low']}")
        print(f"   Duration: {duration}ms")
        print(f"{'='*60}\n")

        # Sort by confidence descending
        signals.sort(key=lambda s: s.get("confidence", 0), reverse=True)

        return {
            "run_id": run_id,
            "market_date": market_date,
            "generated_at": _now_ms(),
            "total_analyzed": len(signals),
            "signals_summary": summary,
            "signals": signals,
            "duration_ms": duration,
        }

    finally:
        if own_session:
            db.close()


# ── Helper Functions ────────────────────────────────────────────────────────

def _empty_summary() -> dict:
    """Return an empty summary counter."""
    return {
        "watch": 0,
        "ignore": 0,
        "stale": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        # Legacy compat
        "buy": 0,
        "sell": 0,
        "hold": 0,
        "no_trade": 0,
    }


def _update_summary(summary: dict, decision: str, priority: str):
    """Update summary counters based on Agent 1 output."""
    d = decision.upper()
    if "WATCH" in d:
        summary["watch"] += 1
    elif "IGNORE" in d:
        summary["ignore"] += 1
    elif "STALE" in d:
        summary["stale"] += 1
    else:
        summary["ignore"] += 1

    p = priority.upper()
    if p == "HIGH":
        summary["high"] += 1
    elif p == "MEDIUM":
        summary["medium"] += 1
    else:
        summary["low"] += 1


def _decision_to_signal_type(decision: str, direction: str) -> str:
    """Map Agent 1 decision + direction to a signal_type for DB compatibility."""
    d = decision.upper()
    if "WATCH" in d:
        if direction.upper() == "BULLISH":
            return "BUY"
        elif direction.upper() == "BEARISH":
            return "SELL"
        else:
            return "HOLD"
    elif "IGNORE" in d or "STALE" in d:
        return "NO_TRADE"
    return "NO_TRADE"


def _trade_pref_to_mode(trade_pref: str) -> str:
    """Map Agent 1 trade_preference to a trade_mode for DB compatibility."""
    p = trade_pref.upper()
    if p == "INTRADAY":
        return "INTRADAY"
    elif p == "DELIVERY":
        return "DELIVERY"
    elif p == "BOTH":
        return "INTRADAY"  # Default to intraday when both
    return "INTRADAY"
