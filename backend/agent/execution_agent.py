"""Execution Agent — Phase 3 of the trading pipeline.

Runs after Agent 2 (Confirmation Agent).
Takes validated trades (confirmation_status = 'confirmed') and generates
a precise execution plan using LIVE market data.
"""

import time
import uuid
import traceback
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

import db_models
from database import SessionLocal
from agent.data_collector import fetch_stock_data_for_symbols
from agent.gemini_executor import plan_execution
from services.indicator_service import build_technical_context
from services.chart_generator import generate_technical_chart

IST = timezone(timedelta(hours=5, minutes=30))

# Comprehensive pool of default indicators based on user's requested categories
# Comprehensive pool of default indicators based on user's requested categories
ALL_DEFAULT_INDICATORS = {
    "Trend": [
        {"name": "SMA", "timeframe": "1m", "period": 20, "reason": "Simple Trend"},
        {"name": "EMA", "timeframe": "1m", "period": 20, "reason": "Primary Trend Alignment"},
        {"name": "WMA", "timeframe": "1m", "period": 20, "reason": "Weighted Trend"},
        {"name": "DEMA", "timeframe": "1m", "period": 20, "reason": "Double EMA Trend"},
        {"name": "TEMA", "timeframe": "1m", "period": 20, "reason": "Triple EMA Trend"},
        {"name": "MACD", "timeframe": "1m", "period": 14, "reason": "Trend & Momentum Reversal"},
        {"name": "ADX", "timeframe": "1m", "period": 14, "reason": "Trend Strength"},
        {"name": "AROON", "timeframe": "1m", "period": 14, "reason": "Aroon Trend Identification"},
        {"name": "SAR", "timeframe": "1m", "period": 0, "reason": "Parabolic SAR Reversal"},
        {"name": "ICHIMOKU", "timeframe": "1m", "period": 0, "reason": "Ichimoku Cloud Trend"},
    ],
    "Momentum": [
        {"name": "RSI", "timeframe": "1m", "period": 14, "reason": "Momentum & Exhaustion (Overbought/Oversold)"},
        {"name": "STOCH", "timeframe": "1m", "period": 14, "reason": "Stochastic Oscillator"},
        {"name": "CCI", "timeframe": "1m", "period": 14, "reason": "Commodity Channel Index"},
        {"name": "ROC", "timeframe": "1m", "period": 14, "reason": "Rate of Change"},
        {"name": "MOM", "timeframe": "1m", "period": 10, "reason": "Pure Momentum"},
        {"name": "WILLR", "timeframe": "1m", "period": 14, "reason": "Williams %R Exhaustion"},
        {"name": "MFI", "timeframe": "1m", "period": 14, "reason": "Money Flow Index"},
    ],
    "Volatility": [
        {"name": "ATR", "timeframe": "1m", "period": 14, "reason": "Volatility-based stop loss distance"},
        {"name": "BBANDS", "timeframe": "1m", "period": 20, "reason": "Volatility Breakouts & Reversion"},
        {"name": "KELTNER", "timeframe": "1m", "period": 20, "reason": "Keltner Channel"},
        {"name": "DONCHIAN", "timeframe": "1m", "period": 20, "reason": "Donchian Channel"},
        {"name": "NATR", "timeframe": "1m", "period": 14, "reason": "Normalized Volatility"},
    ],
    "Volume": [
        {"name": "OBV", "timeframe": "1m", "period": 0, "reason": "On Balance Volume Flow"},
        {"name": "AD", "timeframe": "1m", "period": 0, "reason": "Chaikin A/D Line"},
        {"name": "ADX_VOL", "timeframe": "1m", "period": 14, "reason": "ADX Volume Overlay"},
        {"name": "CMF", "timeframe": "1m", "period": 20, "reason": "Chaikin Money Flow"},
        {"name": "VWAP", "timeframe": "1m", "period": 0, "reason": "Institutional Average Price Level"},
    ],
    "Patterns": [
        {"name": "CANDLESTICK_PATTERNS", "timeframe": "1m", "period": 0, "reason": "Candlestick Patterns (60+)"},
        {"name": "CHART_PATTERNS", "timeframe": "1m", "period": 0, "reason": "Chart Patterns"},
    ],
    "SupportResistance": [
        {"name": "PIVOT_POINTS", "timeframe": "1m", "period": 0, "reason": "Pivot Points"},
        {"name": "FIBONACCI", "timeframe": "1m", "period": 0, "reason": "Fibonacci Levels"},
        {"name": "DYNAMIC_SR", "timeframe": "1m", "period": 0, "reason": "Dynamic S/R"},
    ]
}

