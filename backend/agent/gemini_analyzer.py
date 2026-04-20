"""Gemini-powered Pre-Market Intelligence Analyzer (Agent 1).

Takes news bundles grouped by symbol + rich market context (previous close,
5-day/20-day averages, trend, 52-week range) and produces a watchlist
assessment with directional bias, gap expectations, and confirmation rules.

This is NOT a trade signal generator — it produces intelligence that
Agent 2 will later confirm with live market-open data.
"""

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Create client
_client = None
if GEMINI_API_KEY and GEMINI_API_KEY.strip():
    _client = genai.Client(api_key=GEMINI_API_KEY)


# ── System Instruction ──────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """You are a sharp Indian stock market analyst who explains things in SIMPLE, EASY-TO-READ language.

Your job: Look at overnight news + the stock's recent price history, and tell the trader whether this stock is worth watching today or not.

IMPORTANT — HOW TO WRITE:
- Write like you're explaining to a friend who trades but isn't a finance expert.
- Use simple, short sentences. No jargon. No fancy words.
- Instead of "institutional participation driving momentum" → say "big players are buying, which is pushing the price up"
- Instead of "valuation re-rating catalyst" → say "this news could make people think the stock is worth more"
- Instead of "potential for mean reversion" → say "it has fallen a lot recently, so there's a chance it bounces back"
- Be direct and honest. Say "this is old news, already priced in" or "this is big, the stock will likely react"
- Use everyday Hindi-English trading lingo when it feels natural (gap up, gap down, circuit, volume, etc.)

ANALYSIS RULES:
1. You are NOT giving trade signals (no entry/SL/target). Just tell them if the stock deserves attention today.
2. Be honest. Most news is noise. Only flag stocks where something genuinely important happened.
3. "STALE NO EDGE" is a perfectly fine answer. Old news = no edge. Say it clearly.
4. Tell them if it's a DIRECT hit (the company itself got news) or INDIRECT (sector or market-wide news).
5. Look at the stock's recent trend. If it's already up 15% in 20 days, a bullish news has less room to run.
6. If volume has been high recently, the news might already be partially absorbed.
7. NSE timing: market opens at 9:15 AM, pre-open session 9:00-9:08, circuit limits exist.
8. Respond ONLY with valid JSON. No markdown, no extra text outside JSON."""


# ── Analysis Prompt Template ────────────────────────────────────────────────

ANALYSIS_PROMPT = """Analyze {symbol} ({company_name}) for pre-market intelligence on {market_date}.

=== NEWS BUNDLE ({article_count} articles) ===
{news_section}

=== BUNDLE META ===
Total articles about this stock: {article_count}
Distinct events detected: {distinct_event_count}
Multiple catalysts: {has_multiple_catalysts}
Latest article: {latest_article_time}
Earliest article: {earliest_article_time}

=== MARKET CONTEXT (Previous Session Data) ===
Previous Close: Rs.{previous_close}
Previous Day Open: Rs.{prev_day_open}
Previous Day High: Rs.{prev_day_high}
Previous Day Low: Rs.{prev_day_low}
Previous Day Volume: {prev_day_volume}

Average Volume (5-day): {avg_volume_5d}
Average Volume (20-day): {avg_volume_20d}

Change 1-Day: {change_1d_percent}%
Change 5-Day: {change_5d_percent}%
Change 20-Day: {change_20d_percent}%

Recent Trend: {recent_trend}

Distance from 20-Day High: {distance_from_20d_high_percent}%
Distance from 20-Day Low: {distance_from_20d_low_percent}%

52-Week High: Rs.{w52_high}
52-Week Low: Rs.{w52_low}

=== THINK ABOUT THESE BEFORE ANSWERING ===
1. WHAT HAPPENED: What's the actual news? Is it genuinely new or just rehashed/old stuff?
2. HOW DIRECT: Does this news hit THIS company specifically, or is it a general sector/market thing?
3. HOW FRESH: Was this news published recently enough to move the stock at open? Or is it 12+ hours old?
4. WHERE IS THE STOCK NOW: Is it near its recent highs (less room to go up), near lows (could bounce), or somewhere in between?
5. VOLUME CLUES: Has trading volume been increasing (smart money might be getting in) or drying up?
6. OPENING PREDICTION: Based on the news + where the stock is, will it gap up, gap down, or open flat?
7. WHAT WOULD PROVE YOU WRONG: Under what conditions should the trader ignore this completely?

