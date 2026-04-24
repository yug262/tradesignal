"""Gemini-powered Market Open Confirmation Agent (Agent 2).

Validates Agent 1's (Discovery) news thesis against LIVE market-open data
collected around 9:20 AM IST.

This layer answers ONE question:
    "After the actual market open, is there still usable edge?"

It does NOT:
  - re-discover or re-interpret the news
  - set entry price, stop loss, or target
  - calculate risk-reward
  - perform detailed execution planning

Agent 2 reads the Discovery output and live price data, then decides:
  - TRADE / NO TRADE
  - direction (BULLISH / BEARISH / NEUTRAL / MIXED)
  - whether the move is still developing or already priced in
  - whether enough edge remains after the open

Agent 3 (Execution Planner) receives the confirmed direction and market context
and turns it into a precise, risk-bounded execution plan.
"""

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Create client once at module load
_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    _client = genai.Client(api_key=GEMINI_API_KEY)


AGENT2_SYSTEM_INSTRUCTION = """You are a market-open confirmation analyst for an Indian trading system.

Your only job is to check whether a pre-market news thesis still holds after the actual market open.

You are not a news discovery agent.
You are not an execution agent.

You must judge:
- whether the opening behavior confirms or weakens the original thesis
- whether the move is still developing or already largely priced in
- whether enough edge remains to justify keeping the idea alive

Focus on:
- gap behavior
- opening strength or weakness
- follow-through or fade
- contradiction vs confirmation
- whether the open supports the thesis or damages it

Use volume only as a supporting clue if it is available.
Do not rely on volume alone.

STRICT RULES:
- Do NOT give entry price
- Do NOT give stop loss
- Do NOT give target
- Do NOT calculate risk-reward
- Do NOT give detailed execution setup
- Do NOT drift back into full news analysis unless needed only to validate the thesis
- Do NOT use robotic or dramatic language

Be skeptical and realistic.
A strong news thesis can still become a bad trade if the opening move already absorbs the impact or clearly contradicts the thesis.

Write in clear, natural, human English.
Be direct, sharp, and practical.

Respond only with valid JSON matching the required schema."""


