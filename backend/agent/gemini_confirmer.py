"""Gemini-powered Market Open Confirmation Agent (Agent 2).

Validates Agent 1's pre-market signals against LIVE market-open data (9:15-9:20 AM).
Uses a structured multi-dimensional input (News, Agent 1 View, Market Context)
to produce a high-precision confirmation verdict.
"""

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Create client
_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    _client = genai.Client(api_key=GEMINI_API_KEY)


AGENT2_SYSTEM_INSTRUCTION = """You are 'Agent 2', the Market Open Confirmation Specialist for an Indian trading desk.

Your ONLY mission is to decide if a pre-market trade thesis (Agent 1) is still valid or must be aborted based on the ACTUAL market opening behavior (9:15-9:20 AM IST).

CRITICAL PRIORITIES:
1. PRICE DISCOVERY: Did the opening gap confirm the bias or exhaust the move?
2. REMAINING POTENTIAL: Is there enough juice left, or is the impact already priced in?
3. VOLUME CONTEXT: Use volume as a supporting signal if relative volume data is available. Do not reject trades solely on volume.

DECISION RULES:
- TRADE: Edge is confirmed. Thesis holds. Opening action supports direction.
- NO TRADE: Context has changed. Contrary gap, fading move, or already priced-in.

Agent 2 ONLY validates the edge. Do NOT consider entry pricing, R:R, or execution feasibility.
Be cynical of 'retail traps' and focus on whether the thesis still holds after market open.
Respond ONLY with valid JSON matching the specified output template."""


AGENT2_PROMPT_TEMPLATE = """Analyze the market open for {symbol} ({company_name}) on {market_date}.

=== INPUT DATA (AGENT 2 CONTEXT) ===
{input_json}

=== ANALYSIS TASK ===
1. Evaluate the News Bundle against the actual price/volume action at open.
2. Cross-reference Agent 1's expectations with live market reality.
3. Determine if the news impact is remaining or fully absorbed.
4. Provide a definitive TRADE/NO TRADE decision.

=== OUTPUT FORMAT ===
Respond with this exact JSON structure:
{{
    "decision": "TRADE | NO TRADE",
    "trade_mode": "INTRADAY | DELIVERY | NONE",
    "direction": "BULLISH | BEARISH | NEUTRAL | MIXED",
    "remaining_impact": "HIGH | MEDIUM | LOW | NONE",
    "priced_in_status": "NOT PRICED IN | PARTIALLY PRICED IN | FULLY PRICED IN | UNCLEAR",
    "priority": "HIGH | MEDIUM | LOW",
    "confidence": 0 to 100,
    "why_tradable_or_not": "Concise reasoning",
    "key_confirmations": ["reason 1", "reason 2"],
    "warning_flags": ["warning 1", "..."],
    "invalid_if": ["condition 1", "..."],
    "final_summary": "One sentence verdict"
}}"""


