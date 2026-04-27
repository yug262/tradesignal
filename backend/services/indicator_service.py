"""Indicator Service — bridges Agent 2's requested_indicators to Agent 3's technical_context.

This module:
1. Reads Agent 2's requested_indicators from confirmation_data
2. Calls fetch_indicator_data for each requested indicator
3. Interprets raw indicator values into human-readable signals
4. Builds a structured technical_context dict for Agent 3

Agent 3 uses technical_context ONLY for execution validation:
- Confirm exhaustion (RSI overbought/oversold)
- Confirm trend alignment (EMA/SMA direction)
- Estimate volatility (ATR)
- Confirm momentum (MACD)

Indicators must NEVER override Agent 2's decision or risk limits.
"""

import time
from sqlalchemy.orm import Session
from agent.data_collector import fetch_indicator_data


# ═══════════════════════════════════════════════════════════════════════════════
# INDICATOR INTERPRETATION
# ═══════════════════════════════════════════════════════════════════════════════

def interpret_indicator(name: str, values: list, ltp: float = None) -> dict:
    """
    Interpret raw indicator values into actionable signals for Agent 3.

    Args:
        name: Indicator name (RSI, EMA, SMA, MACD, ATR, BBANDS, CCI, WILLR, etc.)
        values: List of recent indicator values (chronological order, last = latest)
        ltp: Latest traded price (optional, used for EMA/SMA comparison)

    Returns:
        Dict with: latest, trend, interpretation, detail, valid, warning
    """
    if not values or len(values) == 0:
        return {
            "latest": None,
            "trend": "unavailable",
            "interpretation": "no data",
            "detail": "Indicator data not available",
            "valid": False,
            "warning": "No data returned from TA-Lib"
        }

    latest = round(values[-1], 4)
    name_upper = name.upper()

    # Determine trend from last 3 values
    trend = _compute_trend(values)

    interpretation = "neutral"
    detail = ""
    valid = True
    warning = None

    # ── RSI ──────────────────────────────────────────────────────────────
    if name_upper == "RSI":
        # RSI must be between 0 and 100
        if latest < 0 or latest > 100:
            valid = False
            warning = f"RSI value {latest} out of bounds (0-100)"
        
        if latest > 70:
            interpretation = "overbought"
            detail = f"RSI at {latest:.1f} — overbought territory, potential exhaustion"
        elif latest < 30:
            interpretation = "oversold"
            detail = f"RSI at {latest:.1f} — oversold territory, potential bounce"
        elif latest > 60:
            interpretation = "bullish"
            detail = f"RSI at {latest:.1f} — above midline, bullish bias"
        elif latest < 40:
            interpretation = "bearish"
            detail = f"RSI at {latest:.1f} — below midline, bearish bias"
        else:
            interpretation = "neutral"
            detail = f"RSI at {latest:.1f} — neutral zone"

        if trend in ("rising", "falling"):
            detail += f" | {trend}"

    # ── EMA / SMA / WMA ─────────────────────────────────────────────────
    elif name_upper in ("EMA", "SMA", "WMA"):
        # Moving average must be reasonably close to LTP
        if ltp is not None and latest > 0:
            pct_diff = abs(latest - ltp) / ltp
            if pct_diff > 0.25:
                valid = False
                warning = f"{name_upper} {latest} is too far from LTP {ltp} ({pct_diff*100:.1f}%)"
            
            pct_from_ma = round(((ltp - latest) / latest) * 100, 2)
            if ltp > latest:
                interpretation = "price_above_ma"
                detail = f"LTP Rs.{ltp:.2f} is {pct_from_ma:.2f}% above {name_upper} {latest:.2f}"
            elif ltp < latest:
                interpretation = "price_below_ma"
                detail = f"LTP Rs.{ltp:.2f} is {abs(pct_from_ma):.2f}% below {name_upper} {latest:.2f}"
            else:
                interpretation = "at_ma"
                detail = f"LTP at {name_upper} level {latest:.2f}"
        else:
            detail = f"{name_upper} at {latest:.2f}"

        if trend in ("rising", "falling"):
            interpretation = f"{interpretation}_{trend}" if interpretation != "neutral" else trend
            detail += f" | MA is {trend}"

    # ── MACD ─────────────────────────────────────────────────────────────
    elif name_upper == "MACD":
        if latest > 0:
            interpretation = "bullish_momentum"
            detail = f"MACD at {latest:.4f} — above zero, bullish momentum"
        elif latest < 0:
            interpretation = "bearish_momentum"
            detail = f"MACD at {latest:.4f} — below zero, bearish momentum"
        else:
            interpretation = "neutral"
            detail = f"MACD at {latest:.4f} — at zero line"

        if trend in ("rising", "falling"):
            detail += f" | momentum is {trend}"

    # ── ATR / NATR / TRANGE ──────────────────────────────────────────────
    elif name_upper in ("ATR", "NATR", "TRANGE"):
        # ATR should be positive and usually < 20% of LTP
        if latest <= 0:
            valid = False
            warning = f"{name_upper} must be positive, got {latest}"
        elif ltp is not None and latest > (ltp * 0.20):
             valid = False
             warning = f"{name_upper} {latest} is unusually high (>20% of LTP)"

        if trend == "rising":
            interpretation = "volatility_expanding"
            detail = f"{name_upper} at {latest:.2f} — volatility expanding"
        elif trend == "falling":
            interpretation = "volatility_cooling"
            detail = f"{name_upper} at {latest:.2f} — volatility cooling"
        else:
            interpretation = "volatility_stable"
            detail = f"{name_upper} at {latest:.2f} — volatility stable"

    # ── BBANDS (middle band) ─────────────────────────────────────────────
    elif name_upper == "BBANDS":
        # BBANDS middle should be near LTP
        if ltp is not None and latest > 0:
            pct_diff = abs(latest - ltp) / ltp
            if pct_diff > 0.25:
                valid = False
                warning = f"BBANDS {latest} is too far from LTP {ltp}"

            if ltp > latest:
                interpretation = "above_middle_band"
                detail = f"LTP Rs.{ltp:.2f} above Bollinger middle band {latest:.2f}"
            elif ltp < latest:
                interpretation = "below_middle_band"
                detail = f"LTP Rs.{ltp:.2f} below Bollinger middle band {latest:.2f}"
            else:
                interpretation = "at_middle_band"
                detail = f"LTP at Bollinger middle band {latest:.2f}"
        else:
            interpretation = "available_but_limited"
            detail = f"Bollinger middle band at {latest:.2f}"

    # ── CCI ──────────────────────────────────────────────────────────────
    elif name_upper == "CCI":
        if latest > 100:
            interpretation = "overbought"
            detail = f"CCI at {latest:.1f} — overbought"
        elif latest < -100:
            interpretation = "oversold"
            detail = f"CCI at {latest:.1f} — oversold"
        else:
            interpretation = "neutral"
            detail = f"CCI at {latest:.1f} — neutral range"

    # ── WILLR (Williams %R) ──────────────────────────────────────────────
    elif name_upper == "WILLR":
        if latest > -20:
            interpretation = "overbought"
            detail = f"Williams %R at {latest:.1f} — overbought zone"
        elif latest < -80:
            interpretation = "oversold"
            detail = f"Williams %R at {latest:.1f} — oversold zone"
        else:
            interpretation = "neutral"
            detail = f"Williams %R at {latest:.1f} — neutral zone"

    # ── MOM / ROC / TRIX ─────────────────────────────────────────────────
    elif name_upper in ("MOM", "ROC", "TRIX"):
        if latest > 0:
            interpretation = "positive_momentum"
        elif latest < 0:
            interpretation = "negative_momentum"
        else:
            interpretation = "neutral"
        detail = f"{name_upper} at {latest:.4f} | trend: {trend}"

    # ── Unknown indicator ────────────────────────────────────────────────
    else:
        detail = f"{name_upper} at {latest:.4f} | trend: {trend}"

    return {
        "latest": latest,
        "trend": trend,
        "interpretation": interpretation if valid else "unavailable",
        "detail": detail,
        "valid": valid,
        "warning": warning
    }