AGENT2_PROMPT_TEMPLATE = """Analyze the live market open for {symbol} ({company_name}) on {market_date}.

=== INPUT CONTEXT ===
{input_json}

=== TASK ===
Validate the discovery thesis against actual market-open behavior.

Work in this order:

1. DISCOVERY THESIS CHECK
Read the discovery output carefully:
- event_summary
- event_type
- event_strength
- directness
- is_material
- final_verdict
- impact_analysis
- reasoning_summary

First decide whether the discovery layer implies:
- a positive business consequence
- a negative business consequence
- a mixed consequence
- no clear directional consequence

IMPORTANT:
- Do not force BULLISH or BEARISH unless discovery clearly supports it.
- If discovery is mixed, unclear, weak, indirect, or non-material, direction may be NEUTRAL or MIXED.

2. OPEN VALIDATION
Check whether the actual open supports or damages that thesis using:
- gap_percent
- change_percent
- opening_move_quality
- relative_volume if available

Judge whether the opening behavior is:
- confirming
- weakening
- contradicting
- fading
- reversing
- overextended
- unclear

3. PRICED-IN CHECK
Decide whether the move is:
- still developing
- partially priced in
- already largely priced in
- impossible to judge cleanly

A thesis can be correct but no longer tradable if the move is already too extended or mostly absorbed.

4. REMAINING EDGE
Answer this clearly:
Is there still usable edge after the open?

Rules:
- TRADE only if the thesis is still supported AND usable edge remains
- NO TRADE if the move contradicts the thesis, fades badly, becomes too stretched, or the edge is already gone
- Keep directional correctness separate from tradability

5. OUTPUT DISCIPLINE
- Agent 2 confirms or rejects edge
- Agent 2 does NOT plan execution
- Agent 2 does NOT give entry, stop, target, or risk-reward

=== OUTPUT FORMAT ===
Respond with this exact JSON structure:

{{
  "decision": "TRADE | NO TRADE",
  "trade_mode": "INTRADAY | DELIVERY | NONE",
  "direction": "BULLISH | BEARISH | NEUTRAL | MIXED",
  "remaining_impact": "HIGH | MEDIUM | LOW | NONE",
  "priced_in_status": "NOT PRICED IN | PARTIALLY PRICED IN | FULLY PRICED IN | UNCLEAR",
  "priority": "HIGH | MEDIUM | LOW",
  "confidence": 0,
  "why_tradable_or_not": "3-5 lines in clear natural English explaining whether the thesis still holds after the open",
  "key_confirmations": [
    "clear confirmation point 1",
    "clear confirmation point 2"
  ],
  "warning_flags": [
    "clear warning 1",
    "clear warning 2"
  ],
  "invalid_if": [
    "condition that would clearly break the thesis",
    "another condition if relevant"
  ],
  "final_summary": "One sharp sentence summarizing whether the opportunity is still alive or already gone",
  "requested_indicators": [
    {{
      "name": "RSI | SMA | EMA | MACD | BBANDS | ATR | CCI | WILLR",
      "timeframe": "1m | 5m | 15m | 1D",
      "reason": "why Agent 3 needs this indicator for execution validation"
    }}
  ]
}}

=== OUTPUT RULES ===
- If discovery final_verdict is NOISE or is_material is false, decision should usually be NO TRADE unless the live setup shows unusually clear and strong confirmation.
- If direction cannot be grounded from discovery + open, use NEUTRAL or MIXED.
- If opening_move_quality is REVERSING or FADING, be very conservative.
- A large gap can confirm the thesis and still leave NO TRADE if most edge looks already absorbed.
- Do not use dramatic language.
- Do not overstate confidence.

=== REQUESTED INDICATORS RULES ===
- If decision = TRADE, you MUST request 1-4 indicators for Agent 3 execution validation.
- If decision = NO TRADE, requested_indicators MUST be an empty list [].
- Maximum 4 indicators.
- Indicators are used ONLY by Agent 3 for execution safety checks (exhaustion, trend alignment, volatility estimation). Do NOT use indicators to re-analyze the news.
- If trade_mode = INTRADAY, prefer timeframes: 1m, 5m.
- If trade_mode = DELIVERY, prefer timeframe: 1D.
- Choose from: RSI, SMA, EMA, MACD, BBANDS, ATR, CCI, WILLR.
- Each indicator must have a clear reason explaining why Agent 3 needs it.
- Suggested defaults:
  INTRADAY: RSI 1m/5m (exhaustion check), EMA 5m (trend alignment), ATR 5m (volatility for stop placement)
  DELIVERY: RSI 1D (daily exhaustion), EMA 1D (broader trend), MACD 1D (momentum confirmation), ATR 1D (daily volatility)"""