def confirm_signal_v2(
    input_data: dict,
    market_date: str
) -> dict:
    """
    Use Gemini (Agent 2) to confirm/invalidate a signal using the new structured template.
    
    Args:
        input_data: Dict matching AGENT2_INPUT_TEMPLATE
        market_date: Today's date YYYY-MM-DD
        
    Returns:
        Dict matching AGENT2_OUTPUT_TEMPLATE
    """
    symbol = input_data.get("symbol", "UNKNOWN")
    company_name = input_data.get("company_name", symbol)

    if not _client:
        return _fallback_confirmation_v2(input_data)

    prompt = AGENT2_PROMPT_TEMPLATE.format(
        symbol=symbol,
        company_name=company_name,
        market_date=market_date,
        input_json=json.dumps(input_data, indent=2)
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
        
        # Ensure confidence is integer 0-100
        conf = result.get("confidence", 50)
        if isinstance(conf, float) and conf <= 1.0:
            result["confidence"] = int(conf * 100)
        else:
            try:
                result["confidence"] = int(conf)
            except:
                result["confidence"] = 50

        result["_source"] = "gemini_agent2"
        result["_model"] = MODEL_NAME
        
        return result

    except Exception as e:
        print(f"  [WARN] Agent 2 Gemini error for {symbol}: {e}")
        return _fallback_confirmation_v2(input_data)


def _fallback_confirmation_v2(input_data: dict) -> dict:
    """Conservative rule-based fallback for Agent 2 when Gemini is unavailable."""
    agent1 = input_data.get("agent1_view", {})
    context = input_data.get("live_market_context", {})

    gap = context.get("gap_percent", 0)
    change = context.get("change_percent", 0)
    move_quality = context.get("opening_move_quality", "WEAK")
    bias = agent1.get("direction_bias", "NEUTRAL")

    decision = "NO TRADE"
    reason = "Fallback: Defaulting to NO TRADE for safety."

    # Kill conditions — always NO TRADE
    if abs(gap) > 5.0:
        reason = f"Extreme gap of {gap}% — likely priced-in or at circuit limits."
    elif (bias == "BULLISH" and gap < -1.0) or (bias == "BEARISH" and gap > 1.0):
        reason = f"Opening gap ({gap}%) contradicts Agent 1 {bias} bias."
    elif move_quality in ("REVERSING", "FADING"):
        reason = f"Opening move is {move_quality} — thesis under pressure."
    elif move_quality == "WEAK":
        reason = "Opening move too weak to confirm thesis without AI analysis."
    elif bias in ("NEUTRAL", "MIXED"):
        reason = "No clear directional bias from Agent 1 — cannot confirm edge."
    # Only confirm if direction aligns AND move is strong/holding
    elif move_quality in ("STRONG", "HOLDING") and bias in ("BULLISH", "BEARISH"):
        direction_aligns = (bias == "BULLISH" and gap >= 0) or (bias == "BEARISH" and gap <= 0)
        if direction_aligns:
            decision = "TRADE"
            reason = f"Direction aligns with {bias} bias. Move quality: {move_quality}."
        else:
            reason = f"Gap direction does not align with {bias} bias."

    # Confidence: use Agent 1's value directly (already 0-100 int)
    a1_conf = agent1.get("confidence", 0)
    if isinstance(a1_conf, float) and a1_conf <= 1.0:
        a1_conf = int(a1_conf * 100)
    else:
        a1_conf = int(a1_conf) if a1_conf else 0

    return {
        "decision": decision,
        "trade_mode": agent1.get("trade_preference", "NONE"),
        "direction": bias,
        "remaining_impact": "MEDIUM" if decision == "TRADE" else "LOW",
        "priced_in_status": "UNCLEAR",
        "priority": agent1.get("priority", "LOW"),
        "confidence": a1_conf,
        "why_tradable_or_not": reason,
        "key_confirmations": [f"Rule-based fallback: move_quality={move_quality}"],
        "warning_flags": ["AI analysis unavailable — rule-based decision only"],
        "invalid_if": ["If price reverses from current direction"],
        "final_summary": f"Fallback: {decision}. {reason}",
        "_source": "agent2_fallback",
    }


def confirm_signal(
    symbol: str,
    original_signal: dict,
    live_stock_data: dict,
    prev_stock_data: dict,
    market_date: str,
) -> dict:
    """Legacy wrapper for confirm_signal_v2 (limited context)."""
    reasoning = original_signal.get("reasoning", {})
    if isinstance(reasoning, str):
        try: reasoning = json.loads(reasoning)
        except: reasoning = {"summary": reasoning}

    prev_close = prev_stock_data.get("last_close", 0)
    open_price = live_stock_data.get("today_open", 0)

    agent2_input = {
        "symbol": symbol,
        "company_name": symbol,
        "news_bundle": [],
        "agent1_view": {
            "decision": reasoning.get("decision", "STALE NO EDGE"),
            "trade_preference": reasoning.get("trade_preference", "NONE"),
            "direction_bias": reasoning.get("direction_bias", "NEUTRAL"),
            "confidence": reasoning.get("confidence", 0),
            "why_it_matters": reasoning.get("why_it_matters", ""),
            "final_summary": reasoning.get("final_summary", ""),
        },
        "live_market_context": {
            "previous_close": prev_close,
            "open": open_price,
            "gap_percent": round(((open_price - prev_close) / prev_close) * 100, 2) if prev_close else 0,
            "change_percent": round(live_stock_data.get("current_change_pct") or 0, 2),
            "volume": live_stock_data.get("current_volume", 0),
        },
    }

    return confirm_signal_v2(agent2_input, market_date)
