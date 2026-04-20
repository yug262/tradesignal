"""Gemini-powered deep analysis for trading signals.

Uses Google Gemini (google-genai SDK) to provide qualitative reasoning
on top of quantitative scores. Falls back gracefully if API key is missing.
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


SYSTEM_INSTRUCTION = """You are an expert Indian stock market analyst specializing in NSE trading.
Your job is to analyze stocks using news events and price action, then provide clear, actionable trading signals.

RULES:
1. Be decisive - give a clear BUY, SELL, or HOLD signal.
2. If the data is insufficient, say HOLD with low confidence.
3. For INTRADAY trades, entry and exit should be achievable within 1 day.
4. For DELIVERY trades, targets can be 1-4 weeks out.
5. Stop-loss must always be tighter than the target (R:R >= 1.5).
6. Consider Indian market specifics: NSE trading hours 9:15-15:30, circuit limits, lot sizes.
7. Respond ONLY with valid JSON. No markdown, no explanation outside the JSON."""


ANALYSIS_PROMPT = """Analyze {symbol} for trading on {market_date}.

=== RECENT NEWS ({num_articles} articles since last market close) ===
{news_section}

=== LIVE PRICE DATA ===
Previous Close: Rs.{last_close}
Today's Open: Rs.{today_open}
Gap: {gap_pct}%
Day High: Rs.{today_high}
Day Low: Rs.{today_low}
Volume: {volume}
52-Week High: Rs.{w52_high}
52-Week Low: Rs.{w52_low}
Day Change: {change_pct}%

=== LOGIC & FEASIBILITY EXPECTATIONS ===
Evaluate if this is a PERFECT, highly accurate setup. If the technicals don't strongly align with the news catalyst, or if there is no strong momentum, reject it (HOLD/NO_TRADE).
You must analyze the deep logical relationship between the news context and the current price gap/volume/volatility.
Only output BUY or SELL if you are highly confident.

Respond with this exact JSON structure:
{{
  "tradable": true or false,
  "signal": "BUY" or "SELL" or "HOLD",
  "trade_mode": "INTRADAY" or "DELIVERY",
  "confidence": 0.0 to 1.0,
  "entry_price": number,
  "stop_loss": number,
  "target_price": number,
  "reasoning": {{
    "news_analysis": "2-3 sentences on how the news impacts this stock",
    "price_analysis": "2-3 sentences on what the price action tells us",
    "why_tradable": "Clear explanation of why this stock IS or IS NOT tradable today",
    "trade_mode_rationale": "Why INTRADAY or DELIVERY is the right approach",
    "risk_factors": ["risk factor 1", "risk factor 2"],
    "key_catalysts": ["catalyst 1", "catalyst 2"]
  }}
}}"""


def _format_news_section(articles: list[dict]) -> str:
    """Format articles into a readable text block for the prompt."""
    if not articles:
        return "No recent news available."

    lines = []
    for i, art in enumerate(articles[:8], 1):
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

        lines.append(
            f"[{i}] {art.get('title', 'N/A')}\n"
            f"    Source: {art.get('source', 'N/A')} | "
            f"Category: {art.get('news_category', 'N/A')} | "
            f"Impact: {art.get('impact_score', 'N/A')}/10 | "
            f"Sentiment: {sentiment}\n"
            f"    Summary: {art.get('executive_summary', art.get('description', 'N/A'))[:200]}"
        )
    return "\n\n".join(lines)


def analyze_stock(
    symbol: str,
    articles: list[dict],
    stock_data: dict,
    market_date: str,
) -> dict:
    """
    Use Gemini to analyze a stock and generate trading reasoning.
    Returns a dict with Gemini's analysis or a fallback if unavailable.
    """
    if not _client:
        return _fallback_analysis(symbol, scores)

    news_section = _format_news_section(articles)

    prompt = ANALYSIS_PROMPT.format(
        symbol=symbol,
        market_date=market_date,
        num_articles=len(articles),
        news_section=news_section,
        last_close=stock_data.get("last_close") or "N/A",
        today_open=stock_data.get("today_open") or "N/A",
        gap_pct=round(stock_data.get("gap_percentage") or 0, 2),
        today_high=stock_data.get("today_high") or "N/A",
        today_low=stock_data.get("today_low") or "N/A",
        volume=stock_data.get("current_volume") or "N/A",
        w52_high=stock_data.get("52_week_high") or "N/A",
        w52_low=stock_data.get("52_week_low") or "N/A",
        change_pct=round(stock_data.get("current_change_pct") or 0, 2),
    )

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.3,
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
        "tradable": False,
        "signal": "HOLD",
        "trade_mode": "INTRADAY",
        "confidence": 0.0,
        "entry_price": stock_data.get("today_open", 0),
        "stop_loss": stock_data.get("today_low", 0),
        "target_price": stock_data.get("today_high", 0),
        "reasoning": {
            "news_analysis": "Fallback mode. Gemini API unavailable.",
            "price_analysis": "Fallback mode. Gemini API unavailable.",
            "why_tradable": "Cannot determine without AI reasoning.",
            "trade_mode_rationale": "Defaulted to INTRADAY.",
            "risk_factors": ["No AI analysis available"],
            "key_catalysts": []
        },
        "_source": "fallback",
        "_model": "rule_engine_only",
    }