def get_default_indicators(trade_mode: str = "INTRADAY", bias: str = "BULLISH") -> list:
    """
    Selects the 'better' 2 to 3 indicators from the comprehensive pool 
    based on the current market condition (trade_mode and bias) to prevent chart clutter.
    """
    trade_mode = trade_mode.upper() if trade_mode else "INTRADAY"
    bias = bias.upper() if bias else "BULLISH"
    
    indicators = []
    
    if trade_mode == "INTRADAY":
        # Intraday trading heavily relies on volume profile and dynamic support
        indicators.append(ALL_DEFAULT_INDICATORS["Volume"][4]) # VWAP (Overlay)
        
        if bias in ["BULLISH", "BEARISH"]:
            # Directional Intraday: Need trend following, speed, and momentum confirmation
            indicators.append(ALL_DEFAULT_INDICATORS["Trend"][1]) # EMA (Overlay)
            indicators.append(ALL_DEFAULT_INDICATORS["Trend"][3]) # DEMA (Overlay)
            indicators.append(ALL_DEFAULT_INDICATORS["Momentum"][0]) # RSI (Subplot)
            indicators.append(ALL_DEFAULT_INDICATORS["Trend"][5]) # MACD (Subplot)
        else:
            # Sideways/Unclear Intraday: Need mean-reversion and volatility bounds
            indicators.append(ALL_DEFAULT_INDICATORS["Volatility"][1]) # BBANDS (Overlay)
            indicators.append(ALL_DEFAULT_INDICATORS["Trend"][1]) # EMA (Overlay)
            indicators.append(ALL_DEFAULT_INDICATORS["Volatility"][0]) # ATR (Subplot)
            indicators.append(ALL_DEFAULT_INDICATORS["Momentum"][0])   # RSI (Subplot)
    else:
        # DELIVERY (Swing/Position Trading)
        # Swing trading relies on longer-term smoothed trends
        indicators.append(ALL_DEFAULT_INDICATORS["Volume"][4]) # VWAP (Overlay)
        indicators.append(ALL_DEFAULT_INDICATORS["Trend"][0]) # SMA (Overlay)
        
        if bias in ["BULLISH", "BEARISH"]:
            # Directional Swing: Need trailing stop basis and entry timing
            indicators.append(ALL_DEFAULT_INDICATORS["Trend"][1]) # EMA (Overlay)
            indicators.append(ALL_DEFAULT_INDICATORS["Volatility"][0]) # ATR (Subplot)
            indicators.append(ALL_DEFAULT_INDICATORS["Momentum"][0])   # RSI (Subplot)
        else:
            # Sideways Swing: Need bounds and oscillator exhaustion
            indicators.append(ALL_DEFAULT_INDICATORS["Volatility"][1]) # BBANDS (Overlay)
            indicators.append(ALL_DEFAULT_INDICATORS["Trend"][5]) # MACD (Subplot)
            indicators.append(ALL_DEFAULT_INDICATORS["Momentum"][1])   # STOCH (Subplot)

    return indicators

