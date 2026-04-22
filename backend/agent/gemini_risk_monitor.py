"""Gemini-powered Risk Monitor Agent (Agent 4) — LLM judgment layer.

This is an OPTIONAL intelligent overlay on top of the rule-based risk engine.
It is used when:
  1. The rule engine produces a borderline result (risk_score 30-70)
  2. The trade has multiple conflicting signals
  3. A human-quality judgment would add value

It does NOT replace hard invalidations — those always fire first.

Architecture:
  - Receives the full feature snapshot + rule engine output
  - Produces a second opinion that may upgrade or downgrade the decision
  - The orchestrator (risk_monitor.py) merges both outputs

Follows the same Gemini client pattern as Agent 1/2/3.
"""

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_client = None
if GEMINI_API_KEY and GEMINI_API_KEY.strip() and GEMINI_API_KEY != "your_gemini_api_key_here":
    _client = genai.Client(api_key=GEMINI_API_KEY)


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM INSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════════

RISK_MONITOR_SYSTEM_INSTRUCTION = """You are Agent 4 — the live post-entry Risk Monitor of an Indian equity trading system.

You are NOT an entry agent. The trade has ALREADY been entered.
Your only job is to answer: "Does this trade still deserve to be held?"

You must judge the QUALITY of the trade RIGHT NOW — not when it was entered.

OPERATING PRINCIPLES:
- You are conservative about holding damaged trades.
- A single weak indicator alone must NOT force exit (unless it is a hard invalidation).
- Multiple weak signals aligning together IS a valid reason to reduce or exit.
- You must think in terms of trade edge: is the edge still alive, or has it deteriorated?
- You must respect time decay: an intraday trade lingering for hours without follow-through is losing its edge.
- You must differentiate INTRADAY from DELIVERY:
  - INTRADAY: faster reactions, shorter patience, tighter time windows
  - DELIVERY: more patient, wider tolerance, but still exits on structural damage

DECISION OPTIONS:
- HOLD: trade is healthy, thesis intact, no concerning signals
- HOLD_WITH_CAUTION: trade is still viable but showing early warning signs
- TIGHTEN_STOPLOSS: risk is rising, protect gains by moving stop closer
- PARTIAL_EXIT: multiple risks aligning, reduce exposure
- EXIT_NOW: trade edge is broken or severely damaged, exit immediately

IMPORTANT RULES:
- RSI alone does NOT justify exit. RSI + rejection + volume + structure together CAN.
- MACD cross alone does NOT justify exit. It is a supporting signal only.
- One red candle alone does NOT justify exit.
- Supertrend alone does NOT justify exit.
- Stop-loss breach IS always EXIT_NOW (but this is handled by the rule engine, not you).
- If the rule engine already called EXIT_NOW due to hard invalidation, you should agree.

Write in clear, practical English. Be direct.
Respond ONLY with valid JSON matching the required schema."""


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════

