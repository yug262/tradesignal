"""Gemini-powered Execution Agent (Agent 3).

Creates an execution plan based on Agent 2's validation and live market data.
Decides whether to ENTER NOW, WAIT FOR BREAKOUT, WAIT FOR PULLBACK, AVOID CHASE, or NO TRADE.
Produces actionable entry, stoploss, target levels AND position size based on user risk config.
"""

import os
import json
import math
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
2. REALISTIC RISK: Set a logical stoploss based on intraday structure (not arbitrary %). The stoploss MUST ensure the position size stays within the risk_params boundaries provided.
3. REALISTIC REWARD: Set a logical target based on move potential and day range. Must meet or exceed min_rr.
4. POSITION SIZING: You MUST output a position_size_inr (capital allocated) that does NOT exceed max_position_capital. The shares count must be realistic.

EXECUTION RULES:
- If Agent 2 says NO TRADE, your action MUST be AVOID and execution_decision NO TRADE.
- ENTER NOW: Edge is valid, price is not overextended, R:R is acceptable.
- WAIT FOR BREAKOUT: Edge is valid, but stock is testing a key level. BREAKOUT_HIGH = break resistance, BREAKDOWN_LOW = break support.
- WAIT FOR PULLBACK: Edge is valid, but price has already run. Wait for a dip/rally.
- AVOID CHASE: Move is completely exhausted or too far from structure.
- NO TRADE: Context invalid or Agent 2 rejected.

HARD CONSTRAINTS (from user risk settings — you MUST respect these):
- max_loss_amount: Maximum INR loss if stoploss is hit. Position size must be calculated so loss at SL <= this amount.
- max_position_capital: Maximum INR allocated to this trade. position_size_inr must <= this.
- min_rr: Minimum acceptable risk:reward ratio. Reject trades below this.
- A single trade must NEVER use 100% of capital.

Agent 3 DOES NOT second-guess Agent 2's fundamental thesis unless live price action completely breaks intraday structure.
Respond ONLY with valid JSON matching the specified output template."""


AGENT3_PROMPT_TEMPLATE = """Analyze the execution context for {symbol} ({company_name}).

=== RISK PARAMETERS (HARD LIMITS — NON-NEGOTIABLE) ===
Total Capital Available    : Rs.{total_capital}
Max Loss Per Trade         : Rs.{max_loss_amount} ({max_loss_pct}% of capital)
Max Capital Per Trade      : Rs.{max_position_capital} ({max_capital_pct}% of capital)
Min Risk:Reward Required   : {min_rr}:1
Max Daily Loss Budget      : Rs.{max_daily_loss_amount} ({max_daily_loss_pct}% of capital)

POSITION SIZING FORMULA:
  risk_per_share = entry_price - stop_loss_price  (for BUY)
                 = stop_loss_price - entry_price  (for SELL/SHORT)
  max_shares_by_loss    = max_loss_amount / risk_per_share
  max_shares_by_capital = max_position_capital / entry_price
  position_size_shares  = floor(min(max_shares_by_loss, max_shares_by_capital))
  position_size_inr     = position_size_shares × entry_price

=== INPUT DATA (AGENT 3 CONTEXT) ===
{input_json}

