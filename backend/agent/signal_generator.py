"""Signal Generator — main orchestrator for the Agent 1 (Discovery) pipeline.

Pipeline: Fetch News → Group by Symbol → Fetch Company Context → Agent 1 Analysis → Save to DB.

Agent 1 OUTPUT is a stock-level event intelligence report (new schema).
It answers: "What happened, why does it matter, and should this pass to Agent 2?"

Key mapping decisions (new schema → DB):
  - signal_type: WATCH if should_pass_to_agent_2=true, else NO_TRADE
  - trade_mode:  always NONE at this stage (Agent 2 sets trade direction)
  - confidence:  mapped from final_confidence (LOW=20, MEDIUM=55, HIGH=80)
  - reasoning:   stores full new-schema result (with legacy compat fields attached)
  - agent_1_reasoning: stores combined_view.reasoning object separately for fast access
  - All raw Agent 1 output is stored in the `reasoning` JSON column verbatim
"""

import time
import uuid
import logging
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from store import _get_store

from agent.data_collector import fetch_recent_news, trigger_news_fetch, fetch_stock_data_for_symbols
from agent.gemini_analyzer import analyze_stock
from agent.market_calendar import get_news_fetch_window, is_trading_day, IST as MARKET_IST

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.propagate = False

IST = timezone(timedelta(hours=5, minutes=30))

CONFIDENCE_TO_INT = {"LOW": 20, "MEDIUM": 55, "HIGH": 80}

EMPTY_REASONING = {
    "why_agent_gave_this_view": "",
    "main_driver": "",
    "supporting_points": [],
    "risk_points": [],
    "confidence_reason": "",
    "what_agent_2_should_validate": [],
}


def _ensure_agent_1_reasoning_column():
    """
    Safe ALTER TABLE migration: adds agent_1_reasoning JSON column to trade_signals
    if it does not already exist.  Runs once at startup — harmless if column exists.
    """
    from database import engine
    try:
        with engine.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE trade_signals "
                    "ADD COLUMN IF NOT EXISTS agent_1_reasoning JSON"
                )
            )
            conn.commit()
            logger.info("[DB] agent_1_reasoning column ensured on trade_signals")
    except Exception as e:
        logger.warning("[DB] agent_1_reasoning migration skipped (may already exist): %s", e)


# Run migration once at import time (safe — uses IF NOT EXISTS)
try:
    _ensure_agent_1_reasoning_column()
except Exception:
    pass