def _market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _extract_v2_fields(plan: dict) -> dict | None:
    """Extract execution fields from V2 schema, with legacy fallback.

    Priority: _v2_execution_decision > execution_decision(dict) > legacy flat fields.
    Returns a dict of validated values if valid for ENTER_NOW, or None.
    """
    if not isinstance(plan, dict):
        return None

    # ── Read V2 execution decision ──
    v2 = plan.get("_v2_execution_decision", {})
    if not v2 and isinstance(plan.get("execution_decision"), dict):
        v2 = plan["execution_decision"]

    action = v2.get("action", "") if v2 else ""
    direction = v2.get("direction", "NONE") if v2 else "NONE"
    trade_mode = v2.get("trade_mode", "NONE") if v2 else "NONE"
    confidence = v2.get("confidence", "LOW") if v2 else "LOW"
    reason = v2.get("reason", "") if v2 else ""

    # ── Read trade plan (V2 direct) ──
    tp = plan.get("trade_plan", {})
    if isinstance(tp, dict) and tp.get("entry_price") is not None:
        entry_val = tp.get("entry_price", 0)
        sl_val = tp.get("stop_loss", 0)
        tgt_val = tp.get("target_price", 0)
        rr_val = tp.get("risk_reward", 0)
    else:
        # Legacy fallback
        ep = plan.get("entry_plan", {}) or {}
        sl = plan.get("stop_loss", {}) or {}
        tg = plan.get("target", {}) or {}
        entry_val = ep.get("entry_price", 0) if isinstance(ep, dict) else 0
        sl_val = sl.get("price", 0) if isinstance(sl, dict) else 0
        tgt_val = tg.get("price", 0) if isinstance(tg, dict) else 0
        rr_val = 0

    # ── Read position sizing (V2 direct) ──
    ps = plan.get("position_sizing", {}) or {}
    quantity = ps.get("quantity", 0) or ps.get("position_size_shares", 0)
    capital_used = ps.get("capital_used", 0) or ps.get("position_size_inr", 0)
    risk_amount = ps.get("risk_amount", 0) or ps.get("max_loss_at_sl", 0)
    capital_pct = ps.get("capital_used_pct", 0)
    if not capital_pct and plan.get("_risk_params", {}).get("total_capital", 0) > 0:
        capital_pct = round((capital_used / plan["_risk_params"]["total_capital"]) * 100, 2)

    # ── Read order payload (V2 direct) ──
    op = plan.get("order_payload", {}) or {}

    try:
        entry_f = float(entry_val) if entry_val else 0
        sl_f = float(sl_val) if sl_val else 0
        tgt_f = float(tgt_val) if tgt_val else 0
        qty_i = int(quantity) if quantity else 0
        rr_f = float(rr_val) if rr_val else 0
    except (TypeError, ValueError):
        entry_f = sl_f = tgt_f = rr_f = 0.0
        qty_i = 0

    return {
        "action": action,
        "direction": direction,
        "trade_mode": trade_mode,
        "confidence": confidence,
        "reason": reason,
        "entry_price": entry_f,
        "stop_loss": sl_f,
        "target_price": tgt_f,
        "risk_reward": rr_f,
        "shares": qty_i,
        "capital_used": capital_used,
        "capital_used_pct": capital_pct,
        "risk_amount": risk_amount,
        "order_payload": op,
        "is_executable": (
            action == "ENTER_NOW"
            and entry_f > 0 and sl_f > 0 and tgt_f > 0
            and qty_i > 0
            and op.get("transaction_type") in ("BUY", "SELL")
        ),
    }