IMPORTANT: Write ALL text fields in SIMPLE, EASY-TO-UNDERSTAND language. Like you're texting a trader friend.

Respond with this exact JSON structure:
{{
  "decision": "IGNORE" or "WATCH INTRADAY" or "WATCH DELIVERY" or "WATCH BOTH" or "STALE NO EDGE",
  "trade_preference": "INTRADAY" or "DELIVERY" or "BOTH" or "NONE",
  "direction_bias": "BULLISH" or "BEARISH" or "NEUTRAL" or "MIXED",
  "gap_expectation": "LIKELY GAP UP" or "LIKELY GAP DOWN" or "FLAT TO MUTED" or "UNCLEAR",
  "priority": "HIGH" or "MEDIUM" or "LOW",
  "event_summary": "One simple sentence — what happened? Write it so anyone can understand in 3 seconds.",
  "event_strength": "STRONG" or "MODERATE" or "WEAK",
  "directness": "DIRECT" or "INDIRECT" or "WEAK" or "NONE",
  "confidence": 0.0 to 1.0,
  "why_it_matters": "2-3 simple sentences — why should a trader care about this? How does it affect the company's business or stock price? No jargon.",
  "key_drivers": ["simple reason 1 why this could work", "simple reason 2"],
  "risks": ["simple risk 1 — what could go wrong", "simple risk 2"],
  "open_expectation": "2-3 simple sentences — what do you expect to happen when market opens at 9:15? Will it gap up/down? Will there be heavy buying/selling? Keep it conversational.",
  "open_confirmation_needed": ["what to check at market open — e.g. 'stock should open above Rs.150 with high volume'", "another check"],
  "invalid_if": ["when to completely skip this — e.g. 'if it opens flat with no volume, the news is priced in'", "another kill condition"],
  "final_summary": "A short paragraph — talk to the trader like a friend. What should they do? Watch it? Ignore it? What's the bottom line? Keep it real and honest."
}}"""


# ── Helper Functions ────────────────────────────────────────────────────────

def _format_news_section(articles: list[dict]) -> str:
    """Format articles into a readable text block for the prompt."""
    if not articles:
        return "No recent news available."

    lines = []
    for i, art in enumerate(articles[:10], 1):
        sentiment = "unknown"
        raw = art.get("raw_analysis_data")
        if raw:
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}
            if isinstance(raw, dict):
                sentiment = raw.get("sentiment", "unknown")

        published = art.get("published_at", "")
        if isinstance(published, (int, float)) and published > 0:
            from datetime import datetime, timezone, timedelta
            IST = timezone(timedelta(hours=5, minutes=30))
            try:
                dt = datetime.fromtimestamp(published / 1000, tz=IST)
                published = dt.strftime("%Y-%m-%d %H:%M IST")
            except Exception:
                published = str(published)

        title = art.get("title", "N/A")
        desc = art.get("description", art.get("executive_summary", ""))
        if desc and len(desc) > 300:
            desc = desc[:300] + "..."

        lines.append(
            f"[{i}] {title}\n"
            f"    Published: {published}\n"
            f"    Source: {art.get('source', 'N/A')} | "
            f"Category: {art.get('news_category', 'N/A')} | "
            f"Impact: {art.get('impact_score', 'N/A')}/10 | "
            f"Sentiment: {sentiment}\n"
            f"    Detail: {desc}"
        )
    return "\n\n".join(lines)


def _safe_val(val, default="N/A"):
    """Return val formatted or default if None."""
    if val is None:
        return default
    if isinstance(val, float):
        return round(val, 2)
    return val


# ── Main Analysis Function ──────────────────────────────────────────────────

def analyze_stock(
    symbol: str,
    articles: list[dict],
    stock_data: dict,
    market_date: str,
) -> dict:
    """
    Use Gemini to produce a pre-market intelligence assessment.

    Args:
        symbol: NSE stock symbol
        articles: List of news article dicts for this stock
        stock_data: Full market context dict (prev close, volumes, trends)
        market_date: Today's date YYYY-MM-DD

    Returns:
        Dict with the watchlist assessment following AGENT1_OUTPUT_TEMPLATE.
    """
    if not _client:
        return _fallback_analysis(symbol, articles, stock_data)

    news_section = _format_news_section(articles)

    # Build bundle meta
    timestamps = []
    for a in articles:
        pub = a.get("published_at")
        if isinstance(pub, (int, float)) and pub > 0:
            timestamps.append(pub)

    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

    latest_time = "N/A"
    earliest_time = "N/A"
    if timestamps:
        try:
            latest_time = datetime.fromtimestamp(max(timestamps) / 1000, tz=IST).strftime("%Y-%m-%d %H:%M IST")
            earliest_time = datetime.fromtimestamp(min(timestamps) / 1000, tz=IST).strftime("%Y-%m-%d %H:%M IST")
        except Exception:
            pass

    # Detect distinct event types from titles
    titles = [a.get("title", "") for a in articles]
    distinct_events = len(set(t.split(":")[0].strip().lower() for t in titles if t))
    has_multiple = distinct_events >= 2

    # Company name from stock data or symbol
    company_name = stock_data.get("company_name", symbol)

    prompt = ANALYSIS_PROMPT.format(
        symbol=symbol,
        company_name=company_name,
        market_date=market_date,
        article_count=len(articles),
        news_section=news_section,
        distinct_event_count=distinct_events,
        has_multiple_catalysts=has_multiple,
        latest_article_time=latest_time,
        earliest_article_time=earliest_time,
        previous_close=_safe_val(stock_data.get("previous_close", stock_data.get("last_close"))),
        prev_day_open=_safe_val(stock_data.get("prev_day_open")),
        prev_day_high=_safe_val(stock_data.get("prev_day_high", stock_data.get("past_day_high"))),
        prev_day_low=_safe_val(stock_data.get("prev_day_low", stock_data.get("past_day_low"))),
        prev_day_volume=_safe_val(stock_data.get("prev_day_volume")),
        avg_volume_5d=_safe_val(stock_data.get("avg_volume_5d")),
        avg_volume_20d=_safe_val(stock_data.get("avg_volume_20d")),
        change_1d_percent=_safe_val(stock_data.get("change_1d_percent", stock_data.get("current_change_pct"))),
        change_5d_percent=_safe_val(stock_data.get("change_5d_percent")),
        change_20d_percent=_safe_val(stock_data.get("change_20d_percent")),
        recent_trend=_safe_val(stock_data.get("recent_trend")),
        distance_from_20d_high_percent=_safe_val(stock_data.get("distance_from_20d_high_percent")),
        distance_from_20d_low_percent=_safe_val(stock_data.get("distance_from_20d_low_percent")),
        w52_high=_safe_val(stock_data.get("52_week_high")),
        w52_low=_safe_val(stock_data.get("52_week_low")),
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.25,
                max_output_tokens=2048,
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
        return result

    except json.JSONDecodeError as e:
        print(f"  [WARN] Gemini returned invalid JSON for {symbol}: {e}")
        return _fallback_analysis(symbol, articles, stock_data)
    except Exception as e:
        print(f"  [WARN] Gemini API error for {symbol}: {e}")
        return _fallback_analysis(symbol, articles, stock_data)


def _fallback_analysis(symbol: str, articles: list[dict], stock_data: dict) -> dict:
    """Generate a fallback analysis when Gemini is unavailable."""
    return {
        "decision": "STALE NO EDGE",
        "trade_preference": "NONE",
        "direction_bias": "NEUTRAL",
        "gap_expectation": "UNCLEAR",
        "priority": "LOW",
        "event_summary": "Gemini API unavailable — cannot assess event.",
        "event_strength": "WEAK",
        "directness": "NONE",
        "confidence": 0.0,
        "why_it_matters": "Cannot determine without AI reasoning.",
        "key_drivers": [],
        "risks": ["No AI analysis available"],
        "open_expectation": "Cannot predict without analysis.",
        "open_confirmation_needed": [],
        "invalid_if": [],
        "final_summary": "Gemini API was unavailable. This stock requires manual review.",
        "_source": "fallback",
        "_model": "rule_engine_only",
    }
