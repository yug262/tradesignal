"""Gemini-powered Market Reality Validator (Agent 2).

Runs at ~9:20 AM IST (5 minutes after NSE market open).
Validates Agent 1's pre-market thesis using real market behavior after open.

Agent 2 answers ONE question:
    "Did the market RESPECT or REJECT the thesis?"

Agent 2 does NOT:
  - generate trades
  - give entry / stop loss / target
  - do position sizing
  - give BUY/SELL

Agent 2 ONLY validates and filters.

TIME CONTEXT:
  - Market opens 9:15 AM IST
  - Agent runs ~9:20 AM (5 min after open)
  - This is HIGH NOISE phase — conservative by default
  - CONFIRMED must be rare; default = WEAKENED
"""

import os
import json
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    _client = genai.Client(api_key=GEMINI_API_KEY)


# ── Enum sets for validation ────────────────────────────────────────────────

VALID_GAP_DIRECTION = {"UP", "DOWN", "FLAT"}
VALID_GAP_STRENGTH = {"STRONG", "MODERATE", "WEAK", "NONE"}
VALID_PRICE_BEHAVIOR = {"HOLDING_STRENGTH", "FADING", "REVERSING", "SIDEWAYS"}
VALID_POSITION_IN_RANGE = {"NEAR_HIGH", "MID_RANGE", "NEAR_LOW"}
VALID_VOLUME_CONFIRMATION = {"STRONG", "NORMAL", "WEAK", "UNKNOWN"}
VALID_RISK_LEVEL = {"LOW", "MEDIUM", "HIGH"}
VALID_ALIGNMENT = {"ALIGNED", "PARTIAL", "CONTRADICTED", "UNCLEAR"}
VALID_STATUS = {"CONFIRMED", "WEAKENED", "INVALIDATED"}
VALID_SIGNAL_QUALITY = {"STRONG", "MIXED", "NOISY"}
VALID_AGENT3_INSTRUCTION = {"PROCEED", "PROCEED_WITH_CAUTION", "DO_NOT_PROCEED"}
VALID_BIAS = {"BULLISH", "BEARISH", "MIXED", "NEUTRAL"}
VALID_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
VALID_TRADE_MODE = {"INTRADAY", "DELIVERY", "BOTH", "AVOID"}
VALID_HOLDING_LOGIC = {"SHORT_INTRADAY_MOVE", "MULTI_DAY_THESIS", "ONLY_IF_CONFIRMED", "NOT_SUITABLE"}
VALID_TIMEFRAME = {"1m", "3m", "5m", "15m", "1h", None}

INDICATOR_UNIVERSE = {
    "trend": {"SMA", "EMA", "WMA", "DEMA", "TEMA", "MACD", "ADX", "AROON", "PARABOLIC_SAR", "ICHIMOKU"},
    "momentum": {"RSI", "STOCHASTIC", "CCI", "ROC", "MOM", "WILLIAMS_R", "MFI"},
    "volatility": {"ATR", "BOLLINGER_BANDS", "KELTNER_CHANNEL", "DONCHIAN_CHANNEL", "NATR"},
    "volume": {"OBV", "AD", "ADOSC", "CMF", "VWAP"},
    "pattern_recognition": {"CANDLESTICK_PATTERNS", "CHART_PATTERNS"},
    "support_resistance": {"PIVOT_POINTS", "FIBONACCI_LEVELS", "DYNAMIC_SUPPORT_RESISTANCE"}
}

ALL_VALID_INDICATORS = set().union(*INDICATOR_UNIVERSE.values())

FORBIDDEN_FIELDS = {
    "entry_price", "entry", "stop_loss", "stoploss", "stop",
    "target_price", "target", "risk_reward", "rr", "position_size",
    "quantity", "lot_size", "buy", "sell",
}


# ── System Instruction ──────────────────────────────────────────────────────

AGENT2_SYSTEM_INSTRUCTION = """You are Agent 2: the 9:20 AM Market Reality Validator for an Indian equities trading system.

PURPOSE:
You validate Agent 1's pre-market thesis using real market behavior after open (~9:20 AM IST).
You answer: Did the market RESPECT or REJECT the thesis?

You are NOT a news discovery agent.
You are NOT an execution agent.
You ONLY validate and filter.

TIME CONTEXT (CRITICAL):
- Market opens at 9:15 AM IST
- You run at ~9:20 AM (5 minutes after open)
- This is HIGH NOISE phase: early volatility, fake breakouts, gap fades
- Be CONSERVATIVE. CONFIRMED must be rare.
- Default state = WEAKENED unless strong evidence exists
- You are an "early rejection detector, not a trend confirmer"

STRICT RULES — You must NOT output:
- entry price
- stop loss
- target
- risk reward
- position size
- BUY/SELL signals

You validate using:
- Gap behavior (direction, strength)
- Price behavior relative to open and previous close
- Position in day's range
- Volume confirmation
- Support/resistance level validation
- Alignment with Agent 1's thesis

TECHNICAL LEVEL RULES:
Support/resistance is used ONLY for validation, NOT for trade creation.

For BULLISH thesis:
- GOOD if price holds above support
- RISK if price is near resistance
- INVALIDATION if price breaks support

For BEARISH thesis:
- GOOD if price stays below resistance
- RISK if price is near support
- INVALIDATION if price breaks resistance

PRIORITY ORDER:
1. Validation (must determine if market respects thesis)
2. Trade Suitability (determine if thesis is viable for trading)
3. Indicator Selection (only if suitable)

Be skeptical and realistic.
Write in clear, direct English.
Respond only with valid JSON matching the required schema."""


