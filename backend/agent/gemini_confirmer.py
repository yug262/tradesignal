"""Gemini-powered Market Open Confirmation Agent.

Takes Agent 1's pre-market signals and validates them against LIVE market-open
data (9:15-9:20 AM). Compares last close vs open price, gap direction, volume
surge, and first 5-minute price action to CONFIRM / REVISE / INVALIDATE signals.
"""

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Create client
_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    _client = genai.Client(api_key=GEMINI_API_KEY)


CONFIRMATION_SYSTEM_INSTRUCTION = """You are a professional Indian stock market trader analyzing the NSE OPENING SESSION.

The market opened at 9:15 AM IST. You have 5 minutes of live market data.
Your ONLY job is to CONFIRM, REVISE, or INVALIDATE a pre-market trade signal 
generated earlier at 8:30 AM based on news analysis.

RULES:
1. Compare the ACTUAL opening data against the pre-market prediction.
2. Volume is the #1 confirmation signal — high volume = institutional conviction.
3. A gap in the PREDICTED direction with strong volume = CONFIRMED.
4. A gap AGAINST the predicted direction = INVALIDATED (market disagrees with thesis).
5. If the entry price has already been exceeded (stock ran away), REVISE with new levels.
6. If the impact appears already priced-in at open, INVALIDATE.
7. Be DECISIVE. Traders need clear, actionable decisions at 9:20 AM.
8. Respond ONLY with valid JSON. No markdown, no explanation outside the JSON."""


CONFIRMATION_PROMPT = """Analyze the OPENING SESSION for {symbol} on {market_date}.

A pre-market analysis at 8:30 AM produced the following trade signal.
Your job: Is this signal STILL VALID after seeing the actual market open?

=== PRE-MARKET SIGNAL (Agent 1 — 8:30 AM) ===
Signal: {signal_type} ({trade_mode})
Entry Price: Rs.{entry_price}
Stop Loss: Rs.{stop_loss}
Target Price: Rs.{target_price}
Confidence: {confidence}%
Risk/Reward: {risk_reward}x
Pre-Market Reasoning:
{original_reasoning}

=== PREVIOUS DAY DATA ===
Previous Close: Rs.{prev_close}

=== LIVE MARKET-OPEN DATA (9:15 - 9:20 AM) ===
Opening Price: Rs.{open_price}
Current Price (now): Rs.{current_price}
Gap from Previous Close: {gap_pct}%
Today's High (so far): Rs.{today_high}
Today's Low (so far): Rs.{today_low}
Opening Volume: {opening_volume}
Day Change: {change_pct}%

=== CONFIRMATION ANALYSIS CHECKLIST ===
Answer each of these in your reasoning:
1. GAP ANALYSIS: Did the stock gap in the PREDICTED direction? (Up for BUY, Down for SELL)
   - Gap-and-Go: Strong gap with continuation = thesis confirmed
   - Gap-Fill likely: Weak gap, may reverse = thesis weakening
   - Contrary gap: Gapped OPPOSITE to prediction = thesis broken
2. VOLUME CHECK: Is opening volume strong? (Strong volume = institutions are participating)
3. ENTRY ACHIEVABILITY: Is the original entry price still reachable, or has the stock already moved past it?
4. PRICE ACTION: Is the first 5-min candle showing strength (for BUY) or weakness (for SELL)?
5. IMPACT VERDICT: Is the news impact REMAINING (still tradable) or PRICED-IN (already absorbed)?

Based on your analysis, decide ONE of:
- CONFIRMED: The setup is valid. Impact is real and tradable NOW. Keep or tighten parameters.
- REVISED: The thesis holds BUT entry/SL/target need updating based on actual open levels.
- INVALIDATED: The setup is dead. Market disagrees, impact priced-in, or risk too high.

Respond with this exact JSON:
{{
  "decision": "CONFIRMED" or "REVISED" or "INVALIDATED",
  "impact_remaining": true or false,
  "gap_type": "gap_and_go" or "gap_fill_likely" or "flat_open" or "contrary_gap",
  "volume_assessment": "strong" or "average" or "weak",
  "revised_entry": number or null,
  "revised_stop_loss": number or null,
  "revised_target": number or null,
  "revised_confidence": 0.0 to 1.0,
  "revised_signal_type": "BUY" or "SELL" or "NO_TRADE",
  "reasoning": {{
    "gap_assessment": "2-3 sentences on gap direction vs prediction",
    "volume_analysis": "2-3 sentences on volume conviction",
    "price_action": "2-3 sentences on first 5-min candle behavior",
    "entry_check": "Is original entry still achievable? What's the revised level?",
    "impact_verdict": "Is the news impact remaining or priced-in? Why?",
    "final_recommendation": "Clear 1-2 sentence action recommendation for the trader"
  }}
}}"""


