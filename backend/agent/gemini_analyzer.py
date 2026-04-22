"""Gemini-powered Discovery Agent (Agent 1).

Reads news bundles grouped by symbol and produces a pure news-understanding
assessment.  This layer answers ONE question:

    "What actually happened, and does it meaningfully matter?"

It does NOT:
  - predict direction (bullish / bearish)
  - predict gap up / gap down
  - give watchlist or trade advice
  - produce entry / stop / target levels
  - analyse price, chart, volume, or technical structure

Agent 2 (Market Open Confirmation) receives this output and decides whether
the thesis still holds after the actual open.
"""

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Create client once at module load
_client = None
if GEMINI_API_KEY and GEMINI_API_KEY.strip():
    _client = genai.Client(api_key=GEMINI_API_KEY)


# ── System Instruction ───────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """You are a sharp Indian stock market news analyst who explains things in clear, simple, natural English.

Your job is to carefully read news and explain what actually happened and whether it is important for the company.

IMPORTANT — HOW TO WRITE:
- Write like you're explaining to a smart friend who follows markets but is not an expert.
- Use clear, simple sentences. No jargon. No complicated finance terms.
- Keep it natural and human — not robotic, not overly formal.
- Avoid buzzwords and generic phrases.
- Be direct and honest. Say things like:
  - "This is old news, nothing new here"
  - "This is a meaningful development for the company"
  - "This sounds big but does not really change much"

STRICT RULES:
- Do NOT analyze stock price, charts, trend, or volume
- Do NOT predict market movement or gap up/down
- Do NOT give trading advice or signals
- Focus ONLY on the news and its real business impact
- Be realistic — most news is not important

Respond ONLY with valid JSON. No markdown, no extra text."""


# ── Analysis Prompt Template ─────────────────────────────────────────────────

ANALYSIS_PROMPT = """You are a senior Indian equity research analyst. Read the news bundle below and produce a grounded business analysis of what it means for {symbol} ({company_name}) on {market_date}.

Your only source of truth is the news bundle. Do not use outside knowledge. Do not infer facts not clearly stated in the bundle.

<news_bundle articles="{article_count}">
{news_section}
</news_bundle>

<examples>
  <example>
    <input>
      Symbol: DIXON, Company: Dixon Technologies, Date: 2024-11-14
      Bundle (2 articles):
      [1] Dixon Technologies wins a Rs 1,200 crore contract from a global electronics brand to manufacture smartphones under the PLI scheme at its Noida facility. Production begins Q1 FY26.
      [2] Dixon secures large smartphone manufacturing deal worth Rs 1,200 crore under PLI scheme at existing Noida plant.
    </input>
    <o>
      {{
        "event_summary": "Dixon Technologies won a Rs 1,200 crore smartphone manufacturing contract under the PLI scheme, with production starting Q1 FY26.",
        "detailed_explanation": "Dixon has secured a new order to manufacture smartphones for an undisclosed global brand at its Noida facility. Both articles cover the same event. The contract is valued at Rs 1,200 crore and falls under the PLI scheme. Production begins Q1 FY26, so revenue recognition is roughly two quarters away. This directly adds to Dixon's order book and uses existing capacity.",
        "event_type": "corporate_event",
        "event_strength": "STRONG",
        "directness": "DIRECT",
        "is_material": true,
        "impact_analysis": "A Rs 1,200 crore contract is a meaningful addition to Dixon's revenue pipeline. Revenue will flow from Q1 FY26 onward. Using existing Noida capacity limits incremental capex. PLI scheme eligibility may provide margin support through incentive payouts. The main uncertainty is whether volumes are guaranteed or indicative, and the brand is not disclosed.",
        "key_positive_factors": [
          "Rs 1,200 crore contract directly adds to order book",
          "PLI scheme eligibility may provide additional margin support",
          "Uses existing capacity, limiting capex requirement"
        ],
        "key_risks": [
          "Brand identity undisclosed — counterparty risk cannot be assessed",
          "Revenue recognition is 2+ quarters away — execution risk remains"
        ],
        "confidence": 82,
        "final_verdict": "IMPORTANT_EVENT",
        "reasoning_summary": "This is a direct, specific order win with a clear value and timeline. Both articles confirm the same event. The contract is large and material. Only counterparty identity and volume certainty are unknown."
      }}
    </o>
  </example>

  <example>
    <input>
      Symbol: APOLLOHOSP, Company: Apollo Hospitals, Date: 2024-11-14
      Bundle (1 article):
      [1] India's healthcare sector is expected to grow 12% annually over five years, driven by rising insurance penetration and an ageing population, per a CRISIL report.
    </input>
    <o>
      {{
        "event_summary": "CRISIL projects 12% annual growth for India's healthcare sector over five years.",
        "detailed_explanation": "This is a sector-level research report. Apollo Hospitals is not mentioned. The growth drivers cited are general tailwinds that apply across all hospital chains. No company-specific data or development is present in the bundle.",
        "event_type": "sector",
        "event_strength": "WEAK",
        "directness": "INDIRECT",
        "is_material": false,
        "impact_analysis": "No specific impact on Apollo Hospitals can be established. The report is a general industry observation. No change to revenue, margins, capacity, or operations can be derived from this bundle.",
        "key_positive_factors": [],
        "key_risks": [],
        "confidence": 30,
        "final_verdict": "NOISE",
        "reasoning_summary": "Sector research note with no Apollo-specific content. No transmission path to the company's business is described. General industry growth projections are background context, not a business development."
      }}
    </o>
  </example>
