"""Gemini-powered Execution Agent (Agent 3).

Creates an execution plan based on Agent 2's validation and live market data.
Decides whether to ENTER NOW, WAIT FOR BREAKOUT, WAIT FOR PULLBACK, AVOID CHASE, or NO TRADE.
Produces actionable entry, stoploss, and target levels.
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


AGENT3_SYSTEM_INSTRUCTION = """You are 'Agent 3', the Senior Execution Planner for an Indian trading desk.

Your ONLY mission is to decide HOW and WHEN to execute a validated trade thesis (from Agent 2) based on current live price action.

CRITICAL PRIORITIES:
1. SAFE ENTRY: Do not chase extended moves. Ensure the entry price makes structural sense (pullback, breakout, or current price if safe).
2. REALISTIC RISK: Set a logical stoploss based on intraday structure (not arbitrary %).
3. REALISTIC REWARD: Set a logical target based on move potential and day range.

EXECUTION RULES:
- If Agent 2 says NO TRADE, your action MUST be AVOID and execution_decision NO TRADE.
- ENTER NOW: Edge is valid, price is not overextended, R:R is acceptable.
- WAIT FOR BREAKOUT: Edge is valid, but stock is testing a key level and needs to break it first. Note: BREAKOUT_HIGH means breaking resistance, BREAKDOWN_LOW means breaking support.
- WAIT FOR PULLBACK: Edge is valid, but price has already run too much. Wait for a dip/rally.
- AVOID CHASE: The move is completely exhausted or too far from VWAP/structure.
- NO TRADE: Context is completely invalid or Agent 2 rejected it.

Agent 3 DOES NOT second-guess Agent 2's fundamental thesis unless the live price action completely breaks the intraday structure.
Respond ONLY with valid JSON matching the specified output template."""


AGENT3_PROMPT_TEMPLATE = """Analyze the execution context for {symbol} ({company_name}).

=== INPUT DATA (AGENT 3 CONTEXT) ===
{input_json}

=== ANALYSIS TASK ===
1. Review Agent 2's validation (TRADE/NO TRADE, Direction, Confidence).
2. Analyze the live execution context (LTP, VWAP, distance from high/low, move quality, structure).
3. Decide the execution action (BUY / SELL / WAIT / AVOID).
4. Decide the execution decision (ENTER NOW / WAIT FOR BREAKOUT / WAIT FOR PULLBACK / AVOID CHASE / NO TRADE).
5. Formulate precise entry, stoploss, and target plans. Use the provided price levels (LTP, open, high, low, VWAP).

