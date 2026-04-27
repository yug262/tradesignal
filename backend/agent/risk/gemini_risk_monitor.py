"""Gemini Risk Monitor Agent — LLM-powered live trade risk assessment.

This module is the AI decision layer for Agent 4 (Risk Monitor).
It receives structured trade features and returns a JSON risk judgment.

Architecture:
  - Called by risk_monitor.py after feature extraction
  - Returns structured JSON matching the risk decision schema
  - Output is ALWAYS validated by risk_agent_validator.py before execution
  - Falls back to deterministic rule engine on any LLM failure

The agent is NOT an entry agent. It manages already-open trades.
Its purpose is live trade protection: capital first, profits second.
"""

import os
import json
import time
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("agent.risk.gemini_risk_monitor")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL")

IST = timezone(timedelta(hours=5, minutes=30))

_client = None
if GEMINI_API_KEY and GEMINI_API_KEY.strip():
    try:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        _client = None


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — encodes the entire risk monitoring philosophy
# ═══════════════════════════════════════════════════════════════════════════════

RISK_AGENT_SYSTEM_PROMPT = """You are the Risk Monitor Agent for a live Indian equities trading system.

Your role: protect capital and open profits on already-open trades.
You are NOT an entry agent. You do NOT suggest new trades.
You do NOT give market commentary or narratives.

You manage trades that are already OPEN. Your job is to decide:
- Should we continue holding?
- Should we tighten the stop-loss?
- Should we partially exit to reduce exposure?
- Should we exit the entire position immediately?

DECISION OPTIONS (choose exactly one):
- HOLD: Trade is healthy. No action needed. Continue monitoring.
- TIGHTEN_STOPLOSS: Move stop-loss forward to protect profits or reduce risk. NEVER move stop-loss backward. For long trades, new SL must be ABOVE current SL. For short trades, new SL must be BELOW current SL. New SL must never cross LTP.
- PARTIAL_EXIT: Reduce position size. Used when thesis is weakening but not broken, when risk is rising, or when profits should be partially secured. exit_fraction should be between 0.25 and 0.75.
- EXIT_NOW: Close entire position immediately. Used when thesis is broken, max loss is hit, catastrophic reversal detected, or time-based exit triggered.

THESIS STATUS:
- intact: Original trade logic still valid. Structure supports the position.
- weakening: Evidence is mixed. Some factors turning against the trade.
- broken: Clear evidence the trade premise has failed.

URGENCY:
- low: No immediate action needed. Next check cycle is fine.
- medium: Action should be taken soon. Situation is deteriorating.
- high: Immediate action required. Capital at risk.

DECISION PHILOSOPHY:
1. Protect capital first — never let a controllable loss become uncontrollable.
2. Protect open profits second — do not surrender large gains passively.
3. Avoid unnecessary churn — do not exit healthy trades out of nervousness.
4. Intraday trades require tighter management than delivery trades.
5. If evidence is mixed, lean slightly protective.
6. Never become lazy with a deteriorating position.
7. NEVER suggest widening stop-loss or moving it backward.

DECISION BOUNDARIES:
- PnL loss > -2.5%: seriously consider EXIT_NOW
- PnL loss > -3.0%: almost always EXIT_NOW
- Total rupee loss > max allowed: EXIT_NOW regardless of thesis
- PnL gain > +0.5%: consider TIGHTEN_STOPLOSS to breakeven
- PnL gain > +1.5%: TIGHTEN_STOPLOSS into profit zone
- PnL gain > +3.0%: aggressive trailing, consider PARTIAL_EXIT if exhaustion signals
- Structure reversing + reversal candle: PARTIAL_EXIT or EXIT_NOW
- Volume spike against position: PARTIAL_EXIT (or EXIT_NOW if with reversal candle)
- Near market close (after 15:10 IST) for intraday: EXIT_NOW
- Stale trade (4+ hours with < 0.3% progress for intraday): EXIT_NOW or PARTIAL_EXIT
- Delivery trade stale (4+ days with < 1% progress): PARTIAL_EXIT

MARKET DEPTH INTERPRETATION:
- depth_pressure tells you where the order book weight sits
- depth_against_position = true means the book is stacked against you
- absorption_buy = true means buy side is absorbing (large buy depth, may support longs)
- absorption_sell = true means sell side is absorbing (large sell depth, may support shorts)
- Use depth as SUPPORTING evidence, not as a primary decision driver
- Depth against position + volume spike + reversal candle = strong EXIT signal
- Depth supporting position can increase confidence in HOLD decisions
- If depth data shows "unknown" or "balanced", ignore it — do not fabricate conclusions

CHANGE DETECTION:
- If a "changes_since_last_check" section is provided, pay attention to what shifted
- Rapid PnL deterioration since last check = increase urgency
- Structure state change from healthy to reversing = important signal
- Stop-loss getting closer since last check without recovery = concerning
- If nothing meaningful changed, that supports a HOLD decision

STOP-LOSS RULES (absolute, never violate):
- For LONG trades: new_stop_loss > current_stop_loss AND new_stop_loss < ltp
- For SHORT trades: new_stop_loss < current_stop_loss AND new_stop_loss > ltp
- If you cannot satisfy these constraints, do NOT propose a stop-loss change

BEHAVIORAL RULES:
- Respond ONLY with valid JSON. No markdown, no explanation text.
- Do not use dramatic language in reason fields.
- Be concise and practical.
- Do not fabricate data or factors not present in the input.
- If data is insufficient, default to HOLD with low confidence.
- confidence should reflect how sure you are: 90+ for obvious decisions, 60-80 for judgment calls, below 50 for uncertain situations."""


