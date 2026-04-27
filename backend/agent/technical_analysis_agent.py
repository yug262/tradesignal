"""Technical Analysis Agent — Phase 2.5 of the trading pipeline.

Runs after Agent 2 (Confirmation) confirms a signal.
Takes confirmed signals, fetches OHLCV + TA-Lib indicators based on
Agent 2's indicator requests, and produces structured technical
intelligence for Agent 3.

Pipeline:
  1. Query DB for today's confirmed signals pending technical analysis
  2. For each signal:
     a. Read Agent 2's indicators_to_check and timeframe_plan
     b. Fetch OHLCV candles via Groww API
     c. Compute TA-Lib indicators (time-series)
     d. Build S/R levels from Agent 2 technical_validation
     e. Send to Gemini Technical Analyzer
     f. Store technical_analysis_data on the signal
  3. Auto-trigger Agent 3 (Execution Planner)

Agent 2.5 does NOT generate trades — it only interprets technicals.
"""

import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from agent.data_collector import fetch_indicator_data, _fetch_raw_candles
from agent.gemini_technical_analyzer import analyze_technicals

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _build_candle_data(symbol: str, timeframe_plan: dict) -> list:
    """Fetch OHLCV candles and return as list of dicts."""
    primary_tf = timeframe_plan.get("primary_timeframe", "1m")

    TIMEFRAME_MAP = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "1h": 60, "1D": 1440}
    interval = TIMEFRAME_MAP.get(primary_tf, 1)

    raw_candles = _fetch_raw_candles(symbol, interval, count=50)
    if not raw_candles:
        return []

    candles = []
    for c in raw_candles:
        if len(c) >= 5:
            candle = {
                "timestamp": c[0],
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": int(c[5]) if len(c) > 5 and c[5] else 0,
            }
            candles.append(candle)

    return candles


def _build_indicator_data(
    db: Session, symbol: str, indicators_to_check: dict,
    trade_mode: str, ltp: float
) -> dict:
    """Fetch all indicators requested by Agent 2 and return structured data."""
    result = {}

    for category, indicator_names in indicators_to_check.items():
        if not isinstance(indicator_names, list):
            continue
        for ind_name in indicator_names:
            # Skip non-TA-Lib indicators
            if ind_name in ("CANDLESTICK_PATTERNS", "CHART_PATTERNS",
                           "PIVOT_POINTS", "FIBONACCI_LEVELS",
                           "DYNAMIC_SUPPORT_RESISTANCE", "ICHIMOKU",
                           "PARABOLIC_SAR", "KELTNER_CHANNEL",
                           "DONCHIAN_CHANNEL"):
                continue

            # Map indicator to TA-Lib function name
            talib_name = ind_name.upper()
            if talib_name == "BOLLINGER_BANDS":
                talib_name = "BBANDS"
            elif talib_name == "STOCHASTIC":
                talib_name = "STOCH"

            try:
                raw = fetch_indicator_data(
                    db=db,
                    symbol=symbol,
                    trade_mode=trade_mode,
                    indicator_name=talib_name,
                    timeframe="1m" if trade_mode == "INTRADAY" else "1D",
                    ltp=ltp,
                )
                if raw:
                    values = [p["value"] for p in raw]
                    timestamps = [p["timestamp"] for p in raw]
                    trend = _compute_series_trend(values)
                    result[ind_name] = {
                        "last_20": [round(v, 4) for v in values[-20:]],
                        "timestamps": timestamps[-20:],
                        "latest": round(values[-1], 4) if values else None,
                        "trend": trend,
                        "data_points": len(values),
                    }
                else:
                    result[ind_name] = {
                        "last_20": [],
                        "timestamps": [],
                        "latest": None,
                        "trend": "unavailable",
                        "data_points": 0,
                    }
            except Exception as e:
                logger.warning("[AGENT 2.5] Indicator %s failed for %s: %s", ind_name, symbol, e)
                result[ind_name] = {
                    "last_20": [],
                    "timestamps": [],
                    "latest": None,
                    "trend": "error",
                    "data_points": 0,
                    "error": str(e),
                }

    return result


def _compute_series_trend(values: list) -> str:
    """Classify a numeric series as rising/falling/flat/mixed."""
    if not values or len(values) < 3:
        return "insufficient_data"
    last3 = values[-3:]
    if last3[2] > last3[1] > last3[0]:
        return "rising"
    elif last3[2] < last3[1] < last3[0]:
        return "falling"
    elif abs(last3[2] - last3[0]) / max(abs(last3[0]), 0.001) < 0.01:
        return "flat"
    return "mixed"


