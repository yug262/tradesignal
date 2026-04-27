"""Gemini-powered Live Market News Analyzer (Intraday Agent 1+2 combined).

Designed to run every minute during active market hours (09:15-15:30 IST).
Combines Discovery (what happened?) + Confirmation (is there still alpha?)
into a single fast prompt so we can react to breaking news within one minute.

Input:
  - symbol            : NSE symbol (e.g. "TCS")
  - new_news          : list of breaking news articles (just published, impact >= 5)
  - past_news_bundle  : list of earlier news for this symbol today (or None/[])
  - current_price     : live LTP right now (float or None)
  - publish_time_price: LTP at the moment the news was published (float or None)

Output (JSON):
  {
    "what_happened"         : str,   -- Plain English: what the news says happened
    "what_is_confirmed"     : str,   -- Only the hard facts (not speculation)
    "why_news_matters"      : str,   -- Business impact explanation
    "market_bias"           : str,   -- BULLISH | BEARISH | NEUTRAL | MIXED
    "trading_thesis"        : str,   -- The core thesis to trade on (if any)
    "invalidation_logic"    : str,   -- When/why the thesis breaks down
    "market_reacted"        : bool,  -- Has the stock already moved on this news?
    "reaction_magnitude_pct": float, -- % move already absorbed (0 if not reacted)
    "remaining_move_estimate": str,  -- Qualitative assessment of remaining upside/downside
    "should_trade"          : bool,  -- Is there still alpha to capture?
    "trade_reason"          : str,   -- Crisp reason for should_trade decision
    "confidence"            : int    -- 0-100
  }
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("agent.discovery.gemini_live_analyzer")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

IST = timezone(timedelta(hours=5, minutes=30))

_client = None
if GEMINI_API_KEY and GEMINI_API_KEY.strip():
    _client = genai.Client(api_key=GEMINI_API_KEY)


# ── System Instruction ────────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """You are an elite intraday Indian equity analyst operating inside a fully automated trading system.

Your role: Analyze breaking live news during market hours and decide if there is STILL an actionable trading opportunity RIGHT NOW.

KEY PRINCIPLES:
- You receive news the moment it is published. You must judge: has the stock already absorbed this? Is there alpha remaining?
- "confirmed" = explicitly stated in the news. "rumor/speculation" = not confirmed.
- If the stock already moved significantly on this news, the remaining alpha may be low.
- Be extremely precise. Intraday trades need crisp, time-sensitive reasoning.
- Write in clear, direct English. No jargon. No hedging unless warranted.

STRICT RULES:
- Output ONLY valid JSON — no markdown, no preamble, no trailing text.
- market_bias must be one of: BULLISH, BEARISH, NEUTRAL, MIXED
- confidence is an integer 0-100
- If current_price is not provided, you cannot assess market reaction accurately — state that clearly in reaction fields."""


# ── Main Prompt Template ──────────────────────────────────────────────────────

LIVE_ANALYSIS_PROMPT = """You are analyzing live breaking news for {symbol} during active NSE trading hours on {market_date} at {current_time} IST.

=== BREAKING NEWS (just published, high-impact) ===
{new_news_section}

=== PAST NEWS FOR {symbol} TODAY (context / earlier events) ===
{past_news_section}

=== LIVE MARKET DATA ===
Symbol          : {symbol}
Current LTP     : {current_price}
Price at news publish time : {publish_time_price}
Move since news : {move_since_news}

=== YOUR TASK ===

Work through these steps mentally (do NOT output this reasoning):

STEP 1 — WHAT HAPPENED?
Read the breaking news carefully. What is the actual event?

STEP 2 — WHAT IS CONFIRMED vs RUMOR?
Separate confirmed facts (stated clearly in news) from speculation.

STEP 3 — WHY DOES THIS MATTER?
Does this change something real in the business? Revenue, margins, orders, regulation, etc.