def confirm_signal(
    symbol: str,
    original_signal: dict,
    live_stock_data: dict,
    prev_stock_data: dict,
    market_date: str,
) -> dict:
    """
    Use Gemini to confirm/revise/invalidate a pre-market signal
    against live market-open data.

    Args:
        symbol: Stock symbol (e.g., "NBCC")
        original_signal: The Agent 1 signal dict (from DB)
        live_stock_data: Current live price data from Groww API
        prev_stock_data: The stock_snapshot saved by Agent 1 (previous close data)
        market_date: Today's date YYYY-MM-DD

    Returns:
        Confirmation result dict with decision, revised params, and reasoning.
    """
    if not _client:
        return _fallback_confirmation(symbol, original_signal, live_stock_data)

    # Extract original signal fields
    reasoning_obj = original_signal.get("reasoning", {})
    if isinstance(reasoning_obj, str):
        try:
            reasoning_obj = json.loads(reasoning_obj)
        except Exception:
            reasoning_obj = {"summary": reasoning_obj}

    reasoning_text = "\n".join(
        f"  - {k}: {v}" for k, v in reasoning_obj.items()
        if isinstance(v, str)
    ) or "No detailed reasoning available."

    # Previous close from Agent 1's snapshot
    prev_close = (prev_stock_data or {}).get("last_close") or live_stock_data.get("last_close") or 0

    # Calculate gap
    open_price = live_stock_data.get("today_open") or 0
    gap_pct = 0
    if prev_close and prev_close > 0 and open_price:
        gap_pct = round(((open_price - prev_close) / prev_close) * 100, 2)

    prompt = CONFIRMATION_PROMPT.format(
        symbol=symbol,
        market_date=market_date,
        signal_type=original_signal.get("signal_type", "HOLD"),
        trade_mode=original_signal.get("trade_mode", "INTRADAY"),
        entry_price=original_signal.get("entry_price", "N/A"),
        stop_loss=original_signal.get("stop_loss", "N/A"),
        target_price=original_signal.get("target_price", "N/A"),
        confidence=round((original_signal.get("confidence", 0) or 0) * 100, 1),
        risk_reward=original_signal.get("risk_reward", "N/A"),
        original_reasoning=reasoning_text,
        prev_close=prev_close,
        open_price=open_price,
        current_price=live_stock_data.get("today_open") or open_price,  # Best we have at 9:20
        gap_pct=gap_pct,
        today_high=live_stock_data.get("today_high") or "N/A",
        today_low=live_stock_data.get("today_low") or "N/A",
        opening_volume=live_stock_data.get("current_volume") or "N/A",
        change_pct=round(live_stock_data.get("current_change_pct") or 0, 2),
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=CONFIRMATION_SYSTEM_INSTRUCTION,
                temperature=0.2,
                max_output_tokens=1024,
            ),
        )

        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

        result = json.loads(text)
        result["_source"] = "gemini"
        result["_model"] = MODEL_NAME

        # Add the live snapshot for reference
        result["live_snapshot"] = {
            "open_price": open_price,
            "prev_close": prev_close,
            "gap_pct": gap_pct,
            "today_high": live_stock_data.get("today_high"),
            "today_low": live_stock_data.get("today_low"),
            "volume": live_stock_data.get("current_volume"),
            "change_pct": live_stock_data.get("current_change_pct"),
        }

        return result

    except json.JSONDecodeError as e:
        print(f"  [WARN] Gemini returned invalid JSON for {symbol} confirmation: {e}")
        return _fallback_confirmation(symbol, original_signal, live_stock_data)
    except Exception as e:
        print(f"  [WARN] Gemini API error for {symbol} confirmation: {e}")
        return _fallback_confirmation(symbol, original_signal, live_stock_data)


def _fallback_confirmation(symbol: str, original_signal: dict, live_stock_data: dict) -> dict:
    """Generate a fallback confirmation when Gemini is unavailable."""
    return {
        "decision": "CONFIRMED",
        "impact_remaining": True,
        "gap_type": "unknown",
        "volume_assessment": "unknown",
        "revised_entry": original_signal.get("entry_price"),
        "revised_stop_loss": original_signal.get("stop_loss"),
        "revised_target": original_signal.get("target_price"),
        "revised_confidence": original_signal.get("confidence", 0),
        "revised_signal_type": original_signal.get("signal_type", "HOLD"),
        "reasoning": {
            "gap_assessment": "Fallback mode — Gemini API unavailable.",
            "volume_analysis": "Fallback mode — cannot assess volume.",
            "price_action": "Fallback mode — defaulting to CONFIRMED.",
            "entry_check": "Using original entry price.",
            "impact_verdict": "Cannot determine — defaulting to impact remaining.",
            "final_recommendation": "Original signal kept as-is due to API fallback.",
        },
        "_source": "fallback",
        "_model": "none",
    }