def confirm_signal_v2(
    input_data: dict,
    market_date: str
) -> dict:
    """
    Use Gemini (Agent 2) to confirm or reject a thesis using the Discovery output
    and live market-open context.

    Args:
        input_data: Dict containing:
            - symbol, company_name
            - news_bundle: list of article snippets
            - bundle_meta: article count, timing info
            - discovery: full Agent 1 Discovery output (new schema)
            - live_market_context: open, gap_percent, change_percent, move_quality, etc.
        market_date: Today's date YYYY-MM-DD

    Returns:
        Dict conforming to the Agent 2 output schema:
        {
          decision, trade_mode, direction, remaining_impact,
          priced_in_status, priority, confidence,
          why_tradable_or_not, key_confirmations, warning_flags,
          invalid_if, final_summary, _source, _model
        }
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
            except Exception:
                result["confidence"] = 50

        result["_source"] = "gemini_agent2"
        result["_model"] = MODEL_NAME

        return result

    except Exception as e:
        print(f"  [WARN] Agent 2 Gemini error for {symbol}: {e}")
        return _fallback_confirmation_v2(input_data)


def _fallback_confirmation_v2(input_data: dict) -> dict:
    """
    Conservative rule-based fallback for Agent 2 when Gemini is unavailable.
    Uses Agent 1 discovery output + live market-open context only.
    """

    discovery = input_data.get("discovery", {}) or {}
    context = input_data.get("live_market_context", {}) or {}

    final_verdict = str(discovery.get("final_verdict", "NOISE")).upper()
    event_strength = str(discovery.get("event_strength", "WEAK")).upper()
    is_material = bool(discovery.get("is_material", False))
    directness = str(discovery.get("directness", "NONE")).upper()
    impact_analysis = str(discovery.get("impact_analysis", "")).lower()
    reasoning_summary = str(discovery.get("reasoning_summary", "")).lower()
    event_summary = str(discovery.get("event_summary", "")).lower()

    a1_confidence = discovery.get("confidence", 0)
    try:
        if isinstance(a1_confidence, float) and a1_confidence <= 1.0:
            a1_confidence = int(a1_confidence * 100)
        else:
            a1_confidence = int(a1_confidence)
    except Exception:
        a1_confidence = 0

    gap = float(context.get("gap_percent", 0) or 0)
    change = float(context.get("change_percent", 0) or 0)
    rel_volume = float(context.get("relative_volume", 0) or 0)
    move_quality = str(context.get("opening_move_quality", "UNCLEAR")).upper()

    # --- Step 1: infer directional business consequence conservatively ---
    negative_cues = [
        "penalty", "ban", "fine", "loss", "decline", "cut", "downgrade",
        "margin pressure", "higher cost", "delay", "shutdown", "default",
        "liquidity stress", "investigation", "cancellation", "termination"
    ]
    positive_cues = [
        "order win", "approval", "capacity addition", "fundraise",
        "margin support", "expansion", "growth", "contract", "recovery",
        "restart", "commissioning", "incentive"
    ]

    discovery_text = " ".join([impact_analysis, reasoning_summary, event_summary])

    implied_direction = "NEUTRAL"
    if any(cue in discovery_text for cue in negative_cues):
        implied_direction = "BEARISH"
    elif any(cue in discovery_text for cue in positive_cues):
        implied_direction = "BULLISH"

    if final_verdict in ("NOISE", "MINOR_EVENT") or not is_material or directness == "NONE":
        implied_direction = "NEUTRAL"

    # --- Step 2: immediate kill conditions ---
    decision = "NO TRADE"
    trade_mode = "NONE"
    direction = "NEUTRAL"
    remaining_impact = "LOW"
    priced_in_status = "UNCLEAR"
    priority = "LOW"
    key_confirmations = []
    warning_flags = []
    invalid_if = []
    why = "Fallback mode: insufficient confirmation to keep the idea alive."

    if final_verdict == "NOISE" or not is_material or directness == "NONE":
        why = "Discovery layer does not provide a strong enough business edge basis."
        warning_flags.append("Discovery output is weak, indirect, or non-material")
    elif move_quality in ("REVERSING", "FADING"):
        why = f"Opening move is {move_quality}, so the thesis is not being confirmed cleanly."
        warning_flags.append(f"Opening behavior is {move_quality}")
    else:
        # --- Step 3: validate open against implied direction ---
        bullish_confirm = (
            implied_direction == "BULLISH" and
            (gap > 0.25 or change > 0.40) and
            move_quality in ("STRONG", "HOLDING")
        )

        bearish_confirm = (
            implied_direction == "BEARISH" and
            (gap < -0.25 or change < -0.40) and
            move_quality in ("STRONG", "HOLDING")
        )

        stretched_bull = gap > 4.0 or change > 5.0
        stretched_bear = gap < -4.0 or change < -5.0

        if bullish_confirm:
            direction = "BULLISH"
            key_confirmations.append("Open is aligned with positive implied business consequence")
            key_confirmations.append(f"Opening move quality is {move_quality}")
            if rel_volume > 1.2:
                key_confirmations.append("Relative volume supports the move")

            if stretched_bull:
                decision = "NO TRADE"
                trade_mode = "NONE"
                remaining_impact = "LOW"
                priced_in_status = "FULLY PRICED IN"
                why = "The thesis appears confirmed, but the opening move already looks stretched and much of the edge may be gone."
                warning_flags.append("Move appears overextended after the open")
            else:
                decision = "TRADE"
                trade_mode = "INTRADAY"
                remaining_impact = "MEDIUM" if gap > 2.0 else "HIGH"
                priced_in_status = "PARTIALLY PRICED IN" if gap > 1.5 else "NOT PRICED IN"
                why = "The discovery thesis is being confirmed by the open, and the move still appears to have usable edge."
                priority = "HIGH" if event_strength == "STRONG" else "MEDIUM"
                invalid_if.append("Opening strength fades and price begins to reverse")
                invalid_if.append("Follow-through fails and the move loses confirmation quality")

        elif bearish_confirm:
            direction = "BEARISH"
            key_confirmations.append("Open is aligned with negative implied business consequence")
            key_confirmations.append(f"Opening move quality is {move_quality}")
            if rel_volume > 1.2:
                key_confirmations.append("Relative volume supports the move")

            if stretched_bear:
                decision = "NO TRADE"
                trade_mode = "NONE"
                remaining_impact = "LOW"
                priced_in_status = "FULLY PRICED IN"
                why = "The bearish thesis appears confirmed, but the opening move already looks stretched and much of the edge may be gone."
                warning_flags.append("Down move appears overextended after the open")
            else:
                decision = "TRADE"
                trade_mode = "INTRADAY"
                remaining_impact = "MEDIUM" if gap < -2.0 else "HIGH"
                priced_in_status = "PARTIALLY PRICED IN" if gap < -1.5 else "NOT PRICED IN"
                why = "The discovery thesis is being confirmed by the open, and the downside move still appears to have usable edge."
                priority = "HIGH" if event_strength == "STRONG" else "MEDIUM"
                invalid_if.append("Selling pressure fades and price begins to reverse")
                invalid_if.append("The move stops following through after the open")

        else:
            direction = "MIXED" if implied_direction in ("BULLISH", "BEARISH") else "NEUTRAL"
            decision = "NO TRADE"
            trade_mode = "NONE"
            remaining_impact = "LOW"
            priced_in_status = "UNCLEAR"
            why = "The discovery thesis may exist, but the opening behavior does not confirm it cleanly enough."
            warning_flags.append("Open does not provide strong confirmation")
            invalid_if.append("If the move becomes clearly confirming later, reassess")

    if priority == "LOW":
        priority = "HIGH" if event_strength == "STRONG" and decision == "TRADE" else (
            "MEDIUM" if event_strength in ("STRONG", "MODERATE") else "LOW"
        )

    confidence = max(20, min(85, a1_confidence // 2 + (15 if decision == "TRADE" else 0)))

    # Build requested_indicators based on trade_mode (only if TRADE)
    requested_indicators = []
    if decision == "TRADE":
        if trade_mode == "INTRADAY":
            requested_indicators = [
                {"name": "RSI", "timeframe": "1m", "reason": "Check short-term exhaustion before execution"},
                {"name": "EMA", "timeframe": "1m", "reason": "Check immediate trend alignment"},
                {"name": "ATR", "timeframe": "1m", "reason": "Estimate current volatility for stop placement"},
            ]
        elif trade_mode == "DELIVERY":
            requested_indicators = [
                {"name": "RSI", "timeframe": "1D", "reason": "Check daily exhaustion"},
                {"name": "EMA", "timeframe": "1D", "reason": "Check broader trend"},
                {"name": "MACD", "timeframe": "1D", "reason": "Check momentum confirmation"},
            ]

    return {
        "decision": decision,
        "trade_mode": trade_mode,
        "direction": direction,
        "remaining_impact": remaining_impact,
        "priced_in_status": priced_in_status,
        "priority": priority,
        "confidence": confidence,
        "why_tradable_or_not": why,
        "key_confirmations": key_confirmations[:3],
        "warning_flags": warning_flags[:3] or ["Fallback mode only — Gemini confirmation unavailable"],
        "invalid_if": invalid_if[:3] or ["If price action stops confirming the thesis"],
        "final_summary": f"{decision}: {why}",
        "requested_indicators": requested_indicators,
        "_source": "agent2_fallback",
        "_model": "rule_engine_only",
    }