def _compute_trend(values: list) -> str:
    """Determine rising/falling/flat from the last 3 data points."""
    if len(values) < 3:
        return "insufficient_data"

    last3 = values[-3:]
    if last3[2] > last3[1] > last3[0]:
        return "rising"
    elif last3[2] < last3[1] < last3[0]:
        return "falling"
    elif abs(last3[2] - last3[0]) / max(abs(last3[0]), 0.001) < 0.01:
        return "flat"
    else:
        return "mixed"


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD TECHNICAL CONTEXT FOR AGENT 3
# ═══════════════════════════════════════════════════════════════════════════════

def build_technical_context(
    db: Session,
    symbol: str,
    trade_mode: str,
    requested_indicators: list,
    ltp: float = None
) -> dict:
    """
    Build structured technical_context for Agent 3 from Agent 2's requested_indicators.

    This function:
    1. Iterates over requested_indicators from Agent 2
    2. Fetches each indicator via TA-Lib (or returns empty safely)
    3. Interprets each indicator
    4. Generates warnings and confirmations

    Args:
        db: SQLAlchemy session
        symbol: Stock symbol
        trade_mode: INTRADAY or DELIVERY
        requested_indicators: List of dicts with {name, timeframe, reason}
        ltp: Current LTP for price-vs-MA comparisons

    Returns:
        {
            "requested_by_agent2": [...],
            "indicator_values": { "RSI_1m": {...}, ... },
            "technical_warnings": [...],
            "technical_confirmations": [...]
        }
    """
    if not requested_indicators:
        return {
            "requested_by_agent2": [],
            "indicator_values": {},
            "technical_warnings": [],
            "technical_confirmations": [],
        }

    # Cap at 12 indicators to support rich user defaults
    indicators_to_process = requested_indicators[:12]

    indicator_values = {}
    technical_warnings = []
    technical_confirmations = []

    print(f"\n   [TECH CONTEXT] Building technical context for {symbol} ({len(indicators_to_process)} indicators)...")

    # Step 1: Process each requested indicator
    for req in indicators_to_process:
        ind_name = str(req.get("name", "")).upper().strip()
        ind_tf = str(req.get("timeframe", "")).strip()
        ind_reason = str(req.get("reason", "")).strip()
        key = f"{ind_name}_{ind_tf}" if ind_tf else ind_name

        try:
            # A. Fetch raw indicator data (with price-scale check)
            raw_data = fetch_indicator_data(
                db=db,
                symbol=symbol,
                trade_mode=trade_mode,
                indicator_name=ind_name,
                timeframe=ind_tf if ind_tf else None,
                ltp=ltp
            )

            if not raw_data:
                indicator_values[key] = {
                    "latest": None,
                    "last_20": [],
                    "interpretation": "unavailable",
                    "detail": f"No valid data returned for {ind_name}",
                    "valid": False,
                    "reason_requested": ind_reason,
                }
                technical_warnings.append(f"{key}: data unavailable or failed price-scale check")
                continue

            # B. Extract values and interpret
            vals = [point["value"] for point in raw_data]
            interp = interpret_indicator(ind_name, vals, ltp=ltp)

            # C. Store structured output
            indicator_values[key] = {
                "latest": interp["latest"],
                "last_20": [round(v, 4) for v in vals[-20:]],
                "interpretation": interp["interpretation"],
                "trend": interp["trend"],
                "detail": interp["detail"],
                "valid": interp["valid"],
                "warning": interp["warning"],
                "reason_requested": ind_reason,
            }

            # D. Classify into global confirmations/warnings (ONLY if valid)
            if interp["valid"]:
                _classify_signal(key, interp, technical_warnings, technical_confirmations)
                print(f"      [{key}] latest={interp['latest']} | {interp['interpretation']} | {interp['trend']}")
            else:
                technical_warnings.append(f"{key}: {interp['warning']}")
                # print(f"      [{key}] INVALID: {interp['warning']}") # Replaced by summary

        except Exception as e:
            print(f"\n==============================")
            print(f"[ERROR]")
            print(f"==============================")
            print(f"stage: Technical Context / {req.get('name')}")
            print(f"error: {str(e)}")
            print(f"==============================\n")
            
            indicator_values[key] = {
                "latest": None,
                "last_20": [],
                "interpretation": "error",
                "detail": f"Processing error: {str(e)}",
                "valid": False,
                "reason_requested": ind_reason,
            }
            technical_warnings.append(f"{key}: processing error")

    # --- LOGGING: [TECHNICAL CONTEXT] ---
    print(f"==============================")
    print(f"[TECHNICAL CONTEXT]")
    print(f"==============================")
    for k, v in indicator_values.items():
        if v.get("valid"):
            print(f"{k} -> {v.get('latest')} ({v.get('interpretation')})")
        else:
            print(f"{k} -> INVALID ({v.get('interpretation')})")
            
    if technical_confirmations:
        print(f"\nConfirmations:")
        for c in technical_confirmations:
            print(f" - {c}")
    
    if technical_warnings:
        print(f"\nWarnings:")
        for w in technical_warnings:
            print(f" - {w}")
    print(f"==============================\n")

    return {
        "requested_by_agent2": indicators_to_process,
        "indicator_values": indicator_values,
        "technical_warnings": technical_warnings,
        "technical_confirmations": technical_confirmations,
    }