=== ANALYSIS TASK ===
1. Review Agent 2's validation (TRADE/NO TRADE, Direction, Confidence).
2. Analyze the live execution context (LTP, VWAP, distance from high/low, move quality, structure).
3. Decide the execution action (BUY / SELL / WAIT / AVOID).
4. Decide the execution decision (ENTER NOW / WAIT FOR BREAKOUT / WAIT FOR PULLBACK / AVOID CHASE / NO TRADE).
5. Set entry, stoploss, and target. Verify: (entry - stop) × shares <= max_loss_amount AND shares × entry <= max_position_capital AND (target - entry)/(entry - stop) >= min_rr.
6. Calculate the position size using the formula above.
7. If the stoploss would require 0 shares to stay within risk limits, output NO TRADE.

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
    "reason": "Structural reason for this level"
  }},
  "target": {{
    "price": 0.0,
    "reason": "Structural reason for this level"
  }},
  "position_sizing": {{
    "position_size_shares": 0,
    "position_size_inr": 0.0,
    "risk_per_share": 0.0,
    "max_loss_at_sl": 0.0,
    "capital_used_pct": 0.0,
    "sizing_note": "Brief note on how size was determined"
  }},
  "risk_reward": "String like '1:2.3' or 'Below minimum'",
  "invalidation": "What breaks the execution plan",
  "why_now_or_why_wait": "Concise reasoning",
  "final_summary": "One sentence summary"
}}"""


def _compute_risk_params(risk_config: dict) -> dict:
    """
    Pre-compute hard INR boundaries from user risk config before calling Gemini.
    These are passed into the prompt AND used to validate/clamp Gemini's output.
    """
    capital = float(risk_config.get("capital", 100_000))
    max_loss_pct = float(risk_config.get("max_loss_per_trade_pct", 1.0))
    max_capital_pct = float(risk_config.get("max_capital_per_trade_pct", 20.0))
    min_rr = float(risk_config.get("min_rr", 1.5))
    max_daily_loss_pct = float(risk_config.get("max_daily_loss_pct", 3.0))

    # Hard cap: never allocate 100% in one trade — ceiling at 50% regardless of setting
    safe_cap_pct = min(max_capital_pct, 50.0)

    return {
        "total_capital": round(capital, 2),
        "max_loss_pct": max_loss_pct,
        "max_loss_amount": round(capital * max_loss_pct / 100, 2),
        "max_capital_pct": safe_cap_pct,
        "max_position_capital": round(capital * safe_cap_pct / 100, 2),
        "min_rr": min_rr,
        "max_daily_loss_pct": max_daily_loss_pct,
        "max_daily_loss_amount": round(capital * max_daily_loss_pct / 100, 2),
    }


def _compute_position_size(entry: float, stop: float, direction: str, rp: dict) -> dict:
    """
    Compute safe position size given entry, stop, and risk boundaries.
    Returns a sizing dict with shares, INR allocated, and actual loss at SL.
    """
    if entry <= 0 or stop <= 0:
        return {"position_size_shares": 0, "position_size_inr": 0.0, "risk_per_share": 0.0,
                "max_loss_at_sl": 0.0, "capital_used_pct": 0.0, "sizing_note": "Invalid prices"}

    if direction == "BULLISH":
        risk_per_share = entry - stop
    else:
        risk_per_share = stop - entry

    if risk_per_share <= 0:
        return {"position_size_shares": 0, "position_size_inr": 0.0, "risk_per_share": 0.0,
                "max_loss_at_sl": 0.0, "capital_used_pct": 0.0, "sizing_note": "Stop on wrong side of entry"}

    max_shares_by_loss = rp["max_loss_amount"] / risk_per_share
    max_shares_by_capital = rp["max_position_capital"] / entry

    shares = math.floor(min(max_shares_by_loss, max_shares_by_capital))
    if shares < 1:
        return {"position_size_shares": 0, "position_size_inr": 0.0, "risk_per_share": round(risk_per_share, 2),
                "max_loss_at_sl": 0.0, "capital_used_pct": 0.0,
                "sizing_note": f"Risk/share Rs.{risk_per_share:.2f} too wide — 0 shares within limits"}

    position_inr = round(shares * entry, 2)
    loss_at_sl = round(shares * risk_per_share, 2)
    cap_used_pct = round(position_inr / rp["total_capital"] * 100, 2)

    return {
        "position_size_shares": shares,
        "position_size_inr": position_inr,
        "risk_per_share": round(risk_per_share, 2),
        "max_loss_at_sl": loss_at_sl,
        "capital_used_pct": cap_used_pct,
        "sizing_note": f"Sized by {'loss limit' if max_shares_by_loss < max_shares_by_capital else 'capital limit'}"
    }


def _validate_rr(entry: float, stop: float, target: float, direction: str, min_rr: float) -> tuple[float, bool]:
    """Return (actual_rr, meets_minimum)."""
    if direction == "BULLISH":
        risk = entry - stop
        reward = target - entry
    else:
        risk = stop - entry
        reward = entry - target
    if risk <= 0:
        return 0.0, False
    rr = round(reward / risk, 2)
    return rr, rr >= min_rr


def plan_execution(
    input_data: dict,
    risk_config: dict = None,
) -> dict:
    """
    Use Gemini (Agent 3) to generate an execution plan with position sizing.

    Args:
        input_data: Dict matching the Agent 3 Input Contract.
        risk_config: User risk settings from SystemConfig (capital, limits, etc.)

    Returns:
        Dict with execution plan + position_sizing block.
    """
    symbol = input_data.get("symbol", "UNKNOWN")
    company_name = input_data.get("company_name", symbol)
    risk_config = risk_config or {}

    # Pre-compute hard boundaries
    rp = _compute_risk_params(risk_config)

    if not _client:
        return _fallback_execution(input_data, rp)

    prompt = AGENT3_PROMPT_TEMPLATE.format(
        symbol=symbol,
        company_name=company_name,
        total_capital=rp["total_capital"],
        max_loss_pct=rp["max_loss_pct"],
        max_loss_amount=rp["max_loss_amount"],
        max_capital_pct=rp["max_capital_pct"],
        max_position_capital=rp["max_position_capital"],
        min_rr=rp["min_rr"],
        max_daily_loss_pct=rp["max_daily_loss_pct"],
        max_daily_loss_amount=rp["max_daily_loss_amount"],
        input_json=json.dumps(input_data, indent=2)
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=AGENT3_SYSTEM_INSTRUCTION,
                temperature=0.1,
                max_output_tokens=1536,
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

        # Normalize confidence
        conf = result.get("confidence", 50)
        if isinstance(conf, float) and conf <= 1.0:
            result["confidence"] = int(conf * 100)
        else:
            try:
                result["confidence"] = int(conf)
            except Exception:
                result["confidence"] = 50

        # --- Post-process: recompute position sizing from Gemini's price levels ---
        ep = result.get("entry_plan", {})
        sl = result.get("stop_loss", {})
        tg = result.get("target", {})
        direction = input_data.get("agent2_view", {}).get("direction", "BULLISH")

        entry_price = float(ep.get("entry_price") or 0)
        stop_price = float(sl.get("price") or 0)
        target_price = float(tg.get("price") or 0)

        exec_dec = result.get("execution_decision", "NO TRADE").upper()

        if entry_price > 0 and stop_price > 0 and exec_dec not in ("NO TRADE", "AVOID CHASE"):
            # Always recompute sizing with our hard rules — never trust LLM math
            sizing = _compute_position_size(entry_price, stop_price, direction, rp)

            # If 0 shares possible, force NO TRADE
            if sizing["position_size_shares"] == 0:
                result["action"] = "AVOID"
                result["execution_decision"] = "NO TRADE"
                result["why_now_or_why_wait"] = (
                    f"Position sizing failed: {sizing['sizing_note']}. "
                    f"Risk/share Rs.{sizing.get('risk_per_share', 0):.2f} exceeds "
                    f"max loss limit Rs.{rp['max_loss_amount']:.2f}."
                )
                result["trade_mode"] = "NONE"
                sizing["sizing_note"] += " — TRADE BLOCKED"

            # Check R:R
            actual_rr, meets_min = _validate_rr(entry_price, stop_price, target_price, direction, rp["min_rr"])
            if not meets_min and exec_dec not in ("WAIT FOR PULLBACK", "WAIT FOR BREAKOUT"):
                result["risk_reward"] = f"1:{actual_rr} (below min {rp['min_rr']}:1)"
            else:
                result["risk_reward"] = f"1:{actual_rr}"

            result["position_sizing"] = sizing
        else:
            # WAIT / AVOID plans — show projected sizing at current price as guidance
            ltp = input_data.get("live_execution_context", {}).get("ltp", 0)
            if ltp and stop_price and exec_dec in ("WAIT FOR PULLBACK", "WAIT FOR BREAKOUT"):
                sizing = _compute_position_size(ltp, stop_price, direction, rp)
                sizing["sizing_note"] = "(Projected — use when entry condition is met)"
                result["position_sizing"] = sizing
            else:
                result["position_sizing"] = {
                    "position_size_shares": 0,
                    "position_size_inr": 0.0,
                    "risk_per_share": 0.0,
                    "max_loss_at_sl": 0.0,
                    "capital_used_pct": 0.0,
                    "sizing_note": "No execution planned"
                }

        result["_source"] = "gemini_agent3"
        result["_model"] = MODEL_NAME
        result["_risk_params"] = rp
        return result

    except Exception as e:
        print(f"  [WARN] Agent 3 Gemini error for {symbol}: {e}")
        return _fallback_execution(input_data, rp)


def _fallback_execution(input_data: dict, rp: dict = None) -> dict:
    """Conservative rule-based fallback for Agent 3 when Gemini is unavailable."""
    if rp is None:
        rp = _compute_risk_params({})

    agent2 = input_data.get("agent2_view", {})
    context = input_data.get("live_execution_context", {})

    decision2 = agent2.get("decision", "NO TRADE")
    direction = agent2.get("direction", "NEUTRAL")
    trade_mode = agent2.get("trade_mode", "NONE")

    ltp = context.get("ltp", 0)
    vwap = context.get("vwap", 0)
    move_quality = context.get("opening_move_quality", "WEAK")
    dist_high = context.get("distance_from_day_high_percent", 100)
    dist_vwap = context.get("distance_from_vwap_percent", 0)

    # Defaults
    action = "AVOID"
    exec_decision = "NO TRADE"
    entry_type = "NONE"
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    reason = "Agent 2 rejected the trade."

    if decision2 == "TRADE" and direction in ("BULLISH", "BEARISH"):
        if direction == "BULLISH":
            action = "WAIT"
            exec_decision = "WAIT FOR PULLBACK"
            entry_type = "PULLBACK"
            entry_price = vwap if vwap else ltp * 0.99
            stop_price = entry_price * 0.98 if entry_price else 0

            is_delivery = trade_mode == "DELIVERY"
            target_price = entry_price * (1.08 if is_delivery else 1.04) if entry_price else 0
            reason = "Fallback: Waiting for pullback to VWAP."

            if move_quality in ("STRONG", "HOLDING"):
                if is_delivery:
                    if dist_vwap < 1.0 and dist_high > 1.0:
                        action = "BUY"
                        exec_decision = "ENTER NOW"
                        entry_type = "MARKET"
                        entry_price = ltp
                        stop_price = vwap if vwap and vwap < ltp else ltp * 0.98
                        target_price = entry_price * 1.08
                        reason = "Fallback: Clean delivery setup near VWAP."
                else:
                    if dist_vwap > 3.0:
                        exec_decision = "AVOID CHASE"
                        reason = "Fallback: Too far from VWAP — chase risk."
                    elif dist_vwap <= 2.0 and dist_high > 0.5:
                        action = "BUY"
                        exec_decision = "ENTER NOW"
                        entry_type = "MARKET"
                        entry_price = ltp
                        stop_price = vwap if vwap and vwap < ltp else ltp * 0.99
                        target_price = ltp * 1.02
                        reason = "Fallback: Strong intraday move, entering near VWAP."

        elif direction == "BEARISH" and trade_mode == "INTRADAY":
            action = "WAIT"
            exec_decision = "WAIT FOR PULLBACK"
            entry_type = "PULLBACK"
            entry_price = vwap if vwap else ltp * 1.01
            stop_price = entry_price * 1.02 if entry_price else 0
            target_price = entry_price * 0.96 if entry_price else 0
            reason = "Fallback: Waiting for rally to VWAP to short."

            if move_quality in ("STRONG", "HOLDING"):
                if dist_vwap < -3.0:
                    exec_decision = "AVOID CHASE"
                    reason = "Fallback: Downside overextended — chase risk."
                else:
                    action = "SELL"
                    exec_decision = "ENTER NOW"
                    entry_type = "MARKET"
                    entry_price = ltp
                    stop_price = vwap if vwap and vwap > ltp else ltp * 1.01
                    target_price = ltp * 0.98
                    reason = "Fallback: Strong downside, entering short."

        elif direction == "BEARISH" and trade_mode == "DELIVERY":
            # Bearish delivery — conservative: wait only
            action = "WAIT"
            exec_decision = "WAIT FOR PULLBACK"
            entry_type = "PULLBACK"
            entry_price = vwap if vwap else ltp * 1.01
            stop_price = entry_price * 1.02 if entry_price else 0
            target_price = entry_price * 0.95 if entry_price else 0
            reason = "Fallback: Bearish delivery — waiting for dead-cat bounce to enter short."
        else:
            reason = "Fallback: Unclear direction or unsupported trade mode."

    # Compute position sizing
    sizing = {"position_size_shares": 0, "position_size_inr": 0.0, "risk_per_share": 0.0,
               "max_loss_at_sl": 0.0, "capital_used_pct": 0.0, "sizing_note": "No trade planned"}

    if exec_decision not in ("NO TRADE", "AVOID CHASE", "AVOID") and entry_price > 0 and stop_price > 0:
        sizing = _compute_position_size(entry_price, stop_price, direction, rp)
        if sizing["position_size_shares"] == 0:
            action = "AVOID"
            exec_decision = "NO TRADE"
            reason += f" [Blocked: {sizing['sizing_note']}]"

    # R:R string
    rr_str = "Poor"
    if entry_price and stop_price and target_price:
        actual_rr, meets = _validate_rr(entry_price, stop_price, target_price, direction, rp["min_rr"])
        if actual_rr > 0:
            rr_str = f"1:{actual_rr}" + ("" if meets else f" (below min {rp['min_rr']}:1)")

    a2_conf = agent2.get("confidence", 0)
    try:
        a2_conf = int(float(a2_conf) * 100) if isinstance(a2_conf, float) and a2_conf <= 1.0 else int(a2_conf or 0)
    except Exception:
        a2_conf = 0

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
            "reason": "Rule-based fallback stop (structure-based)"
        },
        "target": {
            "price": round(target_price, 2),
            "reason": "Rule-based fallback target"
        },
        "position_sizing": sizing,
        "risk_reward": rr_str,
        "invalidation": "If price moves against structure or violates key level",
        "why_now_or_why_wait": reason,
        "final_summary": f"Fallback execution: {exec_decision}",
        "_source": "agent3_fallback",
        "_risk_params": rp,
    }
