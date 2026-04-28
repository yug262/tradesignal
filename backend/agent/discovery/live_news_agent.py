"""Live Market News Agent - per-minute intraday news monitor.

Runs every minute during NSE market hours (09:15-15:30 IST, Mon-Fri).

Pipeline per run:
  1. Fetch news from external endpoint → get newly saved article IDs
  2. Also sweep DB for recent high-impact articles (fallback)
  3. Deduplicate (skip already-processed article IDs for today)
  4. For each affected symbol:
       a. Fetch current live LTP (Groww API)
       b. Fetch price at news publish time (1-min candle lookup)
       c. Fetch past news bundle for this symbol today (last 4h, from DB)
       d. Run Gemini Live Analyzer (combined Agent 1+2 fast prompt)
       e. Store result to DBLiveNewsEvent table
       f. If should_trade == True and confidence >= 65 → trigger Agent 2.5 → 3

Every article fetched from the endpoint is analyzed regardless of its
published_at timestamp. In-memory dedup prevents re-analysis within the
same trading day session.
"""

import time
import uuid
import json
import traceback
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from store import _get_store
from agent.data_collector import trigger_news_fetch
from .gemini_live_analyzer import analyze_live
from agent.market_calendar import is_trading_day, IST

# ── Constants ─────────────────────────────────────────────────────────────────

# Minimum impact score to qualify for live analysis
MIN_IMPACT_SCORE = 4.0

# How far back (seconds) to look for "new" news in each polling cycle
# 900s = 15 minutes (catch up with any delay from external API or publishing)
POLL_WINDOW_SECONDS = 900

# Minimum confidence to trigger Agent 3
AGENT3_TRIGGER_CONFIDENCE = 65

# In-memory dedup store: {article_id} processed today — reset at midnight
_processed_article_ids: set[str] = set()
_processed_date: str = ""  # YYYY-MM-DD


# ── Price Helpers ─────────────────────────────────────────────────────────────