RISK_MONITOR_PROMPT = """You are evaluating the live risk status of an OPEN trade in {symbol}.

=== TRADE CONTEXT ===
Direction: {direction}
Trade Mode: {trade_mode}
Entry Price: ₹{entry_price}
Stop Loss: ₹{stop_loss}
Target: ₹{target_price}
Current LTP: ₹{ltp}
Time in Trade: {time_in_trade_display}

=== ORIGINAL TRADE THESIS ===
{thesis_summary}

=== LIVE RISK FEATURES ===
{features_json}

=== RULE ENGINE ASSESSMENT ===
{rule_engine_json}

=== TASK ===
Evaluate whether this trade should still be held by analyzing ALL of these factors together:

1. Distance to stop-loss — is the move toward SL controlled or aggressive?
2. Impact persistence — is the original trade catalyst still driving the move?
3. Pullback behavior — healthy retracement or dangerous reversal?
4. Time in trade — has the expected reaction window passed without follow-through?
5. Candle structure — higher lows or lower highs? Strong close or weak close?
6. RSI context — supportive zone or dangerously overbought/oversold?
7. Supertrend — still confirming the trend direction?
8. MACD — momentum expanding or contracting?
9. ATR/volatility — is the current move within normal noise or abnormal?
10. Volume — does volume support the current position or oppose it?
11. Market depth — is order flow supportive or hostile?
12. Overbought/oversold with volume context — is there rejection pressure?

REMEMBER:
- No single indicator alone triggers exit (except SL breach)
- Multiple weak signals together CAN trigger reduction or exit
- INTRADAY and DELIVERY must be judged differently
- Your job is to judge: "Is the edge still alive?"

=== OUTPUT FORMAT ===
Respond with exactly this JSON:

{{
  "decision": "HOLD | HOLD_WITH_CAUTION | TIGHTEN_STOPLOSS | PARTIAL_EXIT | EXIT_NOW",
  "confidence": <integer 0-100>,
  "risk_score": <integer 0-100>,
  "thesis_status": "intact | weakening | damaged | broken",
  "exit_urgency": "none | low | medium | high | critical",
  "primary_reason": "<2-3 sentences explaining the decision>",
  "triggered_risks": ["<risk_1>", "<risk_2>"],
  "execution_note": "<one sentence on what to do right now>",
  "updated_stop_loss": <number or null>,
  "next_review_priority": "normal | high | urgent"
}}

Rules:
- decision must be exactly one of the 5 options
- risk_score 0 = no risk, 100 = maximum risk
- confidence = how sure you are about this decision
- thesis_status reflects the health of the original trade thesis
- updated_stop_loss only if decision = TIGHTEN_STOPLOSS, otherwise null
- Do not output anything outside the JSON"""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_risk_with_llm(
    signal: dict,
    features: dict,
    rule_engine_result: dict,
) -> dict:
    """Use Gemini to produce an intelligent risk assessment.

    Args:
        signal: The trade signal record (with reasoning, execution_data, etc.)
        features: Extracted risk features from risk_features.py
        rule_engine_result: Output from risk_rules.py

    Returns:
        Gemini's risk assessment dict, or fallback if unavailable.
    """
    if not _client:
        # LLM unavailable — return the rule engine result as-is
        result = dict(rule_engine_result)
        result["_source"] = "rule_engine_only"
        result["_llm_available"] = False
        return result

    # Build context
    symbol = signal.get("symbol", "UNKNOWN")
    exec_data = signal.get("execution_data") or {}
    entry_plan = exec_data.get("entry_plan") or {}
    sl_plan = exec_data.get("stop_loss") or {}
    target_plan = exec_data.get("target") or {}

    entry_price = features.get("entry_price", 0)
    stop_loss = features.get("stop_loss", 0)
    target_price = features.get("target_price", 0)
    ltp = features.get("ltp", 0)
    direction = features.get("direction", "BUY")
    trade_mode = features.get("trade_mode", "INTRADAY")

    # Format time display
    time_seconds = features.get("time_in_trade_seconds", 0)
    hours = int(time_seconds // 3600)
    minutes = int((time_seconds % 3600) // 60)
    time_display = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

    # Extract thesis summary from original reasoning
    reasoning = signal.get("reasoning") or {}
    thesis_parts = []
    if reasoning.get("event_summary"):
        thesis_parts.append(f"Event: {reasoning['event_summary']}")
    if reasoning.get("impact_analysis"):
        thesis_parts.append(f"Impact: {reasoning['impact_analysis']}")

    # Add Agent 2 confirmation context
    conf_data = signal.get("confirmation_data") or {}
    if conf_data.get("why_tradable_or_not"):
        thesis_parts.append(f"Confirmation: {conf_data['why_tradable_or_not']}")

    thesis_summary = "\n".join(thesis_parts) if thesis_parts else "No thesis summary available."

    # Compact feature dict for LLM (remove redundant/internal fields)
    compact_features = {k: v for k, v in features.items() if not k.startswith("_") and k not in (
        "symbol", "direction", "is_long", "trade_mode",
        "entry_price", "stop_loss", "target_price"
    )}

    prompt = RISK_MONITOR_PROMPT.format(
        symbol=symbol,
        direction=direction,
        trade_mode=trade_mode,
        entry_price=f"{entry_price:.2f}" if entry_price else "0",
        stop_loss=f"{stop_loss:.2f}" if stop_loss else "0",
        target_price=f"{target_price:.2f}" if target_price else "0",
        ltp=f"{ltp:.2f}" if ltp else "0",
        time_in_trade_display=time_display,
        thesis_summary=thesis_summary,
        features_json=json.dumps(compact_features, indent=2, default=str),
        rule_engine_json=json.dumps({
            "decision": rule_engine_result.get("decision"),
            "risk_score": rule_engine_result.get("risk_score"),
            "thesis_status": rule_engine_result.get("thesis_status"),
            "triggered_risks": rule_engine_result.get("triggered_risks", []),
        }, indent=2),
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=RISK_MONITOR_SYSTEM_INSTRUCTION,
                temperature=0.15,
                max_output_tokens=1024,
            ),
        )

        text = response.text.strip()
        # Strip markdown fences
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
        try:
            if isinstance(conf, float) and conf <= 1.0:
                result["confidence"] = int(conf * 100)
            else:
                result["confidence"] = int(conf)
        except Exception:
            result["confidence"] = 50
        result["confidence"] = max(0, min(100, result["confidence"]))

        # Normalize risk_score
        rs = result.get("risk_score", 50)
        try:
            result["risk_score"] = max(0, min(100, int(rs)))
        except Exception:
            result["risk_score"] = 50

        # Validate decision
        valid_decisions = {"HOLD", "HOLD_WITH_CAUTION", "TIGHTEN_STOPLOSS", "PARTIAL_EXIT", "EXIT_NOW"}
        if result.get("decision") not in valid_decisions:
            result["decision"] = rule_engine_result.get("decision", "HOLD")

        result["_source"] = "gemini_agent4"
        result["_model"] = MODEL_NAME
        result["_llm_available"] = True
        return result

    except json.JSONDecodeError as e:
        print(f"  [WARN] Agent 4 Gemini returned invalid JSON for {symbol}: {e}")
        fallback = dict(rule_engine_result)
        fallback["_source"] = "rule_engine_fallback"
        fallback["_llm_error"] = str(e)
        return fallback
    except Exception as e:
        print(f"  [WARN] Agent 4 Gemini API error for {symbol}: {e}")
        fallback = dict(rule_engine_result)
        fallback["_source"] = "rule_engine_fallback"
        fallback["_llm_error"] = str(e)
        return fallback