def run_execution_planner(db: Session = None, signal_ids: list = None) -> dict:
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
        query = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.market_date == market_date)
            .filter(db_models.DBTradeSignal.confirmation_status == "confirmed")
            .filter(db_models.DBTradeSignal.execution_status == "pending")
        )
        if signal_ids:
            query = query.filter(db_models.DBTradeSignal.id.in_(signal_ids))
            
        pending_signals = query.order_by(db_models.DBTradeSignal.symbol).all()

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

        # -- Step 2: Fetch risk config from DB for position sizing --
        db_cfg = db.query(db_models.DBSystemConfig).first()
        risk_config = {
            "capital": db_cfg.capital if db_cfg else 100_000.0,
            "max_loss_per_trade_pct": db_cfg.max_loss_per_trade_pct if db_cfg else 1.0,
            "max_capital_per_trade_pct": db_cfg.max_capital_per_trade_pct if db_cfg else 20.0,
            "min_rr": db_cfg.min_rr if db_cfg else 1.5,
            "max_daily_loss_pct": db_cfg.max_daily_loss_pct if db_cfg else 3.0,
        } if db_cfg else {}
        print(f"   [CONFIG] Capital: Rs.{risk_config.get('capital', 0):,.0f} | "
              f"Max loss/trade: {risk_config.get('max_loss_per_trade_pct', 1)}% | "
              f"Max capital/trade: {risk_config.get('max_capital_per_trade_pct', 20)}% | "
              f"Min R:R: {risk_config.get('min_rr', 1.5)}")

        # -- Step 3: Fetch LIVE stock data --
        symbols = list(set(s.symbol for s in pending_signals))
        live_data_map = fetch_stock_data_for_symbols(symbols)

        # -- Step 4: Build tasks (keyed by signal ID, not symbol) -----------
        print(f"\n[STEP 4] Running Gemini Execution Planner ({len(pending_signals)} signals, concurrent)...")
        results = []
        summary = {"planned": 0, "avoided": 0, "skipped": 0}

        # tasks: list of (signal, gemini_input) — preserves per-signal identity
        tasks = []
        for sig in pending_signals:
            live_data = live_data_map.get(sig.symbol)
            if not live_data:
                print(f"      [SKIP] {sig.symbol}: No live data — isolated fetch failure")
                sig.execution_status = "skipped"
                sig.executed_at = _now_ms()
                sig.execution_data = {
                    "action": "AVOID",
                    "execution_decision": "NO TRADE",
                    "why_now_or_why_wait": "No live data available — cannot plan execution.",
                    "_source": "no_data_skip"
                }
                summary["skipped"] += 1
            # --- LOGGING: [PROCESSING SYMBOL] ---
            print(f"\n\n{'#'*60}")
            print(f"  [PROCESSING SYMBOL: {sig.symbol}]")
            print(f"{'#'*60}\n")

            agent2_view = sig.confirmation_data if isinstance(sig.confirmation_data, dict) else {}
            # Pass the new Market Reality Validator schema directly to Agent 3
            agent2_input_view = agent2_view

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
            
            dist_from_vwap_pct = round(((ltp - vwap) / vwap * 100), 2) if vwap else 0
            dist_from_high_pct = round(((high_price - ltp) / ltp * 100), 2) if high_price and ltp else 0
            dist_from_low_pct = round(((ltp - low_price) / low_price * 100), 2) if low_price and ltp else 0
            price_move_pct = round(((ltp - prev_close) / prev_close * 100), 2) if prev_close else 0

            move_quality = "WEAK"
            if open_price and prev_close:
                if gap_pct > 0.3 and ltp < open_price * 0.995: move_quality = "REVERSING"
                elif gap_pct < -0.3 and ltp > open_price * 1.005: move_quality = "REVERSING"
                elif (gap_pct > 0.5 and change_pct < -0.3) or (gap_pct < -0.5 and change_pct > 0.3): move_quality = "FADING"
                elif (gap_pct > 0 and change_pct > 0.2) or (gap_pct < 0 and change_pct < -0.2): move_quality = "STRONG"
                elif abs(change_pct) <= 0.5: move_quality = "HOLDING"

            intraday_structure = "UNCLEAR"
            if ltp >= high_price * 0.998 and change_pct > 0.5: intraday_structure = "BREAKOUT_HIGH"
            elif ltp <= low_price * 1.002 and change_pct < -0.5: intraday_structure = "BREAKDOWN_LOW"
            elif move_quality == "STRONG" and abs(change_pct) > 1.0: intraday_structure = "TRENDING"
            elif move_quality == "FADING": intraday_structure = "PULLBACK"
            elif move_quality == "REVERSING": intraday_structure = "REVERSAL"
            elif move_quality == "HOLDING": intraday_structure = "RANGE"

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

            agent3_input = {
                "symbol": sig.symbol,
                "company_name": sig.symbol,
                "agent2_view": agent2_input_view,
                "live_execution_context": live_execution_context
            }

            # ── Build technical_context from Agent 2's requested_indicators ──
            requested_indicators = agent2_view.get("requested_indicators", [])
            trade_mode = agent2_view.get("trade_mode", sig.trade_mode or "INTRADAY")
            bias = agent2_view.get("direction", "BULLISH")
            
            indicators_to_compute = requested_indicators if requested_indicators else get_default_indicators(trade_mode, bias)
            
            if indicators_to_compute and isinstance(indicators_to_compute, list):
                try:
                    technical_context = build_technical_context(
                        db=db,
                        symbol=sig.symbol,
                        trade_mode=trade_mode,
                        requested_indicators=indicators_to_compute,
                        ltp=ltp,
                    )
                    agent3_input["technical_context"] = technical_context
                except Exception as e:
                    print(f"      [WARN] {sig.symbol}: technical_context build failed: {e}")
                    agent3_input["technical_context"] = {
                        "requested_by_agent2": requested_indicators,
                        "indicator_values": {},
                        "technical_warnings": [f"Technical context build failed: {str(e)}"],
                        "technical_confirmations": [],
                    }

            # ── Generate technical chart image for visual AI analysis ──
            chart_image_bytes = None
            if requested_indicators and isinstance(requested_indicators, list):
                try:
                    chart_image_bytes = generate_technical_chart(
                        symbol=sig.symbol,
                        trade_mode=agent2_view.get("trade_mode", sig.trade_mode or "INTRADAY"),
                        requested_indicators=requested_indicators,
                        ltp=ltp,
                        direction=agent2_view.get("direction"),
                    )
                    if chart_image_bytes:
                        print(f"      [CHART] {sig.symbol}: Chart generated ({len(chart_image_bytes) // 1024}KB)")
                    else:
                        print(f"      [CHART] {sig.symbol}: Chart generation returned empty")
                except Exception as e:
                    print(f"      [WARN] {sig.symbol}: Chart generation failed: {e}")
                    chart_image_bytes = None

            tasks.append((sig, agent3_input, chart_image_bytes))

        # Persist skipped signals before moving to Gemini calls
        db.flush()

        # -- Step 5: Run Gemini calls concurrently & Process results IMMEDIATELY -----
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from agent.paper_trading_engine import auto_create_from_execution, _log_action

        def _execute_one(signal_id: str, symbol: str, inp: dict, chart_bytes: bytes = None):
            """Run Gemini for a single signal. Returns (signal_id, result_dict)."""
            print(f"      [GEMINI] Agent 3 planning {symbol} (sig={signal_id[:12]})...")
            try:
                res = plan_execution(inp, risk_config=risk_config, chart_image_bytes=chart_bytes)
                action = res.get("action", "AVOID").upper()
                exec_dec = res.get("execution_decision", "NO TRADE").upper()
                print(f"      [RESULT] {symbol}: {action} | {exec_dec} | Confidence: {res.get('confidence')}")
                return signal_id, res
            except Exception as e:
                print(f"      [ERROR] {symbol} (sig={signal_id[:12]}): {e}")
                return signal_id, None

        # Map signal IDs to objects for immediate lookups
        sig_map = {t[0].id: t[0] for t in tasks}

        if tasks:
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {
                    pool.submit(_execute_one, t[0].id, t[0].symbol, t[1], t[2] if len(t) > 2 else None): t[0].id
                    for t in tasks
                }
                for future in as_completed(futures):
                    sig_id = futures[future]
                    sig = sig_map.get(sig_id)
                    if not sig: continue

                    try:
                        returned_id, execution_plan = future.result()
                        
                        if not execution_plan:
                            sig.execution_status = "skipped"
                            sig.executed_at = _now_ms()
                            sig.execution_data = {
                                "action": "AVOID",
                                "execution_decision": "NO TRADE",
                                "why_now_or_why_wait": "Gemini call failed or returned no result.",
                                "_source": "gemini_failure"
                            }
                            summary["skipped"] += 1
                            _log_action(db, "Agent 3 (Execution)", sig.symbol, "AVOID",
                                        "Execution skipped: Gemini returned no result",
                                        confidence=0)
                            db.commit()
                            continue

                        # ── Extract V2 fields ─────────────────────────────────────
                        v2 = _extract_v2_fields(execution_plan)
                        v2_action = v2["action"]

                        # Always persist full execution result, merging with existing (e.g. Agent 2.5 data)
                        sig.executed_at = _now_ms()
                        existing_data = sig.execution_data if isinstance(sig.execution_data, dict) else {}
                        existing_data.update(execution_plan)
                        sig.execution_data = existing_data

                        # ── V2 Logging ────────────────────────────────────────────
                        print(f"      [AGENT 3] {sig.symbol}: V2 action={v2_action}")
                        print(f"      [AGENT 3]   trade_mode={v2['trade_mode']} direction={v2['direction']}")
                        if v2_action == "ENTER_NOW":
                            print(f"      [AGENT 3]   entry={v2['entry_price']} sl={v2['stop_loss']} "
                                  f"target={v2['target_price']} rr={v2['risk_reward']}")
                            print(f"      [AGENT 3]   quantity={v2['shares']} capital={v2['capital_used']}")

                        # ── V2 Decision routing ───────────────────────────────────
                        # Legacy compat: read old fields for _log_action confidence
                        old_conf = execution_plan.get("confidence", 0)
                        old_action = execution_plan.get("action", "AVOID")

                        if v2_action == "ENTER_NOW":
                            if not v2["is_executable"]:
                                print(f"      [WARN] {sig.symbol}: ENTER_NOW but not executable "
                                      f"(entry={v2['entry_price']}, sl={v2['stop_loss']}, "
                                      f"target={v2['target_price']}, qty={v2['shares']}) "
                                      f"-- downgrading to skipped")
                                sig.execution_status = "skipped"
                                sig.status = "confirmed"
                                summary["skipped"] += 1
                                _log_action(db, "Agent 3 (Execution)", sig.symbol, old_action,
                                            "Execution skipped: ENTER_NOW with incomplete plan data",
                                            confidence=old_conf)
                            else:
                                sig.execution_status = "planned"
                                sig.status = "planned"
                                sig.signal_type = "BUY" if v2["direction"] == "LONG" else "SELL" if v2["direction"] == "SHORT" else "WATCH"
                                sig.entry_price = v2["entry_price"]
                                sig.stop_loss = v2["stop_loss"]
                                sig.target_price = v2["target_price"]
                                summary["planned"] += 1

                                print(f"      [SIZING] {v2['shares']} shares @ Rs.{v2['entry_price']} "
                                      f"= Rs.{v2['capital_used']:,.0f} ({v2['capital_used_pct']}% of capital)")
                                print(f"      [AGENT 3] paper_trade_created=pending")

                                pt_result = auto_create_from_execution(db, sig)
                                if pt_result and pt_result.get("success"):
                                    print(f"      [PAPER TRADE] Auto-created: {pt_result['trade_id']}")
                                    print(f"      [AGENT 3] paper_trade_created=true")
                                    _log_action(db, "Agent 3 (Execution)", sig.symbol, old_action,
                                                f"Execution planned: ENTER_NOW ({v2['direction']}). "
                                                f"SL: {v2['stop_loss']}, Target: {v2['target_price']}",
                                                confidence=old_conf)
                                elif pt_result and not pt_result.get("success"):
                                    print(f"      [PAPER TRADE] Failed: {pt_result.get('error', 'unknown')}")
                                    print(f"      [AGENT 3] paper_trade_created=false")
                                    sig.execution_status = "skipped"
                                    sig.status = "confirmed"
                                    summary["planned"] -= 1
                                    summary["skipped"] += 1
                                    _log_action(db, "Agent 3 (Execution)", sig.symbol, old_action,
                                                f"Execution skipped: paper trade creation failed",
                                                confidence=old_conf)
                                else:
                                    _log_action(db, "Agent 3 (Execution)", sig.symbol, old_action,
                                                f"Execution planned: ENTER_NOW ({v2['direction']}). "
                                                f"SL: {v2['stop_loss']}, Target: {v2['target_price']}",
                                                confidence=old_conf)

                        elif v2_action in ("WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT"):
                            sig.execution_status = "waiting"
                            sig.status = "confirmed"  # Retryable
                            summary["avoided"] += 1
                            print(f"      [AGENT 3] waiting={v2_action}: {v2['reason']}")
                            _log_action(db, "Agent 3 (Execution)", sig.symbol, "WAIT",
                                        f"Execution waiting: {v2_action} — {v2['reason']}",
                                        confidence=old_conf)

                        elif v2_action == "AVOID":
                            sig.execution_status = "skipped"
                            sig.status = "invalidated"
                            summary["avoided"] += 1
                            print(f"      [AGENT 3] avoided: {v2['reason']}")
                            _log_action(db, "Agent 3 (Execution)", sig.symbol, "AVOID",
                                        f"Execution avoided: {v2['reason']}",
                                        confidence=old_conf)

                        else:
                            # Unknown V2 action — treat as avoided
                            sig.execution_status = "skipped"
                            sig.status = "confirmed"
                            summary["avoided"] += 1
                            _log_action(db, "Agent 3 (Execution)", sig.symbol, old_action,
                                        f"Execution avoided: unrecognized v2 action '{v2_action}'",
                                        confidence=old_conf)

                        results.append({
                            "signal_id": sig.id,
                            "symbol": sig.symbol,
                            "v2_action": v2_action,
                            "direction": v2["direction"],
                            "trade_mode": v2["trade_mode"],
                            "confidence": v2["confidence"],
                            "reason": v2["reason"],
                            # Legacy compat for API consumers
                            "action": old_action,
                            "execution_decision": execution_plan.get("execution_decision", ""),
                        })

                        db.commit()

                    except Exception as e:
                        db.rollback()
                        print(f"      [ERROR] Failed to process execution result for {sig.symbol}: {e}")
                        traceback.print_exc()
                        summary["skipped"] += 1

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