def _market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def run_full_analysis(db: Session = None) -> dict:
    """
    Execute the complete Agent 1 (Discovery) pipeline.

    Returns a summary dict with all stock-level event intelligence reports.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        market_date = _market_date_str()
        run_id = f"run-{market_date}-{uuid.uuid4().hex[:8]}"
        started_at = _now_ms()

        from_dt, to_dt, window_info = get_news_fetch_window()

        logger.info("=" * 60)
        logger.info("[AGENT 1] DISCOVERY -- Run ID: %s", run_id)
        logger.info("   Market Date: %s", market_date)
        logger.info("   Started: %s", datetime.now(IST).strftime("%H:%M:%S IST"))
        logger.info("   News Window: %s -> %s", window_info["from_time"], window_info["to_time"])
        logger.info("=" * 60)

        # -- Step 1: Optionally fetch fresh news ------------------------------
        # config = _get_store().config
        # if config.news_endpoint_url:
        #     logger.info("[STEP 1] Fetching fresh news from endpoint...")
        #     new_count = trigger_news_fetch(config.news_endpoint_url, db)
        #     logger.info("   [OK] Saved %d new articles", new_count)
        # else:
        #     logger.info("[STEP 1] Using existing news in DB (no endpoint configured)")
        logger.info("[STEP 1] Using existing news in DB (fetch explicitly disabled)")

        # -- Step 2: Get recent news grouped by symbol ------------------------
        logger.info("[STEP 2] Collecting recent news from DB (smart calendar window)...")
        grouped_news = fetch_recent_news(db)
        symbols = sorted(list(grouped_news.keys()))
        total_articles = sum(len(v) for v in grouped_news.values())
        logger.info("   [OK] Found %d articles across %d symbols", total_articles, len(symbols))

        if not symbols:
            logger.warning("[WARN] No actionable news found. Agent run complete with 0 assessments.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "generated_at": _now_ms(),
                "total_analyzed": 0,
                "signals_summary": _empty_summary(),
                "signals": [],
                "duration_ms": _now_ms() - started_at,
            }

        # -- Step 3: Fetch market context (company_name only) -----------------
        logger.info("[STEP 3] Fetching market context for %d symbols...", len(symbols))
        stock_data_map = fetch_stock_data_for_symbols(symbols)
        logger.info("   [OK] Got context for %d symbols", len(stock_data_map))

        # -- Step 4: Analyze each symbol (concurrent, up to 5 threads) --------
        logger.info("[STEP 4] Running Agent 1 analysis (%d symbols)...", len(symbols))
        signals = []
        summary = _empty_summary()

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _analyze_one(sym: str) -> tuple:
            """Run one Agent 1 analysis in a thread."""
            articles = grouped_news.get(sym, [])
            stock = stock_data_map.get(sym)
            if not stock:
                logger.warning("   [SKIP] %s: No market context", sym)
                return sym, None, []
            logger.info("   -- Analyzing %s (%d articles) --", sym, len(articles))
            try:
                result = analyze_stock(sym, articles, stock, market_date)
                # Attach legacy compat fields so Agent 2 fallback still works
                # result = to_legacy_discovery_fields(result) # Removed: system is now native combined_view
                cv = result.get("combined_view", {})
                logger.info(
                    "      [OK] %s | bias=%s | pass=%s | source=%s",
                    sym,
                    cv.get("final_bias", "?"),
                    cv.get("should_pass_to_agent_2", "?"),
                    result.get("_source", "?"),
                )
                return sym, result, articles
            except Exception as e:
                logger.exception("      [ERROR] %s: Analysis failed", sym)
                return sym, None, articles

        results_map = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_analyze_one, sym): sym for sym in symbols}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    s, result, arts = future.result()
                    if result is not None:
                        results_map[s] = (result, arts)
                except Exception as e:
                    logger.error("   [ERROR] Thread for %s failed: %s", sym, e)

        logger.info("   [CONCURRENT] Got %d/%d results", len(results_map), len(symbols))

        # -- Write results to DB sequentially to avoid deadlocks --------------
        for sym in symbols:
            if sym not in results_map:
                continue

            gemini_result, articles = results_map[sym]

            # Extract new-schema fields
            cv = gemini_result.get("combined_view", {})
            should_pass = cv.get("should_pass_to_agent_2", False)
            final_conf_str = cv.get("final_confidence", "LOW")
            a1_reasoning = cv.get("reasoning") or EMPTY_REASONING

            # Map to DB fields
            signal_type = "WATCH" if should_pass else "NO_TRADE"
            trade_mode = "NONE"
            confidence_int = CONFIDENCE_TO_INT.get(final_conf_str, 20)

            # Derive materiality for summary counters from confidence
            materiality = "low"
            if should_pass:
                materiality = "high" if final_conf_str == "HIGH" else "medium"

            logger.info(
                "[AGENT 1] SIGNAL | symbol=%s | signal_type=%s | "
                "final_confidence=%s | should_pass=%s | main_driver=%s",
                sym, signal_type, final_conf_str, should_pass,
                a1_reasoning.get("main_driver", "N/A"),
            )

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
                "confidence": confidence_int,
                "reasoning": gemini_result,
                "news_article_ids": [a["id"] for a in articles],
                "stock_snapshot": stock_data_map.get(sym),
                "generated_at": _now_ms(),
                "market_date": market_date,
                "gemini_source": gemini_result.get("_source", "unknown"),
            }
            signals.append(signal_record)
            _update_summary(summary, should_pass, materiality)

            # Upsert to DB
            existing = db.query(db_models.DBTradeSignal).filter(
                db_models.DBTradeSignal.symbol == sym,
                db_models.DBTradeSignal.market_date == market_date
            ).first()

            if existing:
                existing.signal_type = signal_type
                existing.confidence = confidence_int
                existing.reasoning = gemini_result
                existing.agent_1_reasoning = a1_reasoning
                # Agent 2 now consumes the new combined_view schema natively
                existing.news_article_ids = [a["id"] for a in articles]
                existing.stock_snapshot = stock_data_map.get(sym)
                existing.generated_at = _now_ms()
                existing.status = "pending_confirmation"
                existing.confirmation_status = "pending"
                existing.execution_status = "pending"
                existing.confirmed_at = None
                existing.executed_at = None
                logger.info("      [DB] Updated existing signal for %s", sym)
                logger.info(
                    "      [DB] Stored agent_1_reasoning for signal id=%s sym=%s",
                    existing.id, sym,
                )
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
                    confidence=confidence_int,
                    reasoning=gemini_result,
                    agent_1_reasoning=a1_reasoning,
                    news_article_ids=[a["id"] for a in articles],
                    stock_snapshot=stock_data_map.get(sym),
                    generated_at=_now_ms(),
                    market_date=market_date,
                    status="pending_confirmation",
                    confirmation_status="pending",
                )
                db.add(db_signal)
                logger.info("      [DB] Created new signal for %s", sym)
                logger.info(
                    "      [DB] Stored agent_1_reasoning for signal id=%s sym=%s",
                    signal_id, sym,
                )

            db.commit()  # Commit per symbol to minimise lock contention

        duration = _now_ms() - started_at

        logger.info("=" * 60)
        logger.info("[DONE] Agent 1 (Discovery) complete!")
        logger.info("   Analyzed: %d symbols", len(signals))
        logger.info("   WATCH (Pass): %d | NO_TRADE (Reject): %d", summary["watch"], summary["ignore"])
        logger.info("   Materiality: High=%d Medium=%d Low=%d", summary["strong"], summary["moderate"], summary["weak"])
        logger.info("   Duration: %dms", duration)
        logger.info("=" * 60)

        # Sort: WATCH first, then by confidence descending
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
    return {
        "watch": 0,
        "ignore": 0,
        "stale": 0,
        "strong": 0,
        "moderate": 0,
        "weak": 0,
    }


def _update_summary(summary: dict, should_pass: bool, materiality: str):
    if should_pass:
        summary["watch"] += 1
    else:
        summary["ignore"] += 1

    m = (materiality or "low").lower()
    if m == "high":
        summary["strong"] += 1
    elif m == "medium":
        summary["moderate"] += 1
    else:
        summary["weak"] += 1


def _verdict_to_signal_type(should_pass: bool) -> str:
    return "WATCH" if should_pass else "NO_TRADE"