def _build_sr_levels(agent2_data: dict) -> dict:
    """Extract support/resistance levels from Agent 2 technical_validation."""
    tv = agent2_data.get("technical_validation", {})
    return {
        "nearest_support": tv.get("nearest_support"),
        "nearest_resistance": tv.get("nearest_resistance"),
        "support_respected": tv.get("support_respected", True),
        "resistance_respected": tv.get("resistance_respected", True),
        "near_resistance_risk": tv.get("near_resistance_risk", "LOW"),
        "near_support_risk": tv.get("near_support_risk", "LOW"),
        "level_comment": tv.get("level_comment", ""),
    }


def run_technical_analysis(db: Session = None, signal_ids: list = None) -> dict:
    """
    Execute the Technical Analysis pipeline (Agent 2.5).

    Fetches all confirmed signals for today, computes indicators,
    and produces structured technical analysis for Agent 3.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        market_date = _market_date_str()
        run_id = f"ta-{market_date}-{uuid.uuid4().hex[:8]}"
        started_at = _now_ms()

        logger.info("=" * 60)
        logger.info("[AGENT 2.5] TECHNICAL ANALYSIS AGENT -- Run ID: %s", run_id)
        logger.info("   Market Date: %s", market_date)
        logger.info("   Time: %s", datetime.now(IST).strftime("%H:%M:%S IST"))
        logger.info("=" * 60)

        # Step 1: Get confirmed signals that haven't been technically analyzed
        query = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.market_date == market_date)
            .filter(db_models.DBTradeSignal.confirmation_status == "confirmed")
            .filter(db_models.DBTradeSignal.execution_status == "pending")
        )
        if signal_ids:
            query = query.filter(db_models.DBTradeSignal.id.in_(signal_ids))
            
        confirmed_signals = query.order_by(db_models.DBTradeSignal.symbol).all()

        if not confirmed_signals:
            logger.warning("[AGENT 2.5] No confirmed signals found for technical analysis.")
            return {
                "run_id": run_id,
                "market_date": market_date,
                "total_analyzed": 0,
                "summary": {"analyzed": 0, "skipped": 0},
                "results": [],
                "duration_ms": 0,
            }

        logger.info("[AGENT 2.5] Analyzing %d confirmed signals...", len(confirmed_signals))

        results = []
        summary = {"analyzed": 0, "skipped": 0}

        for sig in confirmed_signals:
            agent2_data = sig.confirmation_data if isinstance(sig.confirmation_data, dict) else {}

            # Skip if Agent 2 already has technical_analysis_data
            if isinstance(sig.execution_data, dict) and sig.execution_data.get("_has_agent25"):
                logger.info("[TRIGGER] Agent 2.5 skipped %s: already exists", sig.symbol)
                summary["skipped"] += 1
                continue

            indicators_to_check = agent2_data.get("indicators_to_check", {})
            timeframe_plan = agent2_data.get("timeframe_plan", {})
            trade_mode = agent2_data.get("trade_suitability", {}).get("mode", "INTRADAY")

            # Get LTP from snapshot
            snapshot = sig.stock_snapshot if isinstance(sig.stock_snapshot, dict) else {}
            ltp = snapshot.get("last_close") or 0

            logger.info("   [PROCESSING] %s (mode=%s)", sig.symbol, trade_mode)

            # Step 2: Fetch OHLCV candles
            candle_data = _build_candle_data(sig.symbol, timeframe_plan)
            if not candle_data:
                logger.warning("   [SKIP] %s: No candle data available", sig.symbol)
                summary["skipped"] += 1
                continue

            if candle_data and ltp == 0:
                ltp = candle_data[-1].get("close", 0)

            # Step 3: Compute TA-Lib indicators
            indicator_data = _build_indicator_data(
                db, sig.symbol, indicators_to_check, trade_mode, ltp
            )

            # Step 4: Build S/R levels
            sr_levels = _build_sr_levels(agent2_data)

            # Step 4a: Generate technical chart and pass to Gemini as a visual
            chart_image_bytes = None
            try:
                from services.chart_generator import generate_technical_chart
                from agent.execution_agent import get_default_indicators
                # Infer bias from Agent 2 for chart indicator selection
                a1_view = agent2_data.get("agent_1_view", {})
                bias = str(a1_view.get("final_bias", "NEUTRAL")).upper()
                chart_indicators = get_default_indicators(trade_mode=trade_mode, bias=bias)
                chart_image_bytes = generate_technical_chart(
                    symbol=sig.symbol,
                    trade_mode=trade_mode,
                    requested_indicators=chart_indicators,
                    ltp=ltp,
                )
                if chart_image_bytes:
                    logger.info("   [CHART] %s: Chart generated (%dKB) — sending to Gemini",
                                sig.symbol, len(chart_image_bytes) // 1024)
                else:
                    logger.warning("   [CHART] %s: Chart generation returned None — text-only", sig.symbol)
            except Exception as ce:
                logger.warning("   [CHART] %s: Chart generation failed: %s — text-only", sig.symbol, ce)

            # Step 5: Run Gemini Technical Analysis
            try:
                ta_result = analyze_technicals(
                    symbol=sig.symbol,
                    market_date=market_date,
                    agent2_data=agent2_data,
                    candle_data=candle_data,
                    indicator_data=indicator_data,
                    sr_levels=sr_levels,
                    chart_image_bytes=chart_image_bytes,
                )
            except Exception as e:
                logger.error("[TRIGGER] Agent 2.5 failed %s: %s", sig.symbol, e)
                existing_exec = sig.execution_data if isinstance(sig.execution_data, dict) else {}
                existing_exec["technical_analysis_error"] = str(e)
                sig.execution_data = existing_exec
                db.commit()
                summary["skipped"] += 1
                continue

            # Step 6: Store result on the signal
            # We store in execution_data temporarily, with a flag
            ta_output = {
                "_has_agent25": True,
                "technical_analysis_data": ta_result,
                "candle_count": len(candle_data),
                "indicators_computed": list(indicator_data.keys()),
                "analyzed_at": _now_ms(),
            }

            # Merge with any existing execution_data
            existing_exec = sig.execution_data if isinstance(sig.execution_data, dict) else {}
            existing_exec.update(ta_output)
            sig.execution_data = existing_exec

            db.commit()

            # Log output
            ta = ta_result.get("technical_analysis", {})
            overall = ta.get("overall", {})
            handoff = ta.get("agent_3_handoff", {})

            logger.info("=" * 40)
            logger.info("[AGENT 2.5 OUTPUT] %s", sig.symbol)
            logger.info("   bias: %s", overall.get("technical_bias"))
            logger.info("   confidence: %s", overall.get("confidence"))
            logger.info("   grade: %s", overall.get("technical_grade"))
            logger.info("   readiness: %s", overall.get("trade_readiness"))
            logger.info("   go/no-go: %s", handoff.get("technical_go_no_go"))
            logger.info("   source: %s", ta_result.get("_source"))
            logger.info("=" * 40)

            results.append({
                "symbol": sig.symbol,
                "technical_bias": overall.get("technical_bias"),
                "confidence": overall.get("confidence"),
                "grade": overall.get("technical_grade"),
                "trade_readiness": overall.get("trade_readiness"),
                "go_no_go": handoff.get("technical_go_no_go"),
            })
            summary["analyzed"] += 1
            
            logger.info("[TRIGGER] Agent 2.5 completed %s", sig.symbol)
            
            # If Agent 2.5 fell back due to API issues, but Agent 2 already CONFIRMED —
            # don't let the fallback veto a confirmed signal. Override go_no_go to GO.
            ta_source = ta_result.get("_source", "")
            if ta_source == "agent25_fallback" and handoff.get("technical_go_no_go") == "WAIT":
                conf_data = sig.confirmation_data or {}
                a2_status = conf_data.get("validation", {}).get("status", "")
                if a2_status == "CONFIRMED":
                    logger.warning("[AGENT 2.5] Fallback returned WAIT but Agent 2 is CONFIRMED — overriding go_no_go to GO for %s", sig.symbol)
                    handoff["technical_go_no_go"] = "GO"

            # Auto-trigger Agent 3 per signal
            if handoff.get("technical_go_no_go") == "GO":
                logger.info("[TRIGGER] Agent 3 triggered by Agent 2.5 %s", sig.symbol)
                try:
                    from agent.execution_agent import run_execution_planner
                    run_execution_planner(db, signal_ids=[sig.id])
                except Exception as e:
                    logger.error("[ERROR] Triggering Agent 3 failed for %s: %s", sig.symbol, e)
            else:
                logger.info("[TRIGGER] Agent 3 not triggered %s: technical_go_no_go=%s", sig.symbol, handoff.get("technical_go_no_go"))

        duration = _now_ms() - started_at

        logger.info("=" * 60)
        logger.info("[DONE] Agent 2.5 Technical Analysis Complete")
        logger.info("   Analyzed: %d | Skipped: %d", summary["analyzed"], summary["skipped"])
        logger.info("   Duration: %dms", duration)
        logger.info("=" * 60)

        # Auto-trigger Agent 3 (Removed from end of batch, now done per signal)
        agent3_result = None

        return {
            "run_id": run_id,
            "market_date": market_date,
            "total_analyzed": len(confirmed_signals),
            "summary": summary,
            "results": results,
            "agent3_execution": agent3_result,
            "duration_ms": duration,
        }

    finally:
        if own_session:
            db.close()
