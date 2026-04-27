"""Agent 2.5 — Technical Analysis Agent (Gemini-powered).

Converts structured OHLCV + indicator time-series into decision-ready
technical intelligence for Agent 3. Does NOT generate trades.
"""

import os
import json
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL")

_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    _client = genai.Client(api_key=GEMINI_API_KEY)

# ── Valid enums ─────────────────────────────────────────────────────────────

VALID_TREND_DIR = {"UP", "DOWN", "SIDEWAYS"}
VALID_STRENGTH = {"STRONG", "MODERATE", "WEAK"}
VALID_MOMENTUM = {"BULLISH", "BEARISH", "NEUTRAL"}
VALID_VOL_STATUS = {"STRONG", "NORMAL", "WEAK"}
VALID_VOL_CONFIRM = {"CONFIRMING", "DIVERGING", "NEUTRAL"}
VALID_VOLATILITY = {"HIGH", "NORMAL", "LOW"}
VALID_SR_STATUS = {"SUPPORT_HOLDING", "RESISTANCE_PRESSURE", "BREAKOUT", "BREAKDOWN", "NEUTRAL"}
VALID_RISK = {"LOW", "MEDIUM", "HIGH"}
VALID_PATTERN_VALIDITY = {"STRONG", "MODERATE", "WEAK", "NONE"}
VALID_STRUCTURE = {"TRENDING", "RANGE_BOUND", "BREAKOUT_SETUP", "REVERSAL_SETUP"}
VALID_QUALITY = {"CLEAN", "MIXED", "NOISY"}
VALID_BIAS = {"BULLISH", "BEARISH", "NEUTRAL"}
VALID_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
VALID_ALIGNMENT = {"ALIGNED", "PARTIAL", "CONTRADICTED"}
VALID_GRADE = {"A", "B", "C", "D"}
VALID_READINESS = {"READY", "WAIT", "AVOID"}
VALID_EXEC_SUPPORT = {"STRONG_SUPPORT", "MODERATE_SUPPORT", "WEAK_SUPPORT", "NO_SUPPORT"}
VALID_TRADE_MODE = {"INTRADAY", "DELIVERY", "BOTH", "AVOID"}
VALID_GO_NOGO = {"GO", "WAIT", "NO_GO"}

FORBIDDEN_FIELDS = {
    "entry_price", "entry", "stop_loss", "stoploss", "stop",
    "target_price", "target", "risk_reward", "rr", "position_size",
    "quantity", "lot_size", "buy", "sell",
}

# ── System Instruction ──────────────────────────────────────────────────────

AGENT25_SYSTEM_INSTRUCTION = """You are Agent 2.5: the Technical Analysis Agent for an Indian equities trading system.

PURPOSE:
Transform time-aligned OHLCV candles and indicator time-series into structured, confluence-based technical interpretation for Agent 3.

You are NOT a trader. You do NOT generate trades, entry/exit/SL/target/position size/BUY/SELL.

CRITICAL DATA RULES:
- Analyze TIME-SERIES, not single values
- Detect direction (rising/falling), strength, acceleration/deceleration, divergence
- NEVER say "RSI above 50 is bullish"
- ALWAYS say "RSI increased from X to Y across N candles indicating momentum build-up"

CONFLUENCE RULE:
Every conclusion MUST be based on MULTIPLE signals where possible.

CANDLE PATTERN RULE:
- Detect patterns from OHLC data
- VALIDATE patterns using indicators, S/R, and trend
- If not validated: validity MUST be WEAK or NONE

SUPPORT/RESISTANCE RULE:
- Evaluate distance to level, level strength, price reaction
- Do NOT assume breakout or rejection without evidence

AGENT 2 ALIGNMENT (STRICT):
- If Agent 2 status = INVALIDATED: technical_bias MUST be NEUTRAL, confidence MUST be LOW, trade_readiness MUST be AVOID
- If Agent 2 status = WEAKENED: confidence MUST NOT be HIGH

You MUST return ONLY valid JSON matching the required schema. No text outside JSON."""