# ── Prompt Template ─────────────────────────────────────────────────────────

AGENT2_PROMPT_TEMPLATE = """Validate the market reality for {symbol} on {market_date} at ~9:20 AM IST.

=== INPUT ===
{input_json}

=== TASK ===
Validate Agent 1's pre-market thesis against actual market-open behavior.

Work in this order:

1. GAP AND PRICE BEHAVIOR
- Determine gap direction (UP/DOWN/FLAT) and strength
- Assess current price behavior: HOLDING_STRENGTH, FADING, REVERSING, or SIDEWAYS
- Where is price in day's range? NEAR_HIGH, MID_RANGE, or NEAR_LOW
- Is volume confirming the move?

2. TECHNICAL LEVEL VALIDATION
- Is price above the nearest support? (support_respected)
- Is price below the nearest resistance? (resistance_respected)
- How close is price to resistance? (near_resistance_risk)
- How close is price to support? (near_support_risk)
- Comment on the level context

3. THESIS ALIGNMENT CHECK
Compare Agent 1's expected behavior vs actual:

BULLISH thesis:
- ALIGNED if price holds above previous_close AND near high
- CONTRADICTED if price drops below previous_close OR near low

BEARISH thesis:
- ALIGNED if price stays below previous_close AND near low
- CONTRADICTED if price rises above previous_close OR near high

MIXED/NEUTRAL thesis:
- Mostly UNCLEAR or PARTIAL

4. VALIDATION STATUS
CONFIRMED (rare at 9:20 AM):
- alignment = ALIGNED
- price_behavior = HOLDING_STRENGTH
- no level break (support AND resistance respected)
- volume not WEAK

WEAKENED (default):
- partial alignment
- sideways or fading
- near key levels (risk present)
- noisy behavior

INVALIDATED:
- alignment = CONTRADICTED
- strong reversal
- support/resistance break
- thesis clearly rejected

5. PASSING DECISION & SUITABILITY
should_pass_to_agent_3 = true ONLY if ALL:
- validation.status = CONFIRMED
- alignment = ALIGNED
- NO level break
- Agent 1 confidence != LOW

Otherwise: should_pass_to_agent_3 = false

Logic Matrix:
If INVALIDATED:
  trade_suitability.mode = AVOID
  holding_logic = NOT_SUITABLE
  indicators all empty
  should_pass false
If WEAKENED:
  should_pass false
  mode can be INTRADAY or AVOID only
  never DELIVERY/BOTH
If CONFIRMED:
  mode can be INTRADAY/DELIVERY/BOTH
  indicators selected according to mode

6. INDICATOR UNIVERSE
Select from these if mode is not AVOID (empty arrays if AVOID):
trend: SMA, EMA, WMA, DEMA, TEMA, MACD, ADX, AROON, PARABOLIC_SAR, ICHIMOKU
momentum: RSI, STOCHASTIC, CCI, ROC, MOM, WILLIAMS_R, MFI
volatility: ATR, BOLLINGER_BANDS, KELTNER_CHANNEL, DONCHIAN_CHANNEL, NATR
volume: OBV, AD, ADOSC, CMF, VWAP
pattern_recognition: CANDLESTICK_PATTERNS, CHART_PATTERNS
support_resistance: PIVOT_POINTS, FIBONACCI_LEVELS, DYNAMIC_SUPPORT_RESISTANCE

7. TIMEFRAME & DATA WINDOW
Timeframe is used to fetch candle data from market open to current time.
At ~9:20 AM:
- Only ~5 minutes of current-day data exists

Rules:
INTRADAY:
- primary_timeframe MUST be "1m"
- secondary_timeframe MUST be null
- data_window_minutes ≈ time_since_open
- reason: only 1m has enough candles

DELIVERY:
- primary_timeframe MUST be "1m"
- secondary_timeframe MUST be "15m"
- use_previous_data_for_secondary = true
- reason: combine intraday execution with higher timeframe context

BOTH:
- primary_timeframe = "1m"
- secondary_timeframe = "5m" or "15m"
- use_previous_data_for_secondary = true

AVOID:
- all fields null/zero

IMPORTANT:
- Do NOT assign timeframes that have insufficient candles
- Do NOT use 5m/15m as primary at 9:20
- Always consider available data window

=== OUTPUT FORMAT ===
Return this exact JSON:

{{
  "stock": {{
    "symbol": "{symbol}",
    "company_name": "",
    "exchange": "NSE"
  }},
  "market_behavior": {{
    "gap_direction": "UP | DOWN | FLAT",
    "gap_strength": "STRONG | MODERATE | WEAK | NONE",
    "price_behavior": "HOLDING_STRENGTH | FADING | REVERSING | SIDEWAYS",
    "position_in_range": "NEAR_HIGH | MID_RANGE | NEAR_LOW",
    "volume_confirmation": "STRONG | NORMAL | WEAK | UNKNOWN"
  }},
  "technical_validation": {{
    "support_respected": true,
    "resistance_respected": true,
    "near_resistance_risk": "LOW | MEDIUM | HIGH",
    "near_support_risk": "LOW | MEDIUM | HIGH",
    "level_comment": ""
  }},
  "thesis_check": {{
    "agent_1_bias": "BULLISH | BEARISH | MIXED | NEUTRAL",
    "expected_behavior": [],
    "actual_behavior_summary": "",
    "alignment": "ALIGNED | PARTIAL | CONTRADICTED | UNCLEAR"
  }},
  "validation": {{
    "status": "CONFIRMED | WEAKENED | INVALIDATED",
    "confidence_in_validation": "LOW | MEDIUM | HIGH",
    "reason": "",
    "what_failed": [],
    "what_worked": [],
    "early_signal_quality": "STRONG | MIXED | NOISY"
  }},
  "trade_suitability": {{
    "mode": "INTRADAY | DELIVERY | BOTH | AVOID",
    "reason": "",
    "holding_logic": "SHORT_INTRADAY_MOVE | MULTI_DAY_THESIS | ONLY_IF_CONFIRMED | NOT_SUITABLE"
  }},
  "timeframe_plan": {{
    "primary_timeframe": "1m | 3m | 5m | 15m | 1h | null",
    "secondary_timeframe": "1m | 3m | 5m | 15m | 1h | null",
    "data_window_minutes": 5,
    "use_previous_data_for_secondary": true,
    "reason": ""
  }},
  "indicators_to_check": {{
    "trend": [],
    "momentum": [],
    "volatility": [],
    "volume": [],
    "pattern_recognition": [],
    "support_resistance": []
  }},
  "decision": {{
    "should_pass_to_agent_3": false,
    "pass_reason": "",
    "agent_3_instruction": "PROCEED | PROCEED_WITH_CAUTION | DO_NOT_PROCEED"
  }}
}}"""