def _get_live_stock_data(symbol: str) -> dict | None:
    """
    Fetch comprehensive live market data for a symbol using Groww's price API.
    
    Returns dict with:
      ltp, prev_close, open, high, low, volume, day_change_pct, day_change_amt,
      gap_pct, 52w_high, 52w_low
    or None on failure.
    """
    clean = symbol.replace(".NS", "").strip().upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        url = (
            f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/"
            f"exchange/NSE/segment/CASH/{clean}/latest"
        )
        with httpx.Client(timeout=8.0, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                print(f"  [LIVE DATA] HTTP {resp.status_code} for {symbol}")
                return None

            raw = resp.json()
            ltp = raw.get("ltp") or raw.get("close")
            if not ltp:
                return None

            prev_close = raw.get("close", 0)
            today_open = raw.get("open", 0)
            today_high = raw.get("high", 0)
            today_low = raw.get("low", 0)
            volume = raw.get("volume", 0)
            day_change_pct = raw.get("dayChangePerc", 0)
            day_change_amt = raw.get("dayChange", 0)
            year_high = raw.get("yearHighPrice")
            year_low = raw.get("yearLowPrice")

            gap_pct = 0.0
            if prev_close and today_open and prev_close > 0:
                gap_pct = round(((today_open - prev_close) / prev_close) * 100, 2)

            return {
                "ltp": float(ltp),
                "prev_close": float(prev_close) if prev_close else None,
                "open": float(today_open) if today_open else None,
                "high": float(today_high) if today_high else None,
                "low": float(today_low) if today_low else None,
                "volume": int(volume) if volume else 0,
                "day_change_pct": round(float(day_change_pct), 2) if day_change_pct else 0.0,
                "day_change_amt": round(float(day_change_amt), 2) if day_change_amt else 0.0,
                "gap_pct": gap_pct,
                "52w_high": float(year_high) if year_high else None,
                "52w_low": float(year_low) if year_low else None,
            }
    except Exception as e:
        print(f"  [LIVE DATA] Error fetching for {symbol}: {e}")
    return None


def _get_price_at_time(symbol: str, publish_ts_ms: int) -> float | None:
    """
    Attempt to find the stock price at the time a news article was published.

    Strategy:
      1. Fetch 1-minute candles for the last 2 hours
      2. Find the candle whose timestamp is closest to publish_ts_ms
      3. Return that candle's close price

    Returns None if the candle data is unavailable or no match found.
    """
    clean = symbol.replace(".NS", "").strip().upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        now_ms = int(time.time() * 1000)
        # Fetch 2 hours of 1-minute candles
        start_ms = now_ms - (2 * 3600 * 1000)

        url = (
            f"https://groww.in/v1/api/charting_service/v2/chart/"
            f"exchange/NSE/segment/CASH/{clean}"
            f"?intervalInMinutes=1&minimal=false"
            f"&startTimeInMillis={start_ms}&endTimeInMillis={now_ms}"
        )
        with httpx.Client(timeout=8.0, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None

            candles = resp.json().get("candles", [])
            if not candles:
                return None

        # Each candle: [timestamp_ms, open, high, low, close, volume]
        # Find the candle whose timestamp is closest to publish_ts_ms
        best_candle = None
        best_diff = float("inf")

        for c in candles:
            if not isinstance(c, (list, tuple)) or len(c) < 5:
                continue
            ts = c[0]
            diff = abs(ts - publish_ts_ms)
            if diff < best_diff:
                best_diff = diff
                best_candle = c

        # Only use if within 5 minutes of publish time
        if best_candle and best_diff <= 5 * 60 * 1000:
            return float(best_candle[4])  # close price

    except Exception as e:
        print(f"  [PUBLISH PRICE] Error for {symbol}: {e}")

    return None


# ── News Helpers ──────────────────────────────────────────────────────────────

def _fetch_new_news(db: Session) -> list[dict]:
    """
    Fetch news articles published in the last POLL_WINDOW_SECONDS with
    impact_score >= MIN_IMPACT_SCORE. Returns list of article dicts.
    """
    cutoff_ms = int((time.time() - POLL_WINDOW_SECONDS) * 1000)

    articles = (
        db.query(db_models.NewsArticle)
        .filter(db_models.NewsArticle.published_at >= cutoff_ms)
        .filter(db_models.NewsArticle.impact_score >= MIN_IMPACT_SCORE)
        .order_by(db_models.NewsArticle.published_at.desc())
        .all()
    )

    return [
        {
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "source": a.source,
            "published_at": a.published_at,
            "impact_score": a.impact_score,
            "impact_summary": a.impact_summary,
            "executive_summary": a.executive_summary,
            "news_category": a.news_category,
            "affected_symbols": a.affected_symbols or [],
            "raw_analysis_data": a.raw_analysis_data,
        }
        for a in articles
    ]


def _fetch_past_news_for_symbol(db: Session, symbol: str, hours_back: float = 4.0) -> list[dict]:
    """
    Fetch all high-impact news for a symbol published in the last `hours_back` hours.
    Used as "past context" for the Gemini live analyzer.
    """
    cutoff_ms = int((time.time() - hours_back * 3600) * 1000)

    articles = (
        db.query(db_models.NewsArticle)
        .filter(db_models.NewsArticle.affected_symbols.any(symbol))
        .filter(db_models.NewsArticle.published_at >= cutoff_ms)
        .filter(db_models.NewsArticle.impact_score >= MIN_IMPACT_SCORE)
        .order_by(db_models.NewsArticle.published_at.desc())
        .limit(10)
        .all()
    )

    return [
        {
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "published_at": a.published_at,
            "impact_score": a.impact_score,
            "executive_summary": a.executive_summary,
        }
        for a in articles
    ]


def _group_articles_by_symbol(articles: list[dict]) -> dict[str, list[dict]]:
    """Group article dicts by their affected symbols."""
    grouped: dict[str, list[dict]] = {}
    for art in articles:
        symbols = art.get("affected_symbols") or []
        for sym in symbols:
            if sym and sym != "GENERAL":
                grouped.setdefault(sym, []).append(art)
    return grouped


# ── Deduplication ─────────────────────────────────────────────────────────────

def _reset_dedup_if_new_day():
    """Reset the processed article IDs set at the start of each new trading day."""
    global _processed_article_ids, _processed_date
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if today != _processed_date:
        _processed_article_ids = set()
        _processed_date = today
        print(f"  [DEDUP] Reset processed IDs for new day: {today}")


def _filter_new_articles(articles: list[dict]) -> list[dict]:
    """Remove articles that have already been processed in this session."""
    new = [a for a in articles if a["id"] not in _processed_article_ids]
    return new


def _mark_processed(article_ids: list[str]):
    """Mark article IDs as processed to avoid re-analysis."""
    _processed_article_ids.update(article_ids)


# ── DB Persistence ────────────────────────────────────────────────────────────

def _save_live_event(
    db: Session,
    symbol: str,
    news_ids: list[str],
    current_price: float | None,
    publish_time_price: float | None,
    gemini_output: dict,
) -> db_models.DBLiveNewsEvent:
    """Save a live news analysis result to the DB."""
    now_ms = int(time.time() * 1000)
    market_date = datetime.now(IST).strftime("%Y-%m-%d")
    event_id = f"live-{symbol}-{now_ms}"

    event = db_models.DBLiveNewsEvent(
        id=event_id,
        symbol=symbol,
        news_ids=news_ids,
        triggered_at=now_ms,
        current_price=current_price,
        publish_time_price=publish_time_price,
        gemini_output=gemini_output,
        should_trade=gemini_output.get("should_trade", False),
        confidence=float(gemini_output.get("confidence", 0)),
        agent3_triggered=False,
        market_date=market_date,
        created_at=now_ms,
    )
    db.add(event)
    db.commit()
    return event



# ── Main Run Function ─────────────────────────────────────────────────────────

def run_live_news_monitor() -> dict:
    """
    Main entry point — called every minute by the scheduler during market hours.

    Returns a summary dict describing what was processed.
    """
    started_at = int(time.time() * 1000)
    now = datetime.now(IST)

    _reset_dedup_if_new_day()

    db = SessionLocal()
    summary = {
        "status": "idle",
        "new_articles_found": 0,
        "symbols_analyzed": 0,
        "trade_signals_generated": 0,
        "agent3_triggered": 0,
        "errors": [],
        "ran_at": now.strftime("%H:%M:%S IST"),
    }

    try:
        # ── Step 0: Market hours guard ────────────────────────────────────────
        today = now.date()
        if not is_trading_day(today):
            summary["status"] = "skipped_non_trading_day"
            return summary

        hhmm = now.hour * 100 + now.minute
        if hhmm < 915 or hhmm > 1530:
            summary["status"] = "skipped_outside_market_hours"
            return summary

        print(f"\n[LIVE AGENT] {now.strftime('%H:%M:%S IST')} — Polling for live news...")

        # ── Step 1: Pull fresh news from endpoint → get newly saved article IDs ──
        fetched_ids: list[str] = []
        config = _get_store().config
        if config.news_endpoint_url:
            fetched_ids = trigger_news_fetch(config.news_endpoint_url, db)
            if fetched_ids:
                print(f"  [FETCH] Pulled {len(fetched_ids)} new articles from endpoint")

        # ── Step 2: Query ALL articles we need to process ─────────────────────
        # Strategy: Use the freshly fetched IDs (regardless of published_at)
        # PLUS any recent high-impact articles from the DB that haven't been
        # processed yet (catches articles arriving through other channels).
        articles_by_id: dict[str, dict] = {}

        # 2a. Load the freshly fetched articles by their IDs (no time filter)
        if fetched_ids:
            fetched_articles = (
                db.query(db_models.NewsArticle)
                .filter(db_models.NewsArticle.id.in_(fetched_ids))
                .filter(db_models.NewsArticle.impact_score >= MIN_IMPACT_SCORE)
                .all()
            )
            for a in fetched_articles:
                articles_by_id[a.id] = {
                    "id": a.id,
                    "title": a.title,
                    "description": a.description,
                    "source": a.source,
                    "published_at": a.published_at,
                    "impact_score": a.impact_score,
                    "impact_summary": a.impact_summary,
                    "executive_summary": a.executive_summary,
                    "news_category": a.news_category,
                    "affected_symbols": a.affected_symbols or [],
                    "raw_analysis_data": a.raw_analysis_data,
                }

        # 2b. Also sweep for any recent DB articles (fallback for non-endpoint sources)
        recent_articles = _fetch_new_news(db)
        for a in recent_articles:
            if a["id"] not in articles_by_id:
                articles_by_id[a["id"]] = a

        all_candidates = list(articles_by_id.values())

        if not all_candidates:
            summary["status"] = "no_new_news"
            print(f"  [LIVE AGENT] No articles to process")
            return summary

        # ── Step 3: Deduplicate — only process genuinely new articles ─────────
        new_articles = _filter_new_articles(all_candidates)
        if not new_articles:
            summary["status"] = "all_already_processed"
            print(f"  [LIVE AGENT] {len(all_candidates)} article(s) already processed — skipping")
            return summary

        summary["new_articles_found"] = len(new_articles)
        print(f"  [LIVE AGENT] {len(new_articles)} new article(s) to analyze")

        # ── Step 4: Group by symbol ───────────────────────────────────────────
        grouped = _group_articles_by_symbol(new_articles)
        if not grouped:
            summary["status"] = "no_symbols_affected"
            return summary

        print(f"  [LIVE AGENT] Affects {len(grouped)} symbol(s): {', '.join(sorted(grouped.keys()))}")

        # Mark all as processed NOW to prevent re-processing even if we fail below
        _mark_processed([a["id"] for a in new_articles])

        # ── Step 5: Analyze each symbol ───────────────────────────────────────
        symbols_analyzed = 0
        trade_signals = 0
        agent3_triggered = 0

        for symbol in sorted(grouped.keys()):
            symbol_articles = grouped[symbol]

            print(f"\n  -- Analyzing {symbol} ({len(symbol_articles)} article(s)) --")

            try:
                # 5a. Fetch live market data (full context)
                live_data = _get_live_stock_data(symbol)
                current_price = live_data["ltp"] if live_data else None
                
                if live_data:
                    print(
                        f"     LTP: Rs.{live_data['ltp']:.2f} | "
                        f"Open: {live_data['open']} | High: {live_data['high']} | Low: {live_data['low']} | "
                        f"Change: {live_data['day_change_pct']:+.2f}% | "
                        f"Vol: {live_data['volume']:,} | Gap: {live_data['gap_pct']:+.2f}%"
                    )
                else:
                    print(f"     Live data: N/A")

                # 5b. Fetch price at time of earliest article in this batch
                earliest_article = min(symbol_articles, key=lambda a: a.get("published_at", 0))
                publish_ts_ms = earliest_article.get("published_at", 0)
                publish_time_price = _get_price_at_time(symbol, publish_ts_ms)
                print(f"     Publish-time price: {f'Rs.{publish_time_price:.2f}' if publish_time_price else 'N/A'}")

                # 5c. Fetch past news context for this symbol (last 4h)
                past_news = _fetch_past_news_for_symbol(db, symbol, hours_back=4.0)
                # Exclude the current new articles from past news
                new_ids = {a["id"] for a in symbol_articles}
                past_news = [p for p in past_news if p["id"] not in new_ids]
                print(f"     Past news context: {len(past_news)} article(s)")

                # 5d. Run Gemini Live Analyzer (with full market data)
                gemini_output = analyze_live(
                    symbol=symbol,
                    new_news=symbol_articles,
                    past_news_bundle=past_news if past_news else None,
                    current_price=current_price,
                    publish_time_price=publish_time_price,
                    live_market_data=live_data,
                )

                should_trade = gemini_output.get("should_trade", False)
                confidence = gemini_output.get("confidence", 0)
                bias = gemini_output.get("market_bias", "NEUTRAL")

                print(
                    f"     -> Bias: {bias} | Should Trade: {should_trade} | "
                    f"Confidence: {confidence} | "
                    f"Reacted: {gemini_output.get('market_reacted', False)} "
                    f"({gemini_output.get('reaction_magnitude_pct', 0):.1f}%)"
                )
                print(f"     -> {gemini_output.get('trade_reason', '')}")

                # 5e. Save to DB
                live_event = _save_live_event(
                    db=db,
                    symbol=symbol,
                    news_ids=[a["id"] for a in symbol_articles],
                    current_price=current_price,
                    publish_time_price=publish_time_price,
                    gemini_output=gemini_output,
                )

                symbols_analyzed += 1

                # 5f. Trigger the full pipeline (Agent 2.5 -> 3) if confident
                if should_trade and confidence >= AGENT3_TRIGGER_CONFIDENCE:
                    print(f"     Confidence high ({confidence}) -> Triggering full pipeline (2.5 -> 3)...")
                    try:
                        from agent.execution.execution_agent import trigger_pipeline_from_live_news
                        result = trigger_pipeline_from_live_news(
                            symbol=symbol,
                            live_news_output=gemini_output,
                            db=db,
                        )
                        if result.get("success"):
                            trade_signals += 1
                            agent3_triggered += 1
                            live_event.agent3_triggered = True
                            db.commit()
                        else:
                            print(f"     [PIPELINE] Failed to trigger: {result.get('error')}")
                    except Exception as ep:
                        print(f"     [PIPELINE ERROR] {ep}")
                        traceback.print_exc()
                else:
                    print(f"     [LIVE AGENT] Confidence {confidence} below threshold {AGENT3_TRIGGER_CONFIDENCE} or should_trade=False. Skipping Agent 3.")

            except Exception as e:
                err_msg = f"{symbol}: {e}"
                summary["errors"].append(err_msg)
                print(f"     [ERROR] {err_msg}")
                traceback.print_exc()
                try:
                    db.rollback()
                except Exception:
                    pass

        summary["status"] = "completed"
        summary["symbols_analyzed"] = symbols_analyzed
        summary["trade_signals_generated"] = trade_signals
        summary["agent3_triggered"] = agent3_triggered
        summary["duration_ms"] = int(time.time() * 1000) - started_at

        print(
            f"\n  [LIVE AGENT DONE] {symbols_analyzed} analyzed | "
            f"{trade_signals} trade signal(s) | "
            f"{agent3_triggered} Agent 3 trigger(s) | "
            f"{summary['duration_ms']}ms"
        )

    except Exception as e:
        summary["status"] = "error"
        summary["errors"].append(str(e))
        print(f"[LIVE AGENT] CRITICAL ERROR: {e}")
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()

    return summary