</examples>

<reasoning_gates>
Work through these before writing the JSON. Do not output this reasoning.

GATE 1 — EMPTY BUNDLE
If the bundle has no substantive news about {company_name}, output:
{{"event_summary": "No substantive news found.", "detailed_explanation": "The bundle contained no articles with meaningful information about {company_name}.", "event_type": "other", "event_strength": "WEAK", "directness": "NONE", "is_material": false, "impact_analysis": "No impact can be assessed.", "key_positive_factors": [], "key_risks": [], "confidence": 0, "final_verdict": "NOISE", "reasoning_summary": "No news was available to analyze."}}
Stop here.

GATE 2 — DEDUPLICATION AND CONFLICTS
Merge articles covering the same event into one understanding. If two articles contradict each other on a material fact, note the conflict in detailed_explanation, do not assert the disputed fact as certain in impact_analysis, and reduce confidence by at least 20 points.

GATE 3 — DIRECTNESS
- DIRECT = {company_name} is the subject or is explicitly named as affected with specific business consequences stated in the bundle
- INDIRECT = the event affects the sector, macro, peers, or ecosystem — {company_name} may be influenced but no specific transmission is stated
- NONE = no meaningful connection exists

If NONE → set is_material = false, event_strength = "WEAK", final_verdict = "NOISE". Stop. Write the JSON.
INDIRECT events are almost never STRONG.

GATE 4 — MATERIALITY AND STRENGTH
Does this change something real in the company's business? (revenue, margins, costs, capacity, orders, regulation, liquidity, competitive position)
- STRONG = clear, specific, company-relevant development with demonstrable business implications
- MODERATE = real but limited, mixed, or only partially clear
- WEAK = vague, indirect, repetitive, promotional, or low-consequence

If impact is weak, unclear, speculative, or trivial → is_material = false.

GATE 5 — VERDICT
IMPORTANT_EVENT requires all of the following:
- event_strength is STRONG
- is_material is true
- Evidence is concrete, not commentary
- For DIRECT events: the above three conditions are sufficient
- For INDIRECT events: the bundle must also explicitly name {company_name} as affected with clear business consequences

When in doubt, step down. Most news is MODERATE or MINOR. Most market news is NOISE.

CONFIDENCE SCALE
- 85–100 = multiple corroborating articles, specific facts, named figures, clear company attribution
- 65–84 = one solid article with specific details
- 45–64 = one article, some specifics, incomplete or partially unclear
- 25–44 = vague reporting, no concrete details, indirect sourcing
- 0–24 = almost no usable information in the bundle
Reduce by 20 if articles conflict on a material fact.
</reasoning_gates>

<output_contract>
Respond ONLY with a valid JSON object. No markdown. No preamble. No trailing text.
Write all string fields in plain, simple English — no jargon, no hedging, no filler.

{{
  "event_summary": string,
  "detailed_explanation": string,
  "event_type": "corporate_event" | "macro" | "sector" | "regulatory" | "other",
  "event_strength": "STRONG" | "MODERATE" | "WEAK",
  "directness": "DIRECT" | "INDIRECT" | "NONE",
  "is_material": boolean,
  "impact_analysis": string,
  "key_positive_factors": [string],
  "key_risks": [string],
  "confidence": integer,
  "final_verdict": "IMPORTANT_EVENT" | "MODERATE_EVENT" | "MINOR_EVENT" | "NOISE",
  "reasoning_summary": string
}}

Cross-field rules:
- NONE → is_material: false, event_strength: "WEAK", final_verdict: "NOISE"
- is_material: false → final_verdict cannot be "IMPORTANT_EVENT"
- event_strength: "STRONG" → is_material must be true
- key_positive_factors and key_risks: maximum 3 items each
</output_contract>