STEP 4 — MARKET BIAS
Given the confirmed facts, what is the directional bias? BULLISH / BEARISH / NEUTRAL / MIXED.

STEP 5 — HAS THE MARKET ALREADY REACTED?
Compare current LTP vs publish-time price.
- If current_price and publish_time_price are both available: calculate actual % move.
- If only current_price is available: estimate based on context.
- If neither: state you cannot assess.

STEP 6 — TRADING THESIS
If bias is clear and market hasn't fully absorbed the news, what is the thesis?
Be specific: direction, catalyst, what you're betting on.

STEP 7 — INVALIDATION LOGIC
What would break this thesis? Be specific.

STEP 8 — SHOULD TRADE?
Given the confirmed facts, market bias, and how much move has already happened:
- Is there still meaningful alpha left to capture?
- Is the risk/reward still favorable?
- Decision: should_trade = true only if there is clear, actionable edge remaining.

=== OUTPUT FORMAT ===
Respond ONLY with this exact JSON structure:

{{
  "what_happened": "Plain English explanation of the news event",
  "what_is_confirmed": "Only the hard confirmed facts from the news",
  "why_news_matters": "Why this matters to the business — specific impact",
  "market_bias": "BULLISH | BEARISH | NEUTRAL | MIXED",
  "trading_thesis": "The core thesis to trade on. 'No clear thesis' if none.",
  "invalidation_logic": "What would break this thesis",
  "market_reacted": true,
  "reaction_magnitude_pct": 1.5,
  "remaining_move_estimate": "Qualitative: 'Most of the move is done', 'Significant upside remains', 'Cannot assess', etc.",
  "should_trade": false,
  "trade_reason": "Crisp 1-2 line reason for should_trade decision",
  "confidence": 72
}}"""


# ── Helper: Format News Articles ──────────────────────────────────────────────

def _format_articles(articles: list[dict], label: str) -> str:
    """Format a list of news article dicts into a readable prompt section."""
    if not articles:
        return f"No {label} available."

    lines = []
    for i, art in enumerate(articles[:8], 1):
        published = art.get("published_at", "")
        if isinstance(published, (int, float)) and published > 0:
            try:
                dt = datetime.fromtimestamp(published / 1000, tz=IST)
                published = dt.strftime("%H:%M IST")
            except Exception:
                published = str(published)

        title = art.get("title", "N/A")
        desc = art.get("description", art.get("executive_summary", ""))
        if desc and len(desc) > 250:
            desc = desc[:250] + "..."

        lines.append(
            f"[{i}] Published: {published} | Impact: {art.get('impact_score', 'N/A')}/10\n"
            f"    Title: {title}\n"
            f"    Detail: {desc}"
        )
    return "\n\n".join(lines)


def _format_move(current_price, publish_time_price) -> str:
    """Calculate and describe the price move since news publish time."""
    if current_price is None:
        return "Current price unavailable — cannot assess market reaction"
    if publish_time_price is None or publish_time_price <= 0:
        return f"Publish-time price not available. Current price: ₹{current_price:.2f}"

    move_pct = ((current_price - publish_time_price) / publish_time_price) * 100
    direction = "UP" if move_pct > 0 else "DOWN"
    return (
        f"Rs.{publish_time_price:.2f} -> Rs.{current_price:.2f} "
        f"({direction} {abs(move_pct):.2f}%)"
    )


# ── Main Analysis Function ────────────────────────────────────────────────────

def analyze_live(
    symbol: str,
    new_news: list[dict],
    past_news_bundle: list[dict] | None,
    current_price: float | None,
    publish_time_price: float | None,
) -> dict:
    """
    Run the combined Agent 1+2 live analysis for a breaking news event.

    Args:
        symbol            : NSE stock symbol (e.g. "RELIANCE")
        new_news          : Breaking news articles (just published, impact >= 5)
        past_news_bundle  : Earlier news for this symbol today (for context)
        current_price     : Live LTP right now (float or None)
        publish_time_price: LTP at news publish time (float or None)

    Returns:
        dict with keys: what_happened, what_is_confirmed, why_news_matters,
                        market_bias, trading_thesis, invalidation_logic,
                        market_reacted, reaction_magnitude_pct,
                        remaining_move_estimate, should_trade, trade_reason,
                        confidence, _source, _model
    """
    if not _client:
        logger.warning(f"Gemini API key not configured. Using fallback for {symbol}.")
        return _fallback_analysis(symbol, new_news, current_price, publish_time_price)

    logger.info(f"Starting live analysis for {symbol} with {len(new_news)} breaking news articles...")

    now_ist = datetime.now(IST)
    market_date = now_ist.strftime("%Y-%m-%d")
    current_time = now_ist.strftime("%H:%M")

    new_news_section = _format_articles(new_news, "breaking news")
    past_news_section = _format_articles(past_news_bundle or [], "past news")
    move_since_news = _format_move(current_price, publish_time_price)

    prompt = LIVE_ANALYSIS_PROMPT.format(
        symbol=symbol,
        market_date=market_date,
        current_time=current_time,
        new_news_section=new_news_section,
        past_news_section=past_news_section,
        current_price=f"₹{current_price:.2f}" if current_price else "Not available",
        publish_time_price=f"₹{publish_time_price:.2f}" if publish_time_price else "Not available",
        move_since_news=move_since_news,
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        text = response.text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

        result = json.loads(text)

        # Normalize & clamp confidence
        conf = result.get("confidence", 50)
        try:
            conf = int(float(conf))
            if 0 < conf <= 1:
                conf = int(conf * 100)
        except Exception:
            conf = 50
        result["confidence"] = max(0, min(100, conf))

        # Normalize booleans
        result["market_reacted"] = bool(result.get("market_reacted", False))
        result["should_trade"] = bool(result.get("should_trade", False))

        # Normalize reaction_magnitude_pct
        try:
            result["reaction_magnitude_pct"] = float(result.get("reaction_magnitude_pct", 0.0))
        except Exception:
            result["reaction_magnitude_pct"] = 0.0

        result["_source"] = "gemini_live"
        result["_model"] = MODEL_NAME
        
        logger.info(f"Live analysis for {symbol} completed. should_trade={result['should_trade']}, confidence={result['confidence']}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON for {symbol}: {e}")
        return _fallback_analysis(symbol, new_news, current_price, publish_time_price)
    except Exception as e:
        logger.error(f"Gemini error for {symbol}: {e}")
        return _fallback_analysis(symbol, new_news, current_price, publish_time_price)


# ── Fallback ──────────────────────────────────────────────────────────────────

def _fallback_analysis(
    symbol: str,
    new_news: list[dict],
    current_price: float | None,
    publish_time_price: float | None,
) -> dict:
    """Conservative rule-based fallback when Gemini is unavailable."""
    article_count = len(new_news)
    move_pct = 0.0
    market_reacted = False

    if current_price and publish_time_price and publish_time_price > 0:
        move_pct = ((current_price - publish_time_price) / publish_time_price) * 100
        market_reacted = abs(move_pct) >= 0.5

    return {
        "what_happened": f"Gemini unavailable. {article_count} high-impact article(s) detected for {symbol}.",
        "what_is_confirmed": "Cannot confirm without AI analysis.",
        "why_news_matters": "Cannot assess without AI analysis.",
        "market_bias": "NEUTRAL",
        "trading_thesis": "No clear thesis — Gemini unavailable.",
        "invalidation_logic": "All conditions — Gemini analysis required.",
        "market_reacted": market_reacted,
        "reaction_magnitude_pct": round(move_pct, 2),
        "remaining_move_estimate": "Cannot estimate without AI analysis.",
        "should_trade": False,
        "trade_reason": "Fallback mode — Gemini API unavailable. No trade recommendation.",
        "confidence": 0,
        "_source": "fallback",
        "_model": "rule_engine_only",
    }