# ── Prompt Template ─────────────────────────────────────────────────────────

AGENT25_PROMPT_TEMPLATE = """Analyze the technical structure for {symbol} on {market_date}.

=== CHART IMAGE ===
A technical chart image has been provided above. Use it to visually confirm or contradict the indicator data below.
Look for: trend direction, candlestick patterns, key price levels, volume bars, MACD/RSI subplot behavior.
Always reference specific chart observations in your reasoning.

=== AGENT 2 VALIDATION CONTEXT ===
{agent2_json}

=== OHLCV CANDLE DATA (time-aligned) ===
{candle_json}

=== INDICATOR TIME-SERIES (TA-Lib computed, time-aligned with candles) ===
{indicator_json}

=== SUPPORT / RESISTANCE LEVELS ===
{sr_json}

=== TASK ===
Evaluate ALL 7 components using time-series behavior (not single snapshots):
1. Trend — direction, strength from MA slopes and price action
2. Momentum — RSI/MACD/Stochastic series behavior
3. Volume — confirmation/divergence vs price move
4. Volatility — ATR/BB behavior and implication
5. Support/Resistance — distance, reaction, strength
6. Candlestick patterns — detect and validate with indicators
7. Chart structure — trending/range/breakout/reversal

Then produce overall assessment with confluence-based reasoning.

=== OUTPUT JSON ===
Return EXACTLY this structure:
{{
  "technical_analysis": {{
    "trend": {{
      "direction": "UP | DOWN | SIDEWAYS",
      "strength": "STRONG | MODERATE | WEAK",
      "based_on": [],
      "reasoning": "",
      "summary": ""
    }},
    "momentum": {{
      "status": "BULLISH | BEARISH | NEUTRAL",
      "strength": "STRONG | MODERATE | WEAK",
      "based_on": [],
      "reasoning": "",
      "summary": ""
    }},
    "volume": {{
      "status": "STRONG | NORMAL | WEAK",
      "confirmation": "CONFIRMING | DIVERGING | NEUTRAL",
      "based_on": [],
      "reasoning": "",
      "summary": ""
    }},
    "volatility": {{
      "status": "HIGH | NORMAL | LOW",
      "implication": "",
      "based_on": [],
      "reasoning": "",
      "summary": ""
    }},
    "support_resistance": {{
      "status": "SUPPORT_HOLDING | RESISTANCE_PRESSURE | BREAKOUT | BREAKDOWN | NEUTRAL",
      "risk": "LOW | MEDIUM | HIGH",
      "key_level": null,
      "reasoning": "",
      "summary": ""
    }},
    "candlestick_patterns": {{
      "detected": [],
      "validity": "STRONG | MODERATE | WEAK | NONE",
      "reasoning": "",
      "summary": ""
    }},
    "chart_structure": {{
      "structure": "TRENDING | RANGE_BOUND | BREAKOUT_SETUP | REVERSAL_SETUP",
      "quality": "CLEAN | MIXED | NOISY",
      "reasoning": "",
      "summary": ""
    }},
    "overall": {{
      "technical_bias": "BULLISH | BEARISH | NEUTRAL",
      "confidence": "LOW | MEDIUM | HIGH",
      "alignment_with_agent_2": "ALIGNED | PARTIAL | CONTRADICTED",
      "technical_grade": "A | B | C | D",
      "trade_readiness": "READY | WAIT | AVOID",
      "execution_support": "STRONG_SUPPORT | MODERATE_SUPPORT | WEAK_SUPPORT | NO_SUPPORT",
      "reasoning": {{
        "why_this_bias": "",
        "why_this_confidence": "",
        "why_this_grade": "",
        "why_ready_wait_or_avoid": "",
        "key_evidence": [],
        "contradictions": []
      }},
      "summary": ""
    }},
    "risks": [],
    "what_agent_3_should_care_about": [],
    "agent_3_handoff": {{
      "technical_decision_context": "",
      "preferred_trade_mode": "INTRADAY | DELIVERY | BOTH | AVOID",
      "technical_go_no_go": "GO | WAIT | NO_GO",
      "go_no_go_reason": "",
      "must_confirm_before_entry": [],
      "major_blockers": [],
      "best_supporting_evidence": [],
      "technical_risk_level": "LOW | MEDIUM | HIGH",
      "risk_reason": ""
    }}
  }}
}}"""


