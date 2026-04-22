"""Signal Generator — main orchestrator for the Agent 1 (Discovery) pipeline.

Pipeline: Fetch News → Group by Symbol → Fetch Company Context → Gemini Discovery → Save to DB.

Agent 1 OUTPUT is a pure NEWS UNDERSTANDING (not a trade signal, not a watchlist decision).
It answers: "What actually happened, and does it meaningfully matter?"

Agent 2 (Market Open Confirmation) receives this output at 9:20 AM and decides whether
the thesis still holds after the actual market open.

Key mapping decisions:
  - signal_type is set from final_verdict (IMPORTANT_EVENT → WATCH, others → NO_TRADE)
  - trade_mode is always "NONE" at this stage (Agent 2 sets trade direction)
  - All raw Discovery output is stored in the `reasoning` JSON column verbatim
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
    Execute the complete Agent 1 (Discovery) pipeline.

    Returns a summary dict with all news-understanding assessments.
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
        print(f"[AGENT 1] DISCOVERY -- Run ID: {run_id}")
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
            print("\n[STEP 1] Using existing news in DB (no endpoint configured)")

        # -- Step 2: Get recent news grouped by symbol --------------------
        print("\n[STEP 2] Collecting recent news from DB (smart calendar window)...")
        grouped_news = fetch_recent_news(db)
        symbols = list(grouped_news.keys())
        print(f"   [OK] Found {sum(len(v) for v in grouped_news.values())} articles across {len(symbols)} symbols")

        if not symbols:
            print("\n[WARN] No actionable news found. Agent run complete with 0 assessments.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "generated_at": _now_ms(),
                "total_analyzed": 0,
                "signals_summary": _empty_summary(),
                "signals": [],
                "duration_ms": _now_ms() - started_at,
            }

        # -- Step 3: Fetch market context (used only for company_name) ----
        print(f"\n[STEP 3] Fetching market context for {len(symbols)} symbols...")
        stock_data_map = fetch_stock_data_for_symbols(symbols)
        print(f"   [OK] Got context for {len(stock_data_map)} symbols")

        # -- Step 4: Analyze each symbol ----------------------------------
        print(f"\n[STEP 4] Running Gemini Discovery analysis...")
        signals = []
        summary = _empty_summary()

        for sym in symbols:
            articles = grouped_news.get(sym, [])
            stock = stock_data_map.get(sym)

            if not stock:
                print(f"   [SKIP] {sym}: No market context, skipping")
                continue

            print(f"\n   -- Analyzing {sym} ({len(articles)} articles) --")
            print(f"      [GEMINI] Running discovery analysis...")
            gemini_result = analyze_stock(sym, articles, stock, market_date)
            print(f"      [OK] Source: {gemini_result.get('_source', 'unknown')}")

            # Extract Discovery output fields (new schema)
            final_verdict = gemini_result.get("final_verdict", "NOISE")
            event_strength = gemini_result.get("event_strength", "WEAK")
            freshness = gemini_result.get("freshness", "OLD")
            directness = gemini_result.get("directness", "NONE")
            is_material = gemini_result.get("is_material", False)
            confidence = gemini_result.get("confidence", 0)

            print(f"      Verdict: {final_verdict} | Strength: {event_strength} | "
                  f"Freshness: {freshness} | Material: {is_material}")
            print(f"      Confidence: {confidence}")

            # Map final_verdict to a DB-compatible signal_type
            # IMPORTANT_EVENT → WATCH (Agent 2 will decide whether to trade)
            # Everything else → NO_TRADE (not interesting enough to confirm)
            signal_type = _verdict_to_signal_type(final_verdict)

            # trade_mode is unknown at Discovery stage — Agent 2 sets direction
            trade_mode = "NONE"

            # Build signal record
            signal_id = f"sig-{sym}-{market_date}-{uuid.uuid4().hex[:6]}"

            signal_record = {
                "id": signal_id,
                "symbol": sym,
                "signal_type": signal_type,
                "trade_mode": trade_mode,
                "entry_price": None,   # Discovery does NOT set trade levels
                "stop_loss": None,
                "target_price": None,
                "risk_reward": None,
                "confidence": int(confidence),
                "reasoning": gemini_result,   # Full Discovery output is the source of truth
                "news_article_ids": [a["id"] for a in articles],
                "stock_snapshot": stock,
                "generated_at": _now_ms(),
                "market_date": market_date,
                "gemini_source": gemini_result.get("_source", "unknown"),
            }

            signals.append(signal_record)

            # Track summary
            _update_summary(summary, final_verdict, event_strength)

            # Save to DB — replace any existing record for this symbol+date
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
                confidence=int(confidence),
                reasoning=gemini_result,
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
        print(f"[DONE] Agent 1 (Discovery) complete!")
        print(f"   Analyzed: {len(signals)} symbols")
        print(f"   WATCH (Important): {summary['watch']} | NOISE/MINOR: {summary['ignore']} | Stale/Repeated: {summary['stale']}")
        print(f"   Duration: {duration}ms")
        print(f"{'='*60}\n")

        # Sort by confidence descending (integer 0-100)
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


# ── Helper Functions ─────────────────────────────────────────────────────────

def _empty_summary() -> dict:
    """Return an empty summary counter aligned with the Discovery schema."""
    return {
        "watch": 0,         # IMPORTANT_EVENT (passed to Agent 2)
        "ignore": 0,        # MINOR_EVENT / NOISE (skipped)
        "stale": 0,         # NOISE with OLD/REPEATED freshness
        # Strength counters
        "strong": 0,
        "moderate": 0,
        "weak": 0,
    }


def _update_summary(summary: dict, final_verdict: str, event_strength: str):
    """Update summary counters based on Discovery output."""
    v = final_verdict.upper()
    if "IMPORTANT" in v:
        summary["watch"] += 1
    elif "MODERATE" in v:
        summary["ignore"] += 1
    elif "MINOR" in v:
        summary["ignore"] += 1
    else:
        # NOISE
        summary["stale"] += 1

    s = event_strength.upper()
    if s == "STRONG":
        summary["strong"] += 1
    elif s == "MODERATE":
        summary["moderate"] += 1
    else:
        summary["weak"] += 1


def _verdict_to_signal_type(final_verdict: str) -> str:
    """
    Map Discovery final_verdict to a DB signal_type.

    IMPORTANT_EVENT → WATCH  (Agent 2 will confirm or reject)
    Anything else   → NO_TRADE (not worth confirming)
    """
    v = final_verdict.upper()
    if "IMPORTANT" in v:
        return "WATCH"
    return "NO_TRADE"