<hard_prohibitions>
NEVER mention stock price, chart patterns, gap, momentum, volume, VWAP, technical levels, breakout, pullback, support, resistance, or trend.
NEVER predict whether the stock will move up, down, react strongly, or gap.
NEVER use directional market language: "bullish", "bearish", "positive for the stock", "negative for the stock", "market may react".
NEVER give a trading signal, recommendation, watchlist call, or entry/exit opinion.
NEVER fabricate facts, numbers, timelines, or context not present in the bundle.
NEVER produce output belonging to a downstream agent: no scoring, no trade setup, no gap prediction, no watchlist classification.
</hard_prohibitions>"""


# ── Helper Functions ─────────────────────────────────────────────────────────

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


# ── Main Analysis Function ───────────────────────────────────────────────────

def analyze_stock(
    symbol: str,
    articles: list[dict],
    stock_data: dict,
    market_date: str,
) -> dict:
    """
    Use Gemini to produce a pure news-understanding assessment (Discovery Layer).

    Args:
        symbol: NSE stock symbol
        articles: List of news article dicts for this stock
        stock_data: Market context dict — used only for company_name here;
                    price/volume data is NOT injected into the Discovery prompt
        market_date: Today's date YYYY-MM-DD

    Returns:
        Dict conforming to the Discovery output schema:
        {
          event_summary, detailed_explanation, event_type, event_strength,
          freshness, directness, is_material, impact_analysis,
          key_positive_factors, key_risks, confidence,
          final_verdict, reasoning_summary,
          _source, _model
        }
    """
    if not _client:
        return _fallback_analysis(symbol, articles)

    news_section = _format_news_section(articles)

    # Company name for context
    company_name = stock_data.get("company_name", symbol)

    prompt = ANALYSIS_PROMPT.format(
        symbol=symbol,
        company_name=company_name,
        market_date=market_date,
        article_count=len(articles),
        news_section=news_section,
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

        # Normalize confidence to integer 0-100
        conf = result.get("confidence", 0)
        try:
            if isinstance(conf, (float, int)):
                if 0 < conf <= 1.0 and isinstance(conf, float):
                    result["confidence"] = int(conf * 100)
                else:
                    result["confidence"] = int(conf)
            elif isinstance(conf, str):
                result["confidence"] = int(float(conf))
            else:
                result["confidence"] = 50
        except Exception:
            result["confidence"] = 50

        # Clamp confidence
        result["confidence"] = max(0, min(100, result["confidence"]))

        result["_source"] = "gemini"
        result["_model"] = MODEL_NAME
        return result

    except json.JSONDecodeError as e:
        print(f"  [WARN] Gemini returned invalid JSON for {symbol}: {e}")
        return _fallback_analysis(symbol, articles)
    except Exception as e:
        print(f"  [WARN] Gemini API error for {symbol}: {e}")
        return _fallback_analysis(symbol, articles)


def _fallback_analysis(symbol: str, articles: list[dict]) -> dict:
    """
    Rule-based fallback when Gemini is unavailable.

    Returns the same Discovery schema as the Gemini path, defaulting to
    conservative / low-confidence values.  Does NOT include any old
    directional, watchlist, or trade-related fields.
    """
    article_count = len(articles)

    if article_count == 0:
        event_summary = "No news articles found for this symbol."
        event_strength = "WEAK"
        freshness = "OLD"
        directness = "NONE"
        is_material = False
        final_verdict = "NOISE"
        reasoning_summary = (
            "No news was available. Gemini API was also unavailable. "
            "This symbol cannot be assessed without AI reasoning."
        )
    else:
        event_summary = (
            f"Gemini API unavailable — {article_count} article(s) collected but not analyzed."
        )
        event_strength = "WEAK"
        freshness = "FRESH"
        directness = "INDIRECT"
        is_material = False
        final_verdict = "MINOR_EVENT"
        reasoning_summary = (
            "Gemini API was unavailable so the news could not be properly assessed. "
            f"There are {article_count} article(s) in the bundle. "
            "Treat this symbol as unconfirmed until AI analysis is available."
        )

    return {
        "event_summary": event_summary,
        "detailed_explanation": "AI analysis unavailable. Cannot determine what happened without Gemini.",
        "event_type": "other",
        "event_strength": event_strength,
        "freshness": freshness,
        "directness": directness,
        "is_material": is_material,
        "impact_analysis": "Cannot assess business impact without AI reasoning.",
        "key_positive_factors": [],
        "key_risks": ["No AI analysis available — treat as unconfirmed"],
        "confidence": 0,
        "final_verdict": final_verdict,
        "reasoning_summary": reasoning_summary,
        "_source": "fallback",
        "_model": "rule_engine_only",
    }