# ── Validator ───────────────────────────────────────────────────────────────

class Agent25ValidationError(ValueError):
    pass


def validate_agent25_output(result: dict, agent2_data: dict) -> dict:
    """Validate Agent 2.5 output against schema and behavioral rules."""
    errors = []

    ta = result.get("technical_analysis")
    if not isinstance(ta, dict):
        raise Agent25ValidationError("missing top-level 'technical_analysis'")

    # Required sections
    for section in ["trend", "momentum", "volume", "volatility",
                    "support_resistance", "candlestick_patterns",
                    "chart_structure", "overall", "agent_3_handoff"]:
        if section not in ta or not isinstance(ta.get(section), dict):
            errors.append(f"missing or invalid section: '{section}'")

    if errors:
        raise Agent25ValidationError("; ".join(errors))

    # Enum validation
    t = ta["trend"]
    if t.get("direction") not in VALID_TREND_DIR:
        errors.append(f"invalid trend.direction: '{t.get('direction')}'")
    if t.get("strength") not in VALID_STRENGTH:
        errors.append(f"invalid trend.strength: '{t.get('strength')}'")

    m = ta["momentum"]
    if m.get("status") not in VALID_MOMENTUM:
        errors.append(f"invalid momentum.status: '{m.get('status')}'")
    if m.get("strength") not in VALID_STRENGTH:
        errors.append(f"invalid momentum.strength: '{m.get('strength')}'")

    v = ta["volume"]
    if v.get("status") not in VALID_VOL_STATUS:
        errors.append(f"invalid volume.status: '{v.get('status')}'")
    if v.get("confirmation") not in VALID_VOL_CONFIRM:
        errors.append(f"invalid volume.confirmation: '{v.get('confirmation')}'")

    vol = ta["volatility"]
    if vol.get("status") not in VALID_VOLATILITY:
        errors.append(f"invalid volatility.status: '{vol.get('status')}'")

    sr = ta["support_resistance"]
    if sr.get("status") not in VALID_SR_STATUS:
        errors.append(f"invalid support_resistance.status: '{sr.get('status')}'")
    if sr.get("risk") not in VALID_RISK:
        errors.append(f"invalid support_resistance.risk: '{sr.get('risk')}'")

    cp = ta["candlestick_patterns"]
    if cp.get("validity") not in VALID_PATTERN_VALIDITY:
        errors.append(f"invalid candlestick_patterns.validity: '{cp.get('validity')}'")

    cs = ta["chart_structure"]
    if cs.get("structure") not in VALID_STRUCTURE:
        errors.append(f"invalid chart_structure.structure: '{cs.get('structure')}'")
    if cs.get("quality") not in VALID_QUALITY:
        errors.append(f"invalid chart_structure.quality: '{cs.get('quality')}'")

    ov = ta["overall"]
    if ov.get("technical_bias") not in VALID_BIAS:
        errors.append(f"invalid overall.technical_bias: '{ov.get('technical_bias')}'")
    if ov.get("confidence") not in VALID_CONFIDENCE:
        errors.append(f"invalid overall.confidence: '{ov.get('confidence')}'")
    if ov.get("alignment_with_agent_2") not in VALID_ALIGNMENT:
        errors.append(f"invalid overall.alignment_with_agent_2")
    if ov.get("technical_grade") not in VALID_GRADE:
        errors.append(f"invalid overall.technical_grade: '{ov.get('technical_grade')}'")
    if ov.get("trade_readiness") not in VALID_READINESS:
        errors.append(f"invalid overall.trade_readiness: '{ov.get('trade_readiness')}'")
    if ov.get("execution_support") not in VALID_EXEC_SUPPORT:
        errors.append(f"invalid overall.execution_support")

    h = ta["agent_3_handoff"]
    if h.get("preferred_trade_mode") not in VALID_TRADE_MODE:
        errors.append(f"invalid agent_3_handoff.preferred_trade_mode")
    if h.get("technical_go_no_go") not in VALID_GO_NOGO:
        errors.append(f"invalid agent_3_handoff.technical_go_no_go")
    if h.get("technical_risk_level") not in VALID_RISK:
        errors.append(f"invalid agent_3_handoff.technical_risk_level")

    # Reasoning completeness
    reasoning = ov.get("reasoning", {})
    for key in ["why_this_bias", "why_this_confidence", "why_this_grade",
                "why_ready_wait_or_avoid", "key_evidence"]:
        val = reasoning.get(key)
        if not val or (isinstance(val, str) and not val.strip()):
            errors.append(f"empty reasoning field: '{key}'")
        if isinstance(val, list) and len(val) == 0 and key == "key_evidence":
            errors.append(f"key_evidence must not be empty")

    # Required lists
    if not isinstance(ta.get("risks"), list):
        errors.append("risks must be a list")
    if not isinstance(ta.get("what_agent_3_should_care_about"), list):
        errors.append("what_agent_3_should_care_about must be a list")

    # based_on must be non-empty lists for classified components
    for comp in ["trend", "momentum", "volume", "volatility"]:
        based = ta[comp].get("based_on")
        if not isinstance(based, list) or len(based) == 0:
            errors.append(f"{comp}.based_on must be a non-empty list")

    # ── Behavioral Rules (Agent 2 alignment) ────────────────────────────
    a2_status = agent2_data.get("validation", {}).get("status", "")

    if a2_status == "INVALIDATED":
        if ov.get("technical_bias") != "NEUTRAL":
            errors.append("Agent 2 INVALIDATED but technical_bias is not NEUTRAL")
        if ov.get("confidence") != "LOW":
            errors.append("Agent 2 INVALIDATED but confidence is not LOW")
        if ov.get("trade_readiness") != "AVOID":
            errors.append("Agent 2 INVALIDATED but trade_readiness is not AVOID")

    if a2_status == "WEAKENED":
        if ov.get("confidence") == "HIGH":
            errors.append("Agent 2 WEAKENED but confidence is HIGH")

    # ── Forbidden execution fields ──────────────────────────────────────
    result_str = json.dumps(result).lower()
    for forbidden in FORBIDDEN_FIELDS:
        if f'"{forbidden}"' in result_str:
            errors.append(f"forbidden execution field detected: '{forbidden}'")

    if errors:
        raise Agent25ValidationError("; ".join(errors))

    return result