# =========================================================================
# Agent 3 from Live News — called immediately after Live News Agent completes
# =========================================================================

def run_execution_from_live_news(
    symbol: str,
    live_news_output: dict,
    db: Session = None,
    risk_config: dict = None,
) -> dict:
    """
    Trigger Agent 3 (Execution Planner) directly from a Live News Agent result.

    Unlike the standard run_execution_planner() which requires a prior confirmed
    DBTradeSignal, this function works DIRECTLY from the live news analysis output
    and immediately attempts to plan an execution (or reject it).

    Pipeline:
      1. Translate live_news_output -> agent2_view format Agent 3 expects
      2. Fetch live technical data (indicators + chart)
      3. Call plan_execution() with the translated input
      4. If ENTER NOW + valid sizing -> create a paper trade
      5. Return the full execution plan

    Args:
        symbol           : NSE symbol (e.g. "TCS")
        live_news_output : The dict returned by gemini_live_analyzer.analyze_live()
        db               : SQLAlchemy session (creates own if None)
        risk_config      : Risk params dict (fetches from DB if None)

    Returns:
        dict with Agent 3 execution plan + metadata
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    started_at = _now_ms()
    market_date = _market_date_str()

    print(f"\n  [LIVE AGENT -> AGENT 3] Triggering Agent 3 for {symbol}...")

    try:
        # -- Step 1: Build risk_config from DB if not provided --
        if not risk_config:
            db_cfg = db.query(db_models.DBSystemConfig).first()
            risk_config = {
                "capital": db_cfg.capital if db_cfg else 100_000.0,
                "max_loss_per_trade_pct": db_cfg.max_loss_per_trade_pct if db_cfg else 1.0,
                "max_capital_per_trade_pct": db_cfg.max_capital_per_trade_pct if db_cfg else 20.0,
                "min_rr": db_cfg.min_rr if db_cfg else 1.5,
                "max_daily_loss_pct": db_cfg.max_daily_loss_pct if db_cfg else 3.0,
            }

        # -- Step 2: Translate live news output -> agent2_view format --
        bias = live_news_output.get("market_bias", "NEUTRAL")
        should_trade = live_news_output.get("should_trade", False)
        confidence = live_news_output.get("confidence", 0)

        # Map live news bias to Agent 3's expected direction
        direction_map = {
            "BULLISH": "BULLISH",
            "BEARISH": "BEARISH",
            "NEUTRAL": "NEUTRAL",
            "MIXED": "NEUTRAL",
        }
        direction = direction_map.get(bias, "NEUTRAL")

        # Map should_trade to Agent 2's decision field
        # Agent 3 hard-gates on "NO TRADE" so we must set this correctly
        agent2_decision = "TRADE" if should_trade else "NO TRADE"

        agent2_view = {
            "decision": agent2_decision,
            "trade_mode": "INTRADAY",
            "direction": direction,
            "remaining_impact": live_news_output.get("remaining_move_estimate", "UNCLEAR"),
            "priced_in_status": (
                "MOSTLY_PRICED_IN"
                if live_news_output.get("reaction_magnitude_pct", 0) > 2.0
                else "NOT_PRICED_IN"
            ),
            "priority": "HIGH" if confidence >= 70 else "MEDIUM" if confidence >= 50 else "LOW",
            "confidence": confidence,
            "why_tradable_or_not": live_news_output.get("trade_reason", ""),
            "key_confirmations": [live_news_output.get("what_is_confirmed", "")],
            "warning_flags": [live_news_output.get("invalidation_logic", "")],
            "invalid_if": [live_news_output.get("invalidation_logic", "")],
            "final_summary": (
                f"{live_news_output.get('what_happened', '')} | "
                f"Bias: {bias} | "
                f"Market reacted: {live_news_output.get('reaction_magnitude_pct', 0):.1f}%"
            ),
            "trading_thesis": live_news_output.get("trading_thesis", ""),
            "why_news_matters": live_news_output.get("why_news_matters", ""),
            # Source marker so downstream knows this came from live news
            "_source": "live_news_agent",
            "_live_news_confidence": confidence,
        }

        # -- Step 3: Build agent3 input --
        agent3_input = {
            "symbol": symbol,
            "company_name": symbol,
            "agent2_view": agent2_view,
            "live_execution_context": {},   # Will be freshly fetched inside plan_execution()
            "live_news_context": {           # Extra context for Gemini to read
                "what_happened": live_news_output.get("what_happened", ""),
                "why_news_matters": live_news_output.get("why_news_matters", ""),
                "market_bias": bias,
                "trading_thesis": live_news_output.get("trading_thesis", ""),
                "invalidation_logic": live_news_output.get("invalidation_logic", ""),
                "market_reacted": live_news_output.get("market_reacted", False),
                "reaction_magnitude_pct": live_news_output.get("reaction_magnitude_pct", 0),
                "remaining_move_estimate": live_news_output.get("remaining_move_estimate", ""),
                "gemini_confidence": confidence,
            },
            "technical_context": {
                "requested_by_agent2": [],
                "indicator_values": {},
                "technical_warnings": [],
                "technical_confirmations": [],
            },
        }

        # -- Step 4: Optionally build technical indicators --
        try:
            from services.indicator_service import build_technical_context
            from services.chart_generator import generate_technical_chart

            # Fetch fresh LTP for indicator building
            from agent.data_collector import fetch_stock_data_for_symbols
            live_data_map = fetch_stock_data_for_symbols([symbol])
            live_data = live_data_map.get(symbol, {})
            # Note: fetch_stock_data_for_symbols uses 'last_close' as LTP
            ltp = live_data.get("last_close") or live_data.get("ltp", 0)

            if ltp and ltp > 0:
                indicators_to_compute = live_news_output.get("requested_indicators")
                if not indicators_to_compute:
                    bias_condition = live_news_output.get("market_bias", "BULLISH")
                    indicators_to_compute = get_default_indicators("INTRADAY", bias_condition)
                
                try:
                    technical_context = build_technical_context(
                        db=db,
                        symbol=symbol,
                        trade_mode="INTRADAY",
                        requested_indicators=indicators_to_compute,
                        ltp=ltp,
                    )
                    agent3_input["technical_context"] = technical_context
                    print(f"     [TECH] {symbol}: {len(technical_context.get('indicator_values', {}))} indicators")
                except Exception as te:
                    print(f"     [WARN] {symbol}: Technical context failed: {te}")

                # Generate chart
                chart_image_bytes = None
                try:
                    chart_image_bytes = generate_technical_chart(
                        symbol=symbol,
                        trade_mode="INTRADAY",
                        requested_indicators=indicators_to_compute,
                        ltp=ltp,
                        direction=direction,
                    )
                    if chart_image_bytes:
                        print(f"     [CHART] {symbol}: Chart generated ({len(chart_image_bytes) // 1024}KB)")
                except Exception as ce:
                    print(f"     [WARN] {symbol}: Chart failed: {ce}")
                    chart_image_bytes = None
            else:
                chart_image_bytes = None

        except Exception as e:
            print(f"     [WARN] {symbol}: Could not build technical context: {e}")
            chart_image_bytes = None

        # -- Step 5: Call plan_execution() (Agent 3 Gemini prompt) --
        execution_plan = plan_execution(
            input_data=agent3_input,
            risk_config=risk_config,
            chart_image_bytes=chart_image_bytes,
        )

        action = execution_plan.get("action", "AVOID").upper()
        exec_dec = execution_plan.get("execution_decision", "NO TRADE").upper()
        exec_confidence = execution_plan.get("confidence", 0)

        print(
            f"     [AGENT 3 RESULT] {symbol}: {action} | {exec_dec} | "
            f"Confidence: {exec_confidence}"
        )
        print(f"     {execution_plan.get('why_now_or_why_wait', '')}")

        # -- Step 6: Create paper trade if ENTER NOW + valid sizing --
        paper_trade_result = None
        if exec_dec == "ENTER NOW":
            validated = _validate_execution_plan(execution_plan)
            if validated:
                # Create a lightweight synthetic signal so paper trade engine works
                from agent.paper_trading_engine import auto_create_from_execution, _log_action

                # Upsert a synthetic trade signal to serve as the paper trade anchor
                sig_id = f"live-exec-{symbol}-{started_at}"
                existing_sig = db.query(db_models.DBTradeSignal).filter(
                    db_models.DBTradeSignal.id == sig_id
                ).first()

                if not existing_sig:
                    synthetic_signal = db_models.DBTradeSignal(
                        id=sig_id,
                        symbol=symbol,
                        signal_type="BUY" if action == "BUY" else "SELL",
                        trade_mode="INTRADAY",
                        entry_price=validated["entry_price"],
                        stop_loss=validated["stop_loss"],
                        target_price=validated["target_price"],
                        risk_reward=float(validated.get("capital_used_pct", 0)),
                        confidence=float(exec_confidence),
                        reasoning={"source": "live_news_agent", "live_output": live_news_output},
                        news_article_ids=[],
                        stock_snapshot={},
                        generated_at=started_at,
                        market_date=market_date,
                        status="planned",
                        confirmation_status="confirmed",
                        confirmed_at=started_at,
                        confirmation_data=agent2_view,
                        execution_status="planned",
                        executed_at=started_at,
                        execution_data=execution_plan,
                    )
                    db.add(synthetic_signal)
                    db.flush()
                    sig_for_trade = synthetic_signal
                else:
                    existing_sig.execution_data = execution_plan
                    existing_sig.executed_at = started_at
                    sig_for_trade = existing_sig

                paper_trade_result = auto_create_from_execution(db, sig_for_trade)
                db.commit()

                if paper_trade_result and paper_trade_result.get("success"):
                    print(f"     [PAPER TRADE] Created: {paper_trade_result.get('trade_id')}")
                    _log_action(
                        db, "Agent 3 (Live News)", symbol, action,
                        f"Live news triggered ENTER NOW. SL: {validated['stop_loss']}, "
                        f"Target: {validated['target_price']}",
                        confidence=exec_confidence,
                    )
                else:
                    err = paper_trade_result.get("error", "unknown") if paper_trade_result else "None returned"
                    print(f"     [PAPER TRADE] Failed: {err}")
            else:
                print(f"     [AGENT 3] ENTER NOW but plan incomplete — no paper trade created")
        else:
            db.commit()

        duration = _now_ms() - started_at

        return {
            "symbol": symbol,
            "source": "live_news_agent",
            "agent3_triggered": True,
            "action": action,
            "execution_decision": exec_dec,
            "confidence": exec_confidence,
            "why": execution_plan.get("why_now_or_why_wait", ""),
            "final_summary": execution_plan.get("final_summary", ""),
            "paper_trade": paper_trade_result,
            "execution_plan": execution_plan,
            "duration_ms": duration,
        }

    except Exception as e:
        print(f"     [AGENT 3 ERROR] {symbol}: {e}")
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "symbol": symbol,
            "source": "live_news_agent",
            "agent3_triggered": False,
            "error": str(e),
        }
    finally:
        if own_session:
            db.close()