RISK_AGENT_OUTPUT_SCHEMA = """{
  "decision": "HOLD | TIGHTEN_STOPLOSS | PARTIAL_EXIT | EXIT_NOW",
  "reason_code": "SHORT_MACHINE_READABLE_CODE",
  "primary_reason": "short clear explanation",
  "updated_stop_loss": null or number,
  "exit_fraction": number between 0 and 1,
  "confidence": integer between 0 and 100,
  "thesis_status": "intact | weakening | broken",
  "urgency": "low | medium | high",
  "triggered_factors": ["factor1", "factor2"],
  "risk_flags": ["flag1", "flag2"],
  "monitoring_note": "short follow-up monitoring note"
}"""


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT PAYLOAD BUILDER — sends only decision-grade data to the LLM
# ═══════════════════════════════════════════════════════════════════════════════

def _build_agent_input_payload(
    features: dict,
    depth: dict,
    previous_state: dict = None,
) -> dict:
    """Build a compact, structured input payload for the risk agent.

    Only sends decision-relevant data. No noise, no raw candle dumps.
    Includes delta from previous check cycle when available.
    """
    now_ist = datetime.now(IST)
    hhmm = now_ist.hour * 100 + now_ist.minute
    time_in_trade_seconds = features.get("time_in_trade_seconds", 0)
    minutes_in_trade = int(time_in_trade_seconds // 60)
    hours_in_trade = minutes_in_trade // 60
    remaining_mins = minutes_in_trade % 60

    payload = {
        # Trade identity
        "symbol": features.get("symbol", "UNKNOWN"),
        "trade_mode": features.get("trade_mode", "INTRADAY"),
        "direction": features.get("direction", "BUY"),
        "is_long": features.get("is_long", True),
        "quantity": features.get("quantity", 0),

        # Current price context
        "ltp": features.get("ltp", 0),
        "entry_price": features.get("entry_price", 0),
        "current_stop_loss": features.get("stop_loss", 0),
        "target_price": features.get("target_price", 0),
        "day_high": features.get("day_high", 0),
        "day_low": features.get("day_low", 0),
        "vwap": features.get("vwap", 0),

        # PnL snapshot
        "pnl_percent": features.get("pnl_percent", 0),
        "pnl_rupees_per_share": features.get("pnl_rupees_per_share", 0),
        "pnl_rupees_total": features.get("pnl_rupees_total", 0),

        # Distance metrics
        "distance_from_entry_pct": features.get("distance_from_entry", 0),
        "distance_to_sl_pct": features.get("distance_to_sl", 0),
        "distance_to_target_pct": features.get("distance_to_target", 0),

        # Excursion tracking
        "mfe_pct": features.get("mfe_pct", 0),
        "mae_pct": features.get("mae_pct", 0),

        # Time context
        "time_in_trade": f"{hours_in_trade}h {remaining_mins}m",
        "time_in_trade_seconds": time_in_trade_seconds,
        "current_time_ist": now_ist.strftime("%H:%M IST"),
        "current_hhmm": hhmm,

        # Volume signals
        "relative_volume": features.get("relative_volume", 0),
        "volume_spike_against": features.get("volume_spike_against", False),

        # Structure signals
        "strong_reversal_candle": features.get("strong_reversal_candle", False),
        "structure_state": features.get("structure_state", "unknown"),
        "recent_swing_high": features.get("recent_swing_high", 0),
        "recent_swing_low": features.get("recent_swing_low", 0),

        # Market depth (rich analytics from risk_features)
        "depth_pressure": features.get("depth_pressure", "unknown"),
        "depth_imbalance": features.get("depth_imbalance", 1.0),
        "depth_absorption_buy": features.get("depth_absorption_buy", False),
        "depth_absorption_sell": features.get("depth_absorption_sell", False),
        "depth_against_position": features.get("depth_against_position", False),
    }

    # ── Gap 3: Change detection — delta from previous cycle ───────────────
    if previous_state and isinstance(previous_state, dict):
        prev_features = previous_state.get("_features_snapshot", {})
        prev_decision = previous_state.get("decision", "unknown")

        delta = {}
        # PnL change
        prev_pnl = prev_features.get("pnl_percent") or previous_state.get("pnl_percent", 0)
        curr_pnl = features.get("pnl_percent", 0)
        pnl_shift = round(curr_pnl - prev_pnl, 2) if prev_pnl != 0 else 0
        if pnl_shift != 0:
            delta["pnl_change_since_last"] = pnl_shift

        # LTP change
        prev_ltp = prev_features.get("ltp", 0)
        curr_ltp = features.get("ltp", 0)
        if prev_ltp and prev_ltp > 0 and curr_ltp > 0:
            ltp_shift_pct = round(((curr_ltp - prev_ltp) / prev_ltp) * 100, 2)
            if abs(ltp_shift_pct) >= 0.05:
                delta["ltp_change_pct"] = ltp_shift_pct

        # Structure state change
        prev_structure = prev_features.get("structure_state", "unknown")
        curr_structure = features.get("structure_state", "unknown")
        if prev_structure != curr_structure and prev_structure != "unknown":
            delta["structure_changed"] = f"{prev_structure} -> {curr_structure}"

        # Distance to SL change
        prev_dist_sl = prev_features.get("distance_to_sl", 0)
        curr_dist_sl = features.get("distance_to_sl", 0)
        if prev_dist_sl and curr_dist_sl:
            sl_dist_change = round(curr_dist_sl - prev_dist_sl, 2)
            if abs(sl_dist_change) >= 0.1:
                delta["sl_distance_change_pct"] = sl_dist_change

        # Previous decision context
        delta["previous_decision"] = prev_decision

        if delta:
            payload["changes_since_last_check"] = delta

    return payload


def _build_prompt(payload: dict) -> str:
    """Build the user prompt for the risk agent."""
    return f"""Evaluate the risk for this open trade and decide the appropriate action.

=== TRADE DATA ===
{json.dumps(payload, indent=2)}

=== REQUIRED OUTPUT ===
Respond with ONLY valid JSON in this exact schema:
{RISK_AGENT_OUTPUT_SCHEMA}

Make your decision based on the data above. Be practical and execution-focused."""


# ═══════════════════════════════════════════════════════════════════════════════
# JSON PARSING — robust extraction from LLM response
# ═══════════════════════════════════════════════════════════════════════════════

def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    if text.startswith("json"):
        text = text[4:]
    return text.strip()


def _safe_parse_json(raw_text: str) -> Optional[dict]:
    """Attempt to parse JSON from LLM output, handling common quirks."""
    if not raw_text or not raw_text.strip():
        return None

    text = _strip_markdown_fences(raw_text)

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN LLM CALL
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_risk_with_llm(
    features: dict,
    depth: dict = None,
    previous_state: dict = None,
) -> dict:
    """Call the Gemini risk agent to evaluate an open trade.

    Args:
        features: Output from risk_features.extract_risk_features()
        depth: Market depth data from risk_features.fetch_market_depth()

    Returns:
        Dict with the agent's raw output, plus metadata fields:
        - _source: "gemini_agent4" or "agent4_fallback" or "agent4_parse_error"
        - _model: model name used
        - _raw_response: raw LLM text (for debugging)
        - _latency_ms: LLM call latency
        - _error: error message if any failure occurred

        On any failure, returns a safe HOLD fallback with _source indicating the issue.
    """
    symbol = features.get("symbol", "UNKNOWN")

    # If no Gemini client, return immediately with fallback marker
    if not _client:
        logger.warning(f"{symbol}: Gemini client not available, using fallback")
        return _build_fallback_result(
            reason="LLM client not initialized",
            features=features,
        )

    # Build compact input payload (with delta from previous cycle if available)
    payload = _build_agent_input_payload(features, depth or {}, previous_state)
    prompt = _build_prompt(payload)

    # Call LLM with timeout protection
    start_time = time.time()
    raw_text = ""

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=RISK_AGENT_SYSTEM_PROMPT,
                temperature=0.05,
                max_output_tokens=768,
            ),
        )

        latency_ms = int((time.time() - start_time) * 1000)
        raw_text = response.text.strip() if response.text else ""

        if not raw_text:
            logger.warning(f"{symbol}: Gemini returned empty response")
            return _build_fallback_result(
                reason="LLM returned empty response",
                features=features,
                raw_response=raw_text,
                latency_ms=latency_ms,
            )

        # Parse JSON
        parsed = _safe_parse_json(raw_text)
        if parsed is None:
            logger.warning(f"{symbol}: Failed to parse Gemini JSON response")
            return _build_fallback_result(
                reason="Failed to parse LLM JSON response",
                features=features,
                raw_response=raw_text,
                latency_ms=latency_ms,
                source="agent4_parse_error",
            )

        # Normalize confidence
        conf = parsed.get("confidence", 50)
        try:
            if isinstance(conf, float) and conf <= 1.0:
                parsed["confidence"] = int(conf * 100)
            else:
                parsed["confidence"] = int(conf)
        except (ValueError, TypeError):
            parsed["confidence"] = 50

        # Attach metadata
        parsed["_source"] = "gemini_agent4"
        parsed["_model"] = MODEL_NAME
        parsed["_raw_response"] = raw_text[:500]  # Truncate for storage
        parsed["_latency_ms"] = latency_ms
        parsed["_agent_input"] = payload

        logger.info(
            f"{symbol}: Agent decision={parsed.get('decision', 'UNKNOWN')} "
            f"confidence={parsed.get('confidence', 0)} "
            f"latency={latency_ms}ms"
        )

        return parsed

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(f"{symbol}: Gemini API error: {e}")
        return _build_fallback_result(
            reason=f"LLM API error: {str(e)[:200]}",
            features=features,
            raw_response=raw_text,
            latency_ms=latency_ms,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK — safe default when LLM fails
# ═══════════════════════════════════════════════════════════════════════════════

def _build_fallback_result(
    reason: str,
    features: dict,
    raw_response: str = "",
    latency_ms: int = 0,
    source: str = "agent4_fallback",
) -> dict:
    """Build a safe HOLD result when the LLM call fails.

    The fallback is deliberately conservative: HOLD with low confidence.
    The caller (risk_monitor.py) will then optionally run the deterministic
    rule engine as a secondary decision-maker.
    """
    return {
        "decision": "HOLD",
        "reason_code": "LLM_FALLBACK",
        "primary_reason": f"Agent unavailable: {reason}. Defaulting to safe HOLD.",
        "updated_stop_loss": None,
        "exit_fraction": 0.0,
        "confidence": 25,
        "thesis_status": "intact",
        "urgency": "low",
        "triggered_factors": ["llm_fallback"],
        "risk_flags": ["agent_unavailable"],
        "monitoring_note": "LLM agent was not available. Next cycle should retry.",
        "_source": source,
        "_model": MODEL_NAME or "unknown",
        "_raw_response": raw_response[:500] if raw_response else "",
        "_latency_ms": latency_ms,
        "_error": reason,
    }


def is_agent_available() -> bool:
    """Check if the Gemini risk agent is available for use."""
    return _client is not None and bool(MODEL_NAME)
