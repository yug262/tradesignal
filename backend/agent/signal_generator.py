"""Signal Generator -- main orchestrator that runs the full analysis pipeline.

Pipeline: Fetch News -> Fetch Prices -> Score -> Gemini Analysis -> Generate Signals -> Save to DB.
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
    Execute the complete agent pipeline.
    
    Returns a summary dict with all generated signals.
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
        print(f"[AGENT] TRADING AGENT -- Run ID: {run_id}")
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
        # Uses smart market calendar — automatically handles weekends & holidays
        print("\n[STEP 2] Collecting recent news from DB (smart calendar window)...")
        grouped_news = fetch_recent_news(db)  # No hardcoded hours_back!
        symbols = list(grouped_news.keys())
        print(f"   [OK] Found {sum(len(v) for v in grouped_news.values())} articles across {len(symbols)} symbols")

        if not symbols:
            print("\n[WARN] No actionable news found. Agent run complete with 0 signals.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "generated_at": _now_ms(),
                "total_analyzed": 0,
                "signals_summary": {"buy": 0, "sell": 0, "hold": 0, "no_trade": 0},
                "signals": [],
                "duration_ms": _now_ms() - started_at,
            }

        # -- Step 3: Fetch stock prices -----------------------------------
        print(f"\n[STEP 3] Fetching stock prices for {len(symbols)} symbols...")
        stock_data_map = fetch_stock_data_for_symbols(symbols)
        print(f"   [OK] Got price data for {len(stock_data_map)} symbols")

        # -- Step 4: Analyze each symbol ----------------------------------
        print(f"\n[STEP 4] Running analysis pipeline...")
        signals = []
        summary = {"buy": 0, "sell": 0, "hold": 0, "no_trade": 0}

        for sym in symbols:
            articles = grouped_news.get(sym, [])
            stock = stock_data_map.get(sym)

            if not stock:
                print(f"   [SKIP] {sym}: No price data, skipping")
                continue

            print(f"\n   -- Analyzing {sym} ({len(articles)} articles) --")

            # 4a. Gemini deep analysis
            print(f"      [GEMINI] Calling Gemini for deep logic analysis on {sym}...")
            gemini_result = analyze_stock(sym, articles, stock, market_date)
            print(f"      [OK] Gemini source: {gemini_result.get('_source', 'unknown')}")

            # 4b. Extract Gemini output
            tradable = gemini_result.get("tradable", False)
            final_signal = gemini_result.get("signal", "HOLD")
            if not tradable:
                final_signal = "NO_TRADE"
                
            final_mode = gemini_result.get("trade_mode", "INTRADAY")
            final_entry = gemini_result.get("entry_price")
            final_sl = gemini_result.get("stop_loss")
            final_target = gemini_result.get("target_price")
            confidence = gemini_result.get("confidence", 0.0)

            print(f"      Signal: {final_signal} | Mode: {final_mode} | Tradable: {tradable} | Confidence: {confidence}")

            # 4c. Calculate Risk/Reward
            final_rr = 0.0
            if final_entry and final_sl and final_target and final_entry != final_sl:
                risk = abs(final_entry - final_sl)
                if risk > 0:
                    final_rr = round(abs(final_target - final_entry) / risk, 2)

            # 4d. Build signal record
            signal_id = f"sig-{sym}-{market_date}-{uuid.uuid4().hex[:6]}"

            signal_record = {
                "id": signal_id,
                "symbol": sym,
                "signal_type": final_signal,
                "trade_mode": final_mode,
                "entry_price": final_entry,
                "stop_loss": final_sl,
                "target_price": final_target,
                "risk_reward": final_rr,
                "confidence": confidence,
                "reasoning": gemini_result.get("reasoning", {}),
                "news_article_ids": [a["id"] for a in articles],
                "stock_snapshot": stock,
                "generated_at": _now_ms(),
                "market_date": market_date,
                "gemini_source": gemini_result.get("_source", "unknown"),
            }

            signals.append(signal_record)

            # Track summary
            sig_key = final_signal.lower()
            if sig_key in summary:
                summary[sig_key] += 1
            else:
                summary["no_trade"] += 1

            # 4e. Save to DB
            # Remove any existing signals for this symbol on this market date to avoid duplicates
            db.query(db_models.DBTradeSignal).filter(
                db_models.DBTradeSignal.symbol == sym,
                db_models.DBTradeSignal.market_date == market_date
            ).delete(synchronize_session=False)

            db_signal = db_models.DBTradeSignal(
                id=signal_id,
                symbol=sym,
                signal_type=final_signal,
                trade_mode=final_mode,
                entry_price=final_entry,
                stop_loss=final_sl,
                target_price=final_target,
                risk_reward=final_rr,
                confidence=confidence,
                reasoning=gemini_result.get("reasoning", {}),
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
        print(f"[DONE] Agent run complete!")
        print(f"   Analyzed: {len(signals)} symbols")
        print(f"   BUY: {summary['buy']} | SELL: {summary['sell']} | HOLD: {summary['hold']} | NO_TRADE: {summary['no_trade']}")
        print(f"   Duration: {duration}ms")
        print(f"{'='*60}\n")

        # Sort signals by confidence descending
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