def _classify_signal(key: str, interp: dict, warnings: list, confirmations: list):
    """Classify an indicator interpretation as a warning or confirmation."""
    interpretation = interp.get("interpretation", "")

    # Warnings — conditions that suggest caution
    WARNING_SIGNALS = {
        "overbought": f"{key}: overbought — potential exhaustion risk",
        "oversold": f"{key}: oversold — potential bounce risk for shorts",
        "volatility_expanding": f"{key}: volatility expanding — wider stops may be needed",
        "bearish_momentum": f"{key}: bearish momentum — caution for long entries",
        "price_below_ma": f"{key}: price below moving average",
        "below_middle_band": f"{key}: price below Bollinger middle band",
        "negative_momentum": f"{key}: negative momentum",
    }

    # Confirmations — conditions that support execution
    CONFIRM_SIGNALS = {
        "bullish": f"{key}: bullish bias confirmed",
        "bullish_momentum": f"{key}: bullish momentum confirmed",
        "price_above_ma": f"{key}: price above moving average",
        "price_above_ma_rising": f"{key}: price above rising moving average — strong trend",
        "volatility_cooling": f"{key}: volatility cooling — tighter stops feasible",
        "above_middle_band": f"{key}: price above Bollinger middle band",
        "positive_momentum": f"{key}: positive momentum",
    }

    if interpretation in WARNING_SIGNALS:
        warnings.append(WARNING_SIGNALS[interpretation])
    elif interpretation in CONFIRM_SIGNALS:
        confirmations.append(CONFIRM_SIGNALS[interpretation])