=== OUTPUT FORMAT ===
Respond with this exact JSON structure:
{{
  "action": "BUY | SELL | WAIT | AVOID",
  "execution_decision": "ENTER NOW | WAIT FOR BREAKOUT | WAIT FOR PULLBACK | AVOID CHASE | NO TRADE",
  "trade_mode": "INTRADAY | DELIVERY | NONE",
  "confidence": 0 to 100,
  "entry_plan": {{
    "entry_type": "MARKET | BREAKOUT | PULLBACK | NONE",
    "entry_price": 0.0,
    "condition": "Concise condition"
  }},
  "stop_loss": {{
    "price": 0.0,
    "reason": "Concise reasoning"
  }},
  "target": {{
    "price": 0.0,
    "reason": "Concise reasoning"
  }},
  "risk_reward": "String like '1:2' or 'Poor'",
  "invalidation": "What breaks the execution plan",
  "why_now_or_why_wait": "Concise reasoning",
  "final_summary": "One sentence summary"
}}"""


def plan_execution(
    input_data: dict,
) -> dict:
    """
    Use Gemini (Agent 3) to generate an execution plan.
    
    Args:
        input_data: Dict matching the Agent 3 Input Contract.
        
    Returns:
        Dict matching the Agent 3 Output Contract.
    """
    symbol = input_data.get("symbol", "UNKNOWN")
    company_name = input_data.get("company_name", symbol)

    if not _client:
        return _fallback_execution(input_data)

    prompt = AGENT3_PROMPT_TEMPLATE.format(
        symbol=symbol,
        company_name=company_name,
        input_json=json.dumps(input_data, indent=2)
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=AGENT3_SYSTEM_INSTRUCTION,
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

        result["_source"] = "gemini_agent3"
        result["_model"] = MODEL_NAME
        
        return result

    except Exception as e:
        print(f"  [WARN] Agent 3 Gemini error for {symbol}: {e}")
        return _fallback_execution(input_data)


def _fallback_execution(input_data: dict) -> dict:
    """Conservative rule-based fallback for Agent 3 when Gemini is unavailable."""
    agent2 = input_data.get("agent2_view", {})
    context = input_data.get("live_execution_context", {})

    decision2 = agent2.get("decision", "NO TRADE")
    direction = agent2.get("direction", "NEUTRAL")
    trade_mode = agent2.get("trade_mode", "NONE")
    
    ltp = context.get("ltp", 0)
    vwap = context.get("vwap", 0)
    move_quality = context.get("opening_move_quality", "WEAK")
    dist_high = context.get("distance_from_day_high_percent", 100)
    dist_low = context.get("distance_from_day_low_percent", 100)
    dist_vwap = context.get("distance_from_vwap_percent", 0)
    
    # Defaults for NO TRADE
    action = "AVOID"
    exec_decision = "NO TRADE"
    entry_type = "NONE"
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    reason = "Agent 2 rejected the trade."

    if decision2 == "TRADE":
        if direction == "BULLISH":
            action = "WAIT"
            exec_decision = "WAIT FOR PULLBACK"
            entry_type = "PULLBACK"
            entry_price = vwap if vwap else ltp * 0.99
            stop_price = entry_price * 0.98 if entry_price else 0
            
            if trade_mode == "DELIVERY":
                target_price = entry_price * 1.08 if entry_price else 0
                reason = "Fallback: Waiting for pullback. Delivery setups need safe entries."
                if move_quality in ["STRONG", "HOLDING"]:
                    if dist_vwap < 1.0 and dist_high > 1.0:
                        action = "BUY"
                        exec_decision = "ENTER NOW"
                        entry_type = "MARKET"
                        entry_price = ltp
                        stop_price = vwap if vwap and vwap < ltp else ltp * 0.98
                        reason = "Fallback: Clean delivery setup, entering now."
            else:
                target_price = entry_price * 1.04 if entry_price else 0
                reason = "Fallback: Waiting for pullback to VWAP for safety."
                if move_quality in ["STRONG", "HOLDING"]:
                    if dist_vwap > 2.0 or dist_high < 0.5:
                        action = "WAIT"
                        exec_decision = "AVOID CHASE" if dist_vwap > 3.0 else "WAIT FOR PULLBACK"
                        reason = "Fallback: Move is extended (chase risk). Waiting for pullback."
                    else:
                        action = "BUY"
                        exec_decision = "ENTER NOW"
                        entry_type = "MARKET"
                        entry_price = ltp
                        stop_price = vwap if vwap and vwap < ltp else ltp * 0.99
                        target_price = ltp * 1.02
                        reason = "Fallback: Strong move, not overextended, entering now."
                
        elif direction == "BEARISH" and trade_mode == "INTRADAY":
            action = "WAIT"
            exec_decision = "WAIT FOR PULLBACK"
            entry_type = "PULLBACK"
            entry_price = vwap if vwap else ltp * 1.01
            stop_price = entry_price * 1.02 if entry_price else 0
            target_price = entry_price * 0.96 if entry_price else 0
            reason = "Fallback: Waiting for rally to VWAP for safety."
            if move_quality in ["STRONG", "HOLDING"]:
                if dist_vwap < -2.0 or dist_low < 0.5:
                    action = "WAIT"
                    exec_decision = "AVOID CHASE" if dist_vwap < -3.0 else "WAIT FOR PULLBACK"
                    reason = "Fallback: Downside move is extended (chase risk). Waiting for rally."
                else:
                    action = "SELL"
                    exec_decision = "ENTER NOW"
                    entry_type = "MARKET"
                    entry_price = ltp
                    stop_price = vwap if vwap and vwap > ltp else ltp * 1.01
                    target_price = ltp * 0.98
                    reason = "Fallback: Strong downside move, not overextended, entering now."
                
        else:
            action = "AVOID"
            exec_decision = "NO TRADE"
            reason = "Fallback: Unclear direction or invalid mode for shorting."

    # Calculate real fallback RR
    rr_str = "Poor"
    if entry_price and stop_price and target_price:
        if direction == "BULLISH" and entry_price > stop_price:
            risk = entry_price - stop_price
            reward = target_price - entry_price
            if risk > 0 and reward > 0:
                rr_str = f"1:{round(reward / risk, 1)}"
        elif direction == "BEARISH" and stop_price > entry_price:
            risk = stop_price - entry_price
            reward = entry_price - target_price
            if risk > 0 and reward > 0:
                rr_str = f"1:{round(reward / risk, 1)}"

    a2_conf = agent2.get("confidence", 0)
    if isinstance(a2_conf, float) and a2_conf <= 1.0:
        a2_conf = int(a2_conf * 100)
    else:
        a2_conf = int(a2_conf) if a2_conf else 0

    return {
        "action": action,
        "execution_decision": exec_decision,
        "trade_mode": trade_mode if exec_decision != "NO TRADE" else "NONE",
        "confidence": a2_conf,
        "entry_plan": {
            "entry_type": entry_type,
            "entry_price": round(entry_price, 2),
            "condition": reason
        },
        "stop_loss": {
            "price": round(stop_price, 2),
            "reason": "Rule-based fallback stop"
        },
        "target": {
            "price": round(target_price, 2),
            "reason": "Rule-based fallback target"
        },
        "risk_reward": rr_str,
        "invalidation": "If price moves against structure",
        "why_now_or_why_wait": reason,
        "final_summary": f"Fallback execution: {exec_decision}",
        "_source": "agent3_fallback"
    }