# ── Main Entry Point ────────────────────────────────────────────────────────

def analyze_technicals(
    symbol: str,
    market_date: str,
    agent2_data: dict,
    candle_data: list,
    indicator_data: dict,
    sr_levels: dict,
    chart_image_bytes: bytes = None,
) -> dict:
    """
    Use Gemini to produce structured technical analysis.

    Args:
        symbol: Stock symbol
        market_date: YYYY-MM-DD
        agent2_data: Full Agent 2 confirmation output
        candle_data: List of OHLCV candle dicts (time-aligned)
        indicator_data: Dict of indicator name -> time-series values
        sr_levels: Support/resistance levels dict
        chart_image_bytes: Optional PNG bytes of the technical chart.
                           When provided, sent to Gemini as a multimodal image.

    Returns:
        Dict conforming to Agent 2.5 technical analysis output schema.
    """
    if not _client:
        logger.warning("[AGENT 2.5] Gemini unavailable — using fallback for %s", symbol)
        return _fallback_technical_analysis(symbol, agent2_data, candle_data, indicator_data, sr_levels)

    prompt = AGENT25_PROMPT_TEMPLATE.format(
        symbol=symbol,
        market_date=market_date,
        agent2_json=json.dumps(agent2_data, indent=2),
        candle_json=json.dumps(candle_data[-30:], indent=2),  # last 30 candles
        indicator_json=json.dumps(indicator_data, indent=2),
        sr_json=json.dumps(sr_levels, indent=2),
    )

    # Build contents: text prompt + optional chart image
    if chart_image_bytes:
        logger.info("[AGENT 2.5] %s: Sending chart image to Gemini (%d KB)", symbol, len(chart_image_bytes) // 1024)
        contents = [
            types.Part.from_bytes(data=chart_image_bytes, mime_type="image/png"),
            types.Part.from_text(text=prompt),
        ]
    else:
        logger.info("[AGENT 2.5] %s: No chart — sending text-only to Gemini", symbol)
        contents = prompt

    import time as _time
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            response = _client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=AGENT25_SYSTEM_INSTRUCTION,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

            result = json.loads(text)

            try:
                result = validate_agent25_output(result, agent2_data)
            except Agent25ValidationError as ve:
                logger.error("[AGENT 2.5] VALIDATION FAILED for %s: %s", symbol, ve)
                return _fallback_technical_analysis(symbol, agent2_data, candle_data, indicator_data, sr_levels)

            result["_source"] = "gemini_agent25"
            result["_model"] = MODEL_NAME
            return result

        except json.JSONDecodeError as e:
            logger.error("[AGENT 2.5] JSON parse error for %s: %s", symbol, e)
            return _fallback_technical_analysis(symbol, agent2_data, candle_data, indicator_data, sr_levels)
        except Exception as e:
            err_str = str(e)
            is_503 = "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str
            if is_503 and attempt < max_retries:
                wait_sec = 8 * attempt
                logger.warning("[AGENT 2.5] 503 for %s (attempt %d/%d) — retrying in %ds...", symbol, attempt, max_retries, wait_sec)
                _time.sleep(wait_sec)
                continue
            logger.error("[AGENT 2.5] Gemini error for %s: %s", symbol, e)
            return _fallback_technical_analysis(symbol, agent2_data, candle_data, indicator_data, sr_levels)


# ── Fallback (Rule Engine) ──────────────────────────────────────────────────

def _compute_series_trend(values: list) -> str:
    """Classify a numeric series as rising/falling/flat."""
    if not values or len(values) < 3:
        return "flat"
    last3 = values[-3:]
    if last3[2] > last3[1] > last3[0]:
        return "rising"
    elif last3[2] < last3[1] < last3[0]:
        return "falling"
    elif abs(last3[2] - last3[0]) / max(abs(last3[0]), 0.001) < 0.01:
        return "flat"
    return "mixed"


def _fallback_technical_analysis(
    symbol: str,
    agent2_data: dict,
    candle_data: list,
    indicator_data: dict,
    sr_levels: dict,
) -> dict:
    """Conservative rule-based fallback when Gemini is unavailable."""
    a2_status = agent2_data.get("validation", {}).get("status", "WEAKENED")
    a2_mode = agent2_data.get("trade_suitability", {}).get("mode", "AVOID")
    a2_alignment = agent2_data.get("thesis_check", {}).get("alignment", "UNCLEAR")
    a2_bias = agent2_data.get("thesis_check", {}).get("agent_1_bias", "NEUTRAL")

    # Extract indicator series
    rsi_vals = indicator_data.get("RSI", {}).get("last_20", [])
    ema_vals = indicator_data.get("EMA", {}).get("last_20", [])
    macd_vals = indicator_data.get("MACD", {}).get("last_20", [])
    atr_vals = indicator_data.get("ATR", {}).get("last_20", [])
    obv_vals = indicator_data.get("OBV", {}).get("last_20", [])

    # Trend analysis from EMA
    ema_trend = _compute_series_trend(ema_vals)
    trend_dir = "UP" if ema_trend == "rising" else "DOWN" if ema_trend == "falling" else "SIDEWAYS"
    trend_strength = "MODERATE"

    # Momentum from RSI
    rsi_trend = _compute_series_trend(rsi_vals)
    rsi_latest = rsi_vals[-1] if rsi_vals else 50
    if rsi_latest > 60 and rsi_trend == "rising":
        mom_status, mom_strength = "BULLISH", "STRONG"
    elif rsi_latest > 50:
        mom_status, mom_strength = "BULLISH", "MODERATE"
    elif rsi_latest < 40 and rsi_trend == "falling":
        mom_status, mom_strength = "BEARISH", "STRONG"
    elif rsi_latest < 50:
        mom_status, mom_strength = "BEARISH", "MODERATE"
    else:
        mom_status, mom_strength = "NEUTRAL", "WEAK"

    # Volume
    obv_trend = _compute_series_trend(obv_vals)
    vol_status = "NORMAL"
    vol_confirm = "CONFIRMING" if obv_trend == ema_trend and obv_trend != "flat" else "NEUTRAL"

    # Volatility from ATR
    atr_trend = _compute_series_trend(atr_vals)
    vol_stat = "HIGH" if atr_trend == "rising" else "LOW" if atr_trend == "falling" else "NORMAL"

    # S/R
    sr_status = "NEUTRAL"
    sr_risk = "MEDIUM"
    key_level = sr_levels.get("nearest_support") or sr_levels.get("nearest_resistance")

    # Force alignment with Agent 2
    if a2_status == "INVALIDATED":
        tech_bias = "NEUTRAL"
        confidence = "LOW"
        readiness = "AVOID"
        grade = "D"
        go_nogo = "NO_GO"
        exec_support = "NO_SUPPORT"
    elif a2_status == "WEAKENED":
        tech_bias = "NEUTRAL"
        confidence = "LOW"
        readiness = "WAIT"
        grade = "C"
        go_nogo = "WAIT"
        exec_support = "WEAK_SUPPORT"
    else:
        if mom_status == "BULLISH" and trend_dir == "UP":
            tech_bias = "BULLISH"
            confidence = "MEDIUM"
            grade = "B"
        elif mom_status == "BEARISH" and trend_dir == "DOWN":
            tech_bias = "BEARISH"
            confidence = "MEDIUM"
            grade = "B"
        else:
            tech_bias = "NEUTRAL"
            confidence = "LOW"
            grade = "C"
        readiness = "READY" if confidence == "MEDIUM" else "WAIT"
        go_nogo = "GO" if readiness == "READY" else "WAIT"
        exec_support = "MODERATE_SUPPORT" if readiness == "READY" else "WEAK_SUPPORT"

    alignment = "ALIGNED" if a2_alignment in ("ALIGNED", "PARTIAL") else "CONTRADICTED"
    preferred_mode = a2_mode if a2_mode in VALID_TRADE_MODE else "AVOID"

    result = {
        "technical_analysis": {
            "trend": {
                "direction": trend_dir,
                "strength": trend_strength,
                "based_on": ["EMA"],
                "reasoning": f"EMA series trend is {ema_trend} across last 3 data points",
                "summary": f"Trend is {trend_dir} with {trend_strength} strength based on EMA slope"
            },
            "momentum": {
                "status": mom_status,
                "strength": mom_strength,
                "based_on": ["RSI"],
                "reasoning": f"RSI at {rsi_latest:.1f}, trend {rsi_trend}",
                "summary": f"Momentum is {mom_status} ({mom_strength}) — RSI {rsi_latest:.1f} and {rsi_trend}"
            },
            "volume": {
                "status": vol_status,
                "confirmation": vol_confirm,
                "based_on": ["OBV"],
                "reasoning": f"OBV trend is {obv_trend}, price trend is {ema_trend}",
                "summary": f"Volume is {vol_status}, {vol_confirm} price movement"
            },
            "volatility": {
                "status": vol_stat,
                "implication": f"ATR is {atr_trend} — {'wider stops needed' if vol_stat == 'HIGH' else 'normal stop placement'}",
                "based_on": ["ATR"],
                "reasoning": f"ATR series is {atr_trend} over last 3 readings",
                "summary": f"Volatility is {vol_stat} based on ATR behavior"
            },
            "support_resistance": {
                "status": sr_status,
                "risk": sr_risk,
                "key_level": key_level,
                "reasoning": "Evaluated from provided S/R levels",
                "summary": f"S/R status is {sr_status} with {sr_risk} risk"
            },
            "candlestick_patterns": {
                "detected": [],
                "validity": "NONE",
                "reasoning": "Fallback engine does not detect candlestick patterns",
                "summary": "No patterns detected in fallback mode"
            },
            "chart_structure": {
                "structure": "RANGE_BOUND" if trend_dir == "SIDEWAYS" else "TRENDING",
                "quality": "MIXED",
                "reasoning": "Derived from trend direction in fallback mode",
                "summary": f"Chart structure is {'TRENDING' if trend_dir != 'SIDEWAYS' else 'RANGE_BOUND'} with MIXED quality"
            },
            "overall": {
                "technical_bias": tech_bias,
                "confidence": confidence,
                "alignment_with_agent_2": alignment,
                "technical_grade": grade,
                "trade_readiness": readiness,
                "execution_support": exec_support,
                "reasoning": {
                    "why_this_bias": f"Trend {trend_dir} + Momentum {mom_status} + Agent 2 status {a2_status}",
                    "why_this_confidence": f"Agent 2 status is {a2_status}, limited confluence in fallback mode",
                    "why_this_grade": f"Grade {grade} based on {a2_status} status and {confidence} confidence",
                    "why_ready_wait_or_avoid": f"Readiness is {readiness} because Agent 2 status is {a2_status}",
                    "key_evidence": [
                        f"Trend: {trend_dir} ({trend_strength})",
                        f"Momentum: {mom_status} (RSI {rsi_latest:.1f})",
                        f"Agent 2 status: {a2_status}",
                    ],
                    "contradictions": []
                },
                "summary": f"Technical bias is {tech_bias} with {confidence} confidence. Agent 2 {a2_status}."
            },
            "risks": [
                "Fallback rule engine — limited confluence analysis",
                f"Agent 2 status: {a2_status}",
            ],
            "what_agent_3_should_care_about": [
                f"Agent 2 validation: {a2_status}",
                f"Technical bias: {tech_bias} ({confidence})",
                f"Trade readiness: {readiness}",
            ],
            "agent_3_handoff": {
                "technical_decision_context": f"Fallback analysis: {tech_bias} bias, {confidence} confidence, Agent 2 {a2_status}",
                "preferred_trade_mode": preferred_mode,
                "technical_go_no_go": go_nogo,
                "go_no_go_reason": f"Agent 2 {a2_status}, technical confluence is limited in fallback mode",
                "must_confirm_before_entry": ["Verify with live indicators before execution"],
                "major_blockers": [f"Agent 2 status: {a2_status}"] if a2_status != "CONFIRMED" else [],
                "best_supporting_evidence": [f"Trend {trend_dir}", f"RSI {rsi_latest:.1f}"],
                "technical_risk_level": "HIGH" if a2_status == "INVALIDATED" else "MEDIUM",
                "risk_reason": f"Fallback engine with {a2_status} validation"
            }
        },
        "_source": "agent25_fallback",
        "_model": "rule_engine_v1",
    }

    logger.info(
        "[AGENT 2.5] FALLBACK | symbol=%s | bias=%s | confidence=%s | readiness=%s",
        symbol, tech_bias, confidence, readiness,
    )

    return result
