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
        # SORT symbols alphabetically to prevent database deadlocks with other agents
        symbols = sorted(list(grouped_news.keys()))
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

        # -- Step 4: Analyze each symbol (CONCURRENT — up to 5 in parallel) --
        print(f"\n[STEP 4] Running Gemini Discovery analysis ({len(symbols)} symbols, concurrent)...")
        signals = []
        summary = _empty_summary()

        # ── Run Gemini calls concurrently ──────────────────────────────────
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _analyze_one(sym: str) -> tuple[str, dict | None, list]:
            """Run one Gemini analysis in a thread. Returns (symbol, result, article_ids)."""
            articles = grouped_news.get(sym, [])
            stock = stock_data_map.get(sym)
            if not stock:
                print(f"   [SKIP] {sym}: No market context, skipping")
                return sym, None, []
            print(f"   -- Analyzing {sym} ({len(articles)} articles) --")
            try:
                result = analyze_stock(sym, articles, stock, market_date)
                print(f"      [OK] {sym}: {result.get('final_verdict', '?')} "
                      f"(confidence={result.get('confidence', 0)}, source={result.get('_source', '?')})")
                return sym, result, articles
            except Exception as e:
                print(f"      [ERROR] {sym}: {e}")
                return sym, None, articles

        # Use up to 5 threads (Gemini free tier allows ~5 concurrent calls)
        results_map = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_analyze_one, sym): sym for sym in symbols}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    s, result, articles = future.result()
                    if result is not None:
                        results_map[s] = (result, articles)
                except Exception as e:
                    print(f"   [ERROR] Thread for {sym} failed: {e}")

        print(f"\n   [CONCURRENT] Got {len(results_map)}/{len(symbols)} results")

        # ── Write results to DB sequentially (avoids deadlocks) ────────────
        for sym in symbols:
            if sym not in results_map:
                continue

            gemini_result, articles = results_map[sym]

            # Extract Discovery output fields
            final_verdict = gemini_result.get("final_verdict", "NOISE")
            event_strength = gemini_result.get("event_strength", "WEAK")
            confidence = gemini_result.get("confidence", 0)

            signal_type = _verdict_to_signal_type(final_verdict)
            trade_mode = "NONE"

            signal_id = f"sig-{sym}-{market_date}-{uuid.uuid4().hex[:6]}"
            signal_record = {
                "id": signal_id,
                "symbol": sym,
                "signal_type": signal_type,
                "trade_mode": trade_mode,
                "entry_price": None,
                "stop_loss": None,
                "target_price": None,
                "risk_reward": None,
                "confidence": int(confidence),
                "reasoning": gemini_result,
                "news_article_ids": [a["id"] for a in articles],
                "stock_snapshot": stock_data_map.get(sym),
                "generated_at": _now_ms(),
                "market_date": market_date,
                "gemini_source": gemini_result.get("_source", "unknown"),
            }
            signals.append(signal_record)
            _update_summary(summary, final_verdict, event_strength)

            # Save to DB — upsert pattern
            existing = db.query(db_models.DBTradeSignal).filter(
                db_models.DBTradeSignal.symbol == sym,
                db_models.DBTradeSignal.market_date == market_date
            ).first()

            if existing:
                existing.signal_type = signal_type
                existing.confidence = int(confidence)
                existing.reasoning = gemini_result
                existing.news_article_ids = [a["id"] for a in articles]
                existing.stock_snapshot = stock_data_map.get(sym)
                existing.generated_at = _now_ms()
                # Reset pipeline statuses for new analysis
                existing.status = "pending_confirmation"
                existing.confirmation_status = "pending"
                existing.execution_status = "pending"
                existing.confirmed_at = None
                existing.executed_at = None
                print(f"      [DB] Updated existing signal for {sym}")
            else:
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
                    stock_snapshot=stock_data_map.get(sym),
                    generated_at=_now_ms(),
                    market_date=market_date,
                    status="pending_confirmation",
                    confirmation_status="pending",
                )
                db.add(db_signal)
                print(f"      [DB] Created new signal for {sym}")

            # Commit after each symbol to minimize lock contention and avoid deadlocks
            db.commit()

        duration = _now_ms() - started_at
        print(f"\n{'='*60}")
        print(f"[DONE] Agent 1 (Discovery) complete!")
        print(f"   Analyzed: {len(signals)} symbols")
        print(f"   WATCH (Important): {summary['watch']} | NOISE/MINOR: {summary['ignore']} | Stale/Repeated: {summary['stale']}")
        print(f"   Duration: {duration}ms")
        print(f"{'='*60}\n")

        # Sort: WATCH signals first, then by confidence descending
        signals.sort(key=lambda s: (0 if s.get("signal_type") == "WATCH" else 1, -s.get("confidence", 0)))

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