# ── Main Entry Point ────────────────────────────────────────────────────────

def confirm_signal_v2(input_data: dict, market_date: str) -> dict:
    """
    Use Gemini (Agent 2) to validate Agent 1's thesis against live market data.

    Args:
        input_data: Dict with stock, agent_1_view, market_data (new schema)
        market_date: Today's date YYYY-MM-DD

    Returns:
        Dict conforming to the Agent 2 Market Reality Validator output schema.
    """
    symbol = input_data.get("stock", {}).get("symbol", "UNKNOWN")

    if not _client:
        logger.warning("[AGENT 2] Gemini unavailable — using fallback for %s", symbol)
        return _fallback_confirmation_v2(input_data)

    prompt = AGENT2_PROMPT_TEMPLATE.format(
        symbol=symbol,
        market_date=market_date,
        input_json=json.dumps(input_data, indent=2),
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=AGENT2_SYSTEM_INSTRUCTION,
                temperature=0.1,
                max_output_tokens=1024,
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

        # Validate output
        try:
            result = validate_agent2_output(result, input_data)
        except Agent2ValidationError as ve:
            logger.error("[AGENT 2] VALIDATION FAILED for %s: %s", symbol, ve)
            logger.warning("[AGENT 2] Falling back to rule engine for %s", symbol)
            return _fallback_confirmation_v2(input_data)

        result["_source"] = "gemini_agent2"
        result["_model"] = MODEL_NAME
        return result

    except json.JSONDecodeError as e:
        logger.error("[AGENT 2] JSON parse error for %s: %s", symbol, e)
        return _fallback_confirmation_v2(input_data)
    except Exception as e:
        logger.error("[AGENT 2] Gemini error for %s: %s", symbol, e)
        return _fallback_confirmation_v2(input_data)


# ── Validator ───────────────────────────────────────────────────────────────

class Agent2ValidationError(ValueError):
    pass


def validate_agent2_output(result: dict, input_data: dict) -> dict:
    """
    Validate Agent 2 output against all schema and behavioral rules.
    Raises Agent2ValidationError on failure. Returns cleaned result on success.
    """
    errors = []

    # 1. Required top-level sections
    for section in ["stock", "market_behavior", "technical_validation",
                     "thesis_check", "validation", "decision",
                     "trade_suitability", "timeframe_plan", "indicators_to_check"]:
        if section not in result or not isinstance(result.get(section), dict):
            errors.append(f"missing or invalid section: '{section}'")

    if errors:
        raise Agent2ValidationError("; ".join(errors))

    # 2. market_behavior enums
    mb = result.get("market_behavior", {})
    if mb.get("gap_direction") not in VALID_GAP_DIRECTION:
        errors.append(f"invalid gap_direction: '{mb.get('gap_direction')}'")
    if mb.get("gap_strength") not in VALID_GAP_STRENGTH:
        errors.append(f"invalid gap_strength: '{mb.get('gap_strength')}'")
    if mb.get("price_behavior") not in VALID_PRICE_BEHAVIOR:
        errors.append(f"invalid price_behavior: '{mb.get('price_behavior')}'")
    if mb.get("position_in_range") not in VALID_POSITION_IN_RANGE:
        errors.append(f"invalid position_in_range: '{mb.get('position_in_range')}'")
    if mb.get("volume_confirmation") not in VALID_VOLUME_CONFIRMATION:
        errors.append(f"invalid volume_confirmation: '{mb.get('volume_confirmation')}'")

    # 3. technical_validation
    tv = result.get("technical_validation", {})
    if not isinstance(tv.get("support_respected"), bool):
        errors.append("support_respected must be boolean")
    if not isinstance(tv.get("resistance_respected"), bool):
        errors.append("resistance_respected must be boolean")
    if tv.get("near_resistance_risk") not in VALID_RISK_LEVEL:
        errors.append(f"invalid near_resistance_risk: '{tv.get('near_resistance_risk')}'")
    if tv.get("near_support_risk") not in VALID_RISK_LEVEL:
        errors.append(f"invalid near_support_risk: '{tv.get('near_support_risk')}'")

    # 4. thesis_check
    tc = result.get("thesis_check", {})
    if tc.get("alignment") not in VALID_ALIGNMENT:
        errors.append(f"invalid alignment: '{tc.get('alignment')}'")
    if tc.get("agent_1_bias") not in VALID_BIAS:
        errors.append(f"invalid agent_1_bias: '{tc.get('agent_1_bias')}'")
    if not isinstance(tc.get("expected_behavior"), list):
        errors.append("expected_behavior must be a list")

    # 5. validation
    val = result.get("validation", {})
    if val.get("status") not in VALID_STATUS:
        errors.append(f"invalid status: '{val.get('status')}'")
    if val.get("early_signal_quality") not in VALID_SIGNAL_QUALITY:
        errors.append(f"invalid early_signal_quality: '{val.get('early_signal_quality')}'")
    if val.get("confidence_in_validation") not in VALID_CONFIDENCE:
        errors.append(f"invalid confidence_in_validation: '{val.get('confidence_in_validation')}'")
    if not isinstance(val.get("what_failed"), list):
        errors.append("what_failed must be a list")
    if not isinstance(val.get("what_worked"), list):
        errors.append("what_worked must be a list")

    # 6. trade_suitability
    ts = result.get("trade_suitability", {})
    if ts.get("mode") not in VALID_TRADE_MODE:
        errors.append(f"invalid mode: '{ts.get('mode')}'")
    if ts.get("holding_logic") not in VALID_HOLDING_LOGIC:
        errors.append(f"invalid holding_logic: '{ts.get('holding_logic')}'")

    # 6.5. timeframe_plan
    tp = result.get("timeframe_plan", {})
    prim = tp.get("primary_timeframe")
    sec = tp.get("secondary_timeframe")
    dw = tp.get("data_window_minutes")
    upd = tp.get("use_previous_data_for_secondary")

    if prim not in VALID_TIMEFRAME:
        errors.append(f"invalid primary_timeframe: '{prim}'")
    if sec not in VALID_TIMEFRAME:
        errors.append(f"invalid secondary_timeframe: '{sec}'")
    if dw is not None and not isinstance(dw, (int, float)):
        errors.append(f"invalid data_window_minutes: '{dw}'")
    if upd is not None and not isinstance(upd, bool):
        errors.append(f"invalid use_previous_data_for_secondary: '{upd}'")

    # 7. indicators_to_check
    inds = result.get("indicators_to_check", {})
    total_inds = []
    for category in ["trend", "momentum", "volatility", "volume", "pattern_recognition", "support_resistance"]:
        if category not in inds or not isinstance(inds[category], list):
            errors.append(f"indicators_to_check missing or invalid category: {category}")
        else:
            for ind in inds[category]:
                if ind not in ALL_VALID_INDICATORS:
                    errors.append(f"indicator '{ind}' outside fixed universe")
                total_inds.append(ind)
    
    if len(total_inds) != len(set(total_inds)):
        errors.append("duplicate indicators found in indicators_to_check")

    # 8. decision
    dec = result.get("decision", {})
    if not isinstance(dec.get("should_pass_to_agent_3"), bool):
        errors.append("should_pass_to_agent_3 must be boolean")
    if dec.get("agent_3_instruction") not in VALID_AGENT3_INSTRUCTION:
        errors.append(f"invalid agent_3_instruction: '{dec.get('agent_3_instruction')}'")

    # 9. Behavioral Rules
    should_pass = dec.get("should_pass_to_agent_3", False)
    status = val.get("status", "")
    alignment = tc.get("alignment", "")
    mode = ts.get("mode", "")
    holding_logic = ts.get("holding_logic", "")
    instruction = dec.get("agent_3_instruction", "")

    a1_confidence = input_data.get("agent_1_view", {}).get("final_confidence", "")

    if status == "INVALIDATED":
        if mode != "AVOID":
            errors.append("status is INVALIDATED but mode is not AVOID")
        if holding_logic != "NOT_SUITABLE":
            errors.append("status is INVALIDATED but holding_logic is not NOT_SUITABLE")
        if len(total_inds) > 0:
            errors.append("status is INVALIDATED but indicators_to_check is not empty")
        if should_pass:
            errors.append("status is INVALIDATED but should_pass is true")

    if status == "WEAKENED":
        if should_pass:
            errors.append("status is WEAKENED but should_pass is true")
        if mode in ("DELIVERY", "BOTH"):
            errors.append("status is WEAKENED but mode is DELIVERY or BOTH")

    if mode == "AVOID" and len(total_inds) > 0:
        errors.append("mode is AVOID but indicators_to_check is not empty")

    if mode == "INTRADAY":
        if prim != "1m":
            errors.append("mode is INTRADAY but primary_timeframe is not 1m")
        if sec is not None:
            errors.append("mode is INTRADAY but secondary_timeframe is not null")
    elif mode == "DELIVERY":
        if prim != "1m":
            errors.append("mode is DELIVERY but primary_timeframe is not 1m")
        if sec != "15m":
            errors.append("mode is DELIVERY but secondary_timeframe is not 15m")
        if upd is not True:
            errors.append("mode is DELIVERY but use_previous_data_for_secondary is not true")
    elif mode == "BOTH":
        if prim != "1m":
            errors.append("mode is BOTH but primary_timeframe is not 1m")
        if sec not in ("5m", "15m"):
            errors.append("mode is BOTH but secondary_timeframe is not 5m or 15m")
        if upd is not True:
            errors.append("mode is BOTH but use_previous_data_for_secondary is not true")
    elif mode == "AVOID":
        if prim is not None or sec is not None:
            errors.append("mode is AVOID but timeframes are not null")

    if should_pass:
        if status != "CONFIRMED":
            errors.append(f"should_pass=true but status='{status}' (must be CONFIRMED)")
        if alignment != "ALIGNED":
            errors.append(f"should_pass=true but alignment='{alignment}' (must be ALIGNED)")
        if a1_confidence == "LOW":
            errors.append("should_pass=true but Agent 1 confidence is LOW")
        if instruction == "DO_NOT_PROCEED":
            errors.append("should_pass=true but agent_3_instruction is DO_NOT_PROCEED")

    # 10. Forbidden execution fields
    result_str = json.dumps(result).lower()
    for forbidden in FORBIDDEN_FIELDS:
        if f'"{forbidden}"' in result_str:
            errors.append(f"forbidden execution field detected: '{forbidden}'")

    if errors:
        raise Agent2ValidationError("; ".join(errors))

    return result


# ── Technical Context Helpers ───────────────────────────────────────────────

def _compute_gap(previous_close: float, open_price: float) -> tuple:
    """Returns (gap_direction, gap_strength, gap_percent)."""
    if not previous_close or previous_close == 0:
        return "FLAT", "NONE", 0.0

    gap_pct = round((open_price - previous_close) / previous_close * 100, 2)

    if abs(gap_pct) < 0.3:
        return "FLAT", "NONE", gap_pct
    direction = "UP" if gap_pct > 0 else "DOWN"
    abs_gap = abs(gap_pct)
    if abs_gap >= 3.0:
        strength = "STRONG"
    elif abs_gap >= 1.0:
        strength = "MODERATE"
    else:
        strength = "WEAK"
    return direction, strength, gap_pct


def _compute_price_behavior(
    previous_close: float, open_price: float, ltp: float,
    day_high: float, day_low: float, gap_pct: float,
) -> tuple:
    """Returns (price_behavior, position_in_range)."""
    if not open_price or not ltp:
        return "SIDEWAYS", "MID_RANGE"

    # Price behavior
    change_from_open = (ltp - open_price) / open_price * 100 if open_price else 0

    if gap_pct > 0.3 and ltp < previous_close:
        behavior = "REVERSING"
    elif gap_pct < -0.3 and ltp > previous_close:
        behavior = "REVERSING"
    elif gap_pct > 0.3 and change_from_open < -0.5:
        behavior = "FADING"
    elif gap_pct < -0.3 and change_from_open > 0.5:
        behavior = "FADING"
    elif abs(change_from_open) < 0.3:
        behavior = "SIDEWAYS"
    elif (gap_pct > 0 and ltp >= open_price) or (gap_pct < 0 and ltp <= open_price):
        behavior = "HOLDING_STRENGTH"
    else:
        behavior = "SIDEWAYS"

    # Position in range
    day_range = day_high - day_low if day_high and day_low else 0
    if day_range > 0:
        position_pct = (ltp - day_low) / day_range
        if position_pct >= 0.7:
            position = "NEAR_HIGH"
        elif position_pct <= 0.3:
            position = "NEAR_LOW"
        else:
            position = "MID_RANGE"
    else:
        position = "MID_RANGE"

    return behavior, position


def _compute_volume_confirmation(volume_ratio: float) -> str:
    """Determine volume confirmation from volume_ratio (current / avg)."""
    if not volume_ratio or volume_ratio <= 0:
        return "UNKNOWN"
    if volume_ratio >= 1.5:
        return "STRONG"
    elif volume_ratio >= 0.8:
        return "NORMAL"
    else:
        return "WEAK"


def _compute_technical_validation(tech_ctx: dict) -> dict:
    """Compute support/resistance validation from technical_context."""
    if not tech_ctx:
        return {
            "support_respected": True,
            "resistance_respected": True,
            "near_resistance_risk": "LOW",
            "near_support_risk": "LOW",
            "level_comment": "No technical levels provided",
        }

    support_respected = bool(tech_ctx.get("price_above_support", True))
    resistance_respected = bool(tech_ctx.get("price_below_resistance", True))

    res_dist = float(tech_ctx.get("resistance_distance_percent", 99))
    sup_dist = float(tech_ctx.get("support_distance_percent", 99))

    if res_dist < 0.5:
        near_res_risk = "HIGH"
    elif res_dist < 1.5:
        near_res_risk = "MEDIUM"
    else:
        near_res_risk = "LOW"

    if sup_dist < 0.5:
        near_sup_risk = "HIGH"
    elif sup_dist < 1.5:
        near_sup_risk = "MEDIUM"
    else:
        near_sup_risk = "LOW"

    comments = []
    if not support_respected:
        comments.append("Price has broken below nearest support")
    if not resistance_respected:
        comments.append("Price has broken above nearest resistance")
    if near_res_risk == "HIGH":
        comments.append(f"Very close to resistance ({res_dist:.1f}%)")
    if near_sup_risk == "HIGH":
        comments.append(f"Very close to support ({sup_dist:.1f}%)")
    if not comments:
        comments.append("Price is within normal range relative to key levels")

    return {
        "support_respected": support_respected,
        "resistance_respected": resistance_respected,
        "near_resistance_risk": near_res_risk,
        "near_support_risk": near_sup_risk,
        "level_comment": "; ".join(comments),
    }


def _compute_alignment(
    bias: str, previous_close: float, ltp: float, position: str,
) -> tuple:
    """Returns (alignment, summary)."""
    if not previous_close or not ltp:
        return "UNCLEAR", "Insufficient price data"

    price_vs_close = "above" if ltp > previous_close else "below" if ltp < previous_close else "at"

    if bias == "BULLISH":
        if ltp > previous_close and position == "NEAR_HIGH":
            return "ALIGNED", f"Price is {price_vs_close} prev close and near day high — bullish thesis holding"
        elif ltp < previous_close or position == "NEAR_LOW":
            return "CONTRADICTED", f"Price is {price_vs_close} prev close and {position} — bullish thesis rejected"
        else:
            return "PARTIAL", f"Price is {price_vs_close} prev close but at {position} — partial bullish confirmation"

    elif bias == "BEARISH":
        if ltp < previous_close and position == "NEAR_LOW":
            return "ALIGNED", f"Price is {price_vs_close} prev close and near day low — bearish thesis holding"
        elif ltp > previous_close or position == "NEAR_HIGH":
            return "CONTRADICTED", f"Price is {price_vs_close} prev close and {position} — bearish thesis rejected"
        else:
            return "PARTIAL", f"Price is {price_vs_close} prev close but at {position} — partial bearish confirmation"

    else:  # MIXED or NEUTRAL
        return "UNCLEAR", f"Thesis is {bias} — price is {price_vs_close} prev close at {position}"


def _compute_validation_status(
    alignment: str, behavior: str, tech_val: dict,
    volume: str, bias: str,
) -> tuple:
    """Returns (status, reason, signal_quality)."""
    support_ok = tech_val.get("support_respected", True)
    resistance_ok = tech_val.get("resistance_respected", True)
    near_res = tech_val.get("near_resistance_risk", "LOW")
    near_sup = tech_val.get("near_support_risk", "LOW")

    # INVALIDATED checks
    if alignment == "CONTRADICTED":
        return "INVALIDATED", "Thesis clearly contradicted by market behavior", "NOISY"
    if behavior == "REVERSING":
        return "INVALIDATED", "Price is reversing against the thesis direction", "NOISY"
    if bias == "BULLISH" and not support_ok:
        return "INVALIDATED", "Bullish thesis invalidated — price broke below support", "NOISY"
    if bias == "BEARISH" and not resistance_ok:
        return "INVALIDATED", "Bearish thesis invalidated — price broke above resistance", "NOISY"

    # CONFIRMED checks (rare at 9:20 AM)
    if (alignment == "ALIGNED"
            and behavior == "HOLDING_STRENGTH"
            and support_ok and resistance_ok
            and volume != "WEAK"):
        # Extra conservatism: if near key levels, downgrade
        if (bias == "BULLISH" and near_res == "HIGH") or (bias == "BEARISH" and near_sup == "HIGH"):
            return "WEAKENED", "Thesis aligned but price is near a key level — too early to confirm", "MIXED"
        return "CONFIRMED", "Thesis aligned, price holding strength, levels respected, volume not weak", "STRONG"

    # Everything else = WEAKENED
    reasons = []
    if alignment == "PARTIAL":
        reasons.append("partial alignment only")
    if alignment == "UNCLEAR":
        reasons.append("thesis alignment unclear")
    if behavior in ("FADING", "SIDEWAYS"):
        reasons.append(f"price behavior is {behavior}")
    if near_res in ("HIGH", "MEDIUM") or near_sup in ("HIGH", "MEDIUM"):
        reasons.append("near key technical levels")
    if volume == "WEAK":
        reasons.append("weak volume")
    if volume == "UNKNOWN":
        reasons.append("volume data unavailable")

    reason = "Early market phase — " + (", ".join(reasons) if reasons else "insufficient confirmation")
    quality = "MIXED" if alignment == "PARTIAL" else "NOISY"
    return "WEAKENED", reason, quality

def _empty_indicators():
    return {
        "trend": [],
        "momentum": [],
        "volatility": [],
        "volume": [],
        "pattern_recognition": [],
        "support_resistance": []
    }

def _select_indicators(mode: str, status: str) -> dict:
    if mode == "AVOID" or status == "INVALIDATED":
        return _empty_indicators()
    if mode == "INTRADAY":
        return {
            "trend": ["EMA", "MACD", "PARABOLIC_SAR"],
            "momentum": ["RSI", "STOCHASTIC", "MFI"],
            "volatility": ["ATR", "BOLLINGER_BANDS"],
            "volume": ["VWAP", "OBV", "CMF"],
            "pattern_recognition": ["CANDLESTICK_PATTERNS"],
            "support_resistance": ["PIVOT_POINTS", "DYNAMIC_SUPPORT_RESISTANCE"]
        }
    if mode == "DELIVERY":
        return {
            "trend": ["SMA", "EMA", "ADX", "ICHIMOKU", "MACD"],
            "momentum": ["RSI", "ROC", "MFI"],
            "volatility": ["ATR", "BOLLINGER_BANDS", "NATR"],
            "volume": ["OBV", "CMF", "AD"],
            "pattern_recognition": ["CHART_PATTERNS"],
            "support_resistance": ["FIBONACCI_LEVELS", "DYNAMIC_SUPPORT_RESISTANCE"]
        }
    # BOTH
    return {
        "trend": ["EMA", "SMA", "MACD", "ADX"],
        "momentum": ["RSI", "MFI"],
        "volatility": ["ATR", "BOLLINGER_BANDS"],
        "volume": ["VWAP", "OBV", "CMF"],
        "pattern_recognition": ["CANDLESTICK_PATTERNS", "CHART_PATTERNS"],
        "support_resistance": ["PIVOT_POINTS", "FIBONACCI_LEVELS", "DYNAMIC_SUPPORT_RESISTANCE"]
    }

def _select_trade_suitability(status: str, alignment: str, bias: str, confidence: str, behavior: str, volume: str, tech_val: dict, agent_1_view: dict) -> dict:
    if status == "INVALIDATED":
        return {
            "mode": "AVOID",
            "reason": "Thesis invalidated by price action",
            "holding_logic": "NOT_SUITABLE"
        }
    if status == "WEAKENED":
        return {
            "mode": "INTRADAY",
            "reason": "Thesis weakened, short intraday scalp only if confirmed",
            "holding_logic": "SHORT_INTRADAY_MOVE"
        }
    # CONFIRMED
    return {
        "mode": "BOTH",
        "reason": "Thesis confirmed, suitable for intraday and swing",
        "holding_logic": "ONLY_IF_CONFIRMED"
    }

def _select_timeframe_plan(mode: str) -> dict:
    if mode == "INTRADAY":
        return {
            "primary_timeframe": "1m",
            "secondary_timeframe": None,
            "data_window_minutes": 5,
            "use_previous_data_for_secondary": False,
            "reason": "Early market + limited data"
        }
    elif mode == "DELIVERY":
        return {
            "primary_timeframe": "1m",
            "secondary_timeframe": "15m",
            "data_window_minutes": 5,
            "use_previous_data_for_secondary": True,
            "reason": "Combine intraday execution with higher timeframe context"
        }
    elif mode == "BOTH":
        return {
            "primary_timeframe": "1m",
            "secondary_timeframe": "15m",
            "data_window_minutes": 5,
            "use_previous_data_for_secondary": True,
            "reason": "Multi-timeframe confirmation"
        }
    else:
        return {
            "primary_timeframe": None,
            "secondary_timeframe": None,
            "data_window_minutes": 0,
            "use_previous_data_for_secondary": False,
            "reason": "Not suitable for trading"
        }

# ── Fallback (Rule Engine) ──────────────────────────────────────────────────

def _fallback_confirmation_v2(input_data: dict) -> dict:
    """
    Conservative rule-based fallback for Agent 2 when Gemini is unavailable.
    Uses the new input schema with technical_context support.
    """
    stock = input_data.get("stock", {})
    symbol = stock.get("symbol", "UNKNOWN")
    a1_view = input_data.get("agent_1_view", {})
    market = input_data.get("market_data", {})
    tech_ctx = market.get("technical_context", {})

    bias = a1_view.get("final_bias", "NEUTRAL")
    confidence = a1_view.get("final_confidence", "LOW")
    prev_close = float(market.get("previous_close", 0) or 0)
    open_price = float(market.get("open_price", 0) or 0)
    ltp = float(market.get("ltp", 0) or 0)
    day_high = float(market.get("day_high", 0) or 0)
    day_low = float(market.get("day_low", 0) or 0)
    volume_ratio = float(market.get("volume_ratio", 0) or 0)

    # Compute all components
    gap_dir, gap_str, gap_pct = _compute_gap(prev_close, open_price)
    behavior, position = _compute_price_behavior(
        prev_close, open_price, ltp, day_high, day_low, gap_pct,
    )
    vol_conf = _compute_volume_confirmation(volume_ratio)
    tech_val = _compute_technical_validation(tech_ctx)
    alignment, behavior_summary = _compute_alignment(bias, prev_close, ltp, position)
    status, reason, signal_quality = _compute_validation_status(
        alignment, behavior, tech_val, vol_conf, bias,
    )

    # Compute new logic
    suitability = _select_trade_suitability(status, alignment, bias, confidence, behavior, vol_conf, tech_val, a1_view)
    indicators = _select_indicators(suitability["mode"], status)
    timeframe_plan = _select_timeframe_plan(suitability["mode"])

    # Passing decision
    should_pass = (
        status == "CONFIRMED"
        and alignment == "ALIGNED"
        and tech_val["support_respected"]
        and tech_val["resistance_respected"]
        and confidence != "LOW"
    )

    if should_pass:
        pass_reason = "Thesis confirmed with aligned price action, respected levels, and adequate volume"
        a3_instruction = "PROCEED_WITH_CAUTION"
    elif status == "INVALIDATED":
        pass_reason = f"Thesis invalidated: {reason}"
        a3_instruction = "DO_NOT_PROCEED"
    else:
        pass_reason = f"Thesis weakened at 9:20 AM: {reason}"
        a3_instruction = "DO_NOT_PROCEED"

    result = {
        "stock": {
            "symbol": symbol,
            "company_name": stock.get("company_name", ""),
            "exchange": stock.get("exchange", "NSE"),
        },
        "market_behavior": {
            "gap_direction": gap_dir,
            "gap_strength": gap_str,
            "price_behavior": behavior,
            "position_in_range": position,
            "volume_confirmation": vol_conf,
        },
        "technical_validation": tech_val,
        "thesis_check": {
            "agent_1_bias": bias,
            "expected_behavior": [],
            "actual_behavior_summary": behavior_summary,
            "alignment": alignment,
        },
        "validation": {
            "status": status,
            "confidence_in_validation": "HIGH" if status in ("CONFIRMED", "INVALIDATED") else "MEDIUM",
            "reason": reason,
            "what_failed": [reason] if status != "CONFIRMED" else [],
            "what_worked": ["Levels respected"] if status == "CONFIRMED" else [],
            "early_signal_quality": signal_quality,
        },
        "trade_suitability": suitability,
        "timeframe_plan": timeframe_plan,
        "indicators_to_check": indicators,
        "decision": {
            "should_pass_to_agent_3": should_pass,
            "pass_reason": pass_reason,
            "agent_3_instruction": a3_instruction,
        },
        "_source": "agent2_fallback",
        "_model": "rule_engine_v2",
    }

    logger.info(
        "[AGENT 2] FALLBACK | symbol=%s | status=%s | alignment=%s | pass=%s",
        symbol, status, alignment, should_pass,
    )
    logger.info(
        "[AGENT 2] SUITABILITY | mode=%s | holding_logic=%s",
        suitability["mode"], suitability["holding_logic"]
    )
    logger.info(
        "[AGENT 2] INDICATORS | trend=%s | momentum=%s | volatility=%s | volume=%s | patterns=%s | sr=%s",
        indicators["trend"], indicators["momentum"], indicators["volatility"],
        indicators["volume"], indicators["pattern_recognition"], indicators["support_resistance"]
    )

    return result