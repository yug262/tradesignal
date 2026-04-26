"""Gemini-powered Discovery Agent (Agent 1) — Stock-Level Event Intelligence Analyst.

INPUT:  one pre-selected stock + bundle_metadata + news_bundle
OUTPUT: per-item news_analysis[] + combined_view

Rules enforced:
  - Does NOT discover stocks / add symbols / expand peers
  - Does NOT give entry, SL, target, position size, RR, or trade execution
  - Passes should_pass_to_agent_2 = true ONLY if combined_trading_thesis is non-empty 
    AND importance != LOW at combined level
"""

import os
import json
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.propagate = False

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_client = None
if GEMINI_API_KEY and GEMINI_API_KEY.strip():
    _client = genai.Client(api_key=GEMINI_API_KEY)


# ── Enum sets for validation ─────────────────────────────────────────────────


VALID_IMPORTANCE = {"LOW", "MEDIUM", "HIGH"}
VALID_BIAS = {"BULLISH", "BEARISH", "MIXED", "NEUTRAL"}
VALID_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}


# ── System Instruction ───────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """You are part of a multi-agent event-driven trading intelligence system for Indian equities.

SYSTEM PURPOSE:
The system converts raw news into actionable trading decisions through a structured pipeline.

Pipeline:
- Agent 1: Event Intelligence (Pre-market analysis)
- Agent 2: Market Confirmation (Post-open validation)
- Agent 3: Execution Planning (Trade decision)
- Risk Agent: Post-trade management

CORE OBJECTIVE:
- Filter noise from news
- Identify meaningful events
- Build a logical trading thesis BEFORE market open
- Validate the thesis AFTER market open
- Execute trades only when both align

IMPORTANT PRINCIPLES:
- No event-type bias (earnings, orders, policy all treated equally)
- Decisions must be logic-driven, not narrative-driven
- Each agent has a strict role and must not overlap responsibilities

DOWNSTREAM DEPENDENCY:
Agent outputs are used by the next agent.
If an agent gives vague or incorrect output, the entire system fails.

Therefore:
- Be precise
- Be structured
- Be logical
- Avoid generic explanations

Your output must be production-grade and usable by downstream agents without interpretation.

You are agent 1 and your job is to analyze the news and provide a trading thesis for the stock.
You do not need to be the most important agent in the system, but you need to be the most logical and well-reasoned. 
You are also the first agent in the pipeline, so if you do not do your job well, the entire system will fail.

Agent 2 must interpret your confidence levels as:
- HIGH   → strong confirmation expected
- MEDIUM → partial confirmation acceptable
- LOW    → ignore / reject
"""


# ── Analysis Prompt ──────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """You are Agent 1: PRE-MARKET EVENT INTELLIGENCE ANALYST.

==================================================
ROLE
==================================================

You analyze overnight news for a single stock and convert it into a structured trading hypothesis.

You are the FIRST FILTER in the system.

Your output will be used by the next agent (Agent 2) to validate your thesis using live market data.

If your reasoning is weak or unclear, the system will fail.

==================================================
PRE-MARKET CONSTRAINT (CRITICAL)
==================================================

All news is from:
previous market close → next day 08:30 (before market open)

This means:
- Market has NOT reacted yet
- No price confirmation exists

STRICT RULES:

NEVER say:
- "price has reacted"
- "move already happened"
- "trend is visible"
- "market confirmed"

ALWAYS use expectation language:
- "may lead to"
- "can trigger"
- "if market reacts"
- "could result in"

==================================================
INPUT UNDERSTANDING
==================================================

You receive:
- One stock
- A bundle of news items
- Bundle metadata

You must:
1. Analyze each news item individually
2. Create one combined stock-level view

==================================================
IMPORTANCE LOGIC
==================================================

You must determine if each news item is meaningful or noise.

Importance must be based on REAL impact mechanisms:

Allowed mechanisms:
- revenue impact
- margin impact
- demand change
- supply change
- regulatory change
- capital allocation (buyback/dividend/capex)
- sentiment shift
- macro linkage

If no clear mechanism:
→ importance must be LOW

==================================================
TRADING THESIS
==================================================

You must create a trading thesis.

Format:
Event → Impact → Expected market behavior

BAD:
"Stock may go up because news is positive"

GOOD:
"Acquisition may improve revenue visibility, which can attract buyers if market reacts positively after open"

==================================================
METADATA USAGE
==================================================

Use bundle metadata to adjust confidence:

- More news → more attention
- Tight time cluster → stronger signal
- Fresh news → more relevant

BUT:
Metadata must NOT create importance.

==================================================
CONFIDENCE DEFINITIONS
==================================================

final_confidence represents:
- strength of the event
- clarity of impact mechanism
- reliability of information

LOW:
- weak signal
- unclear or indirect impact
- noisy or conflicting data

MEDIUM:
- reasonable signal
- clear but not strong impact
- suitable for watchlist

HIGH:
- strong and direct event
- clear impact mechanism
- high confidence in market relevance

==================================================
CONFLICT HANDLING
==================================================

If multiple news items contradict each other:
- final_bias must be MIXED or NEUTRAL
- reduce confidence
- clearly explain the conflict

==================================================
REASONING (MANDATORY)
==================================================

You MUST include structured reasoning in combined_view:

"reasoning": {
  "why_agent_gave_this_view": "",
  "main_driver": "",
  "supporting_points": [],
  "risk_points": [],
  "confidence_reason": "",
  "what_agent_2_should_validate": []
}

RULES:

1. why_agent_gave_this_view:
Explain WHY you selected:
- final_bias
- confidence

2. main_driver:
The single strongest factor driving the view.

3. supporting_points:
Concrete facts from the news.

4. risk_points:
Weaknesses, unknowns, contradictions, or missing data.

5. confidence_reason:
Explain WHY the event is strong/weak and why confidence is LOW/MEDIUM/HIGH based on:
- clarity of impact
- quality of information
- consistency across news

6. what_agent_2_should_validate:
CRITICAL.

Define EXACT market behaviors Agent 2 must check after open.

Examples:
- "Price should gap up after open"
- "Gap should not fully fade"
- "Price should hold above previous close"
- "Volume should support the move"
- "Price should not break below invalidation level"

These must be:
- specific
- testable
- based on market behavior

==================================================
PASSING LOGIC
==================================================

Set should_pass_to_agent_2 = true ONLY if:
- there is a clear trading thesis
- importance is not LOW
- confidence is MEDIUM or HIGH
- no major unresolved contradiction

Otherwise:
should_pass_to_agent_2 = false

==================================================
STRICT CONSTRAINTS
==================================================

- Analyze ONLY the given stock
- Do NOT add or infer other stocks
- Do NOT give entry price
- Do NOT give stop loss
- Do NOT give target
- Do NOT give position sizing
- Do NOT give BUY/SELL decision
- Do NOT assume market reaction has already happened

==================================================
FINAL MENTAL MODEL
==================================================

You are NOT predicting.

You are building a hypothesis:

Event → Impact → Expected Market Reaction

Agent 2 will test your hypothesis.

==================================================
OUTPUT SCHEMA (STRICT)
==================================================

You MUST return output in the following JSON format ONLY.

{
  "stock": {
    "symbol": "string",
    "company_name": "string or null",
    "exchange": "string"
  },
  "news_analysis": [
    {
      "news_number": 1,
      "event_type": "string",
      "what_happened": "string",
      "confirmed_facts": ["string"],
      "unknowns": ["string"],
      "importance": "LOW | MEDIUM | HIGH",
      "importance_reason": "string",
      "impact_mechanism": "string",
      "bias": "BULLISH | BEARISH | MIXED | NEUTRAL",
      "trading_thesis": "string",
      "invalidation": "string",
      "confidence": "LOW | MEDIUM | HIGH"
    }
  ],
  "combined_view": {
    "final_bias": "BULLISH | BEARISH | MIXED | NEUTRAL",
    "final_confidence": "LOW | MEDIUM | HIGH",
    "executive_summary": "string",
    "why_this_stock_is_important_today": "string",
    "combined_trading_thesis": "string",
    "combined_invalidation": "string",
    "key_risks": ["string"],
    "conflict_detected": true,
    "conflict_reason": "string",
    "reasoning": {
      "why_agent_gave_this_view": "string",
      "main_driver": "string",
      "supporting_points": ["string"],
      "risk_points": ["string"],
      "confidence_reason": "string",
      "what_agent_2_should_validate": ["string"]
    },
    "should_pass_to_agent_2": true,
    "pass_reason": "string"
  }
}

==================================================
SCHEMA RULES
==================================================

- news_analysis length must equal input news count
- arrays must always be arrays
- no missing fields
- if should_pass_to_agent_2 = true → validation list must not be empty
- output must be valid JSON only (no extra text)"""


# ── Input Builder ────────────────────────────────────────────────────────────

def build_agent1_input(
    symbol: str,
    exchange: str,
    articles: list[dict],
    company_name: str = None,
) -> dict:
    """
    Build the standardised Agent 1 input contract from raw DB article dicts.

    Returns the full input dict AND the bundle_metadata separately.
    """
    import time
    now_ms = int(time.time() * 1000)
    company_name = company_name or symbol

    # Build news_bundle
    news_bundle = []
    pub_times_ms = []
    for i, art in enumerate(articles[:10], 1):   # cap at 10 items
        pub_ms = art.get("published_at")
        if isinstance(pub_ms, (int, float)) and pub_ms > 0:
            pub_times_ms.append(int(pub_ms))
            pub_iso = _ms_to_iso(int(pub_ms))
        else:
            pub_iso = None

        news_bundle.append({
            "news_number": i,
            "title": art.get("title", ""),
            "description": (art.get("description") or art.get("executive_summary") or "")[:500],
            "source": art.get("source"),
            "published_at": pub_iso,
            "received_at": _ms_to_iso(int(art["analyzed_at"])) if art.get("analyzed_at") else None,
            "prev_agent_view": {},
        })

    # Compute bundle_metadata
    if pub_times_ms:
        latest_ms = max(pub_times_ms)
        oldest_ms = min(pub_times_ms)
        latest_age_min = round((now_ms - latest_ms) / 60_000, 1)
        oldest_age_min = round((now_ms - oldest_ms) / 60_000, 1)
        span_min = round((latest_ms - oldest_ms) / 60_000, 1)
    else:
        latest_age_min = oldest_age_min = span_min = 0

    bundle_metadata = {
        "total_news_count": len(news_bundle),
        "time_span_minutes": span_min,
        "latest_news_age_minutes": latest_age_min,
        "oldest_news_age_minutes": oldest_age_min,
    }

    return {
        "stock": {
            "symbol": symbol,
            "company_name": company_name,
            "exchange": exchange,
        },
        "bundle_metadata": bundle_metadata,
        "news_bundle": news_bundle,
    }, bundle_metadata


def _ms_to_iso(ms: int) -> str:
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    try:
        return datetime.fromtimestamp(ms / 1000, tz=IST).isoformat()
    except Exception:
        return ""


# ── Validator ────────────────────────────────────────────────────────────────

class Agent1ValidationError(ValueError):
    pass


def validate_agent1_output(result: dict, input_data: dict) -> dict:
    """
    Validate Agent 1 output against all schema and behavioral rules.
    Raises Agent1ValidationError with a descriptive message on failure.
    Returns the cleaned result on success.
    """
    errors = []

    # 1. Stock must match input
    input_symbol = input_data.get("stock", {}).get("symbol", "")
    out_symbol = result.get("stock", {}).get("symbol", "")
    if out_symbol.upper() != input_symbol.upper():
        errors.append(f"stock mismatch: input={input_symbol} output={out_symbol}")

    # 2. news_analysis length must match news_bundle length
    expected_count = len(input_data.get("news_bundle", []))
    news_analysis = result.get("news_analysis", [])
    if not isinstance(news_analysis, list):
        errors.append("news_analysis is not a list")
    elif len(news_analysis) != expected_count:
        errors.append(
            f"news_analysis length mismatch: expected {expected_count}, got {len(news_analysis)}"
        )

    # 3. Per-item field validation
    expected_nums = {item["news_number"] for item in input_data.get("news_bundle", [])}
    seen_nums = set()
    for i, item in enumerate(news_analysis if isinstance(news_analysis, list) else []):
        prefix = f"news_analysis[{i}]"

        # Required fields
        for field in ["news_number", "event_type", "what_happened", "importance",
                      "importance_reason", "impact_mechanism", "bias",
                      "trading_thesis", "invalidation", "confidence"]:
            if field not in item:
                errors.append(f"{prefix}: missing field '{field}'")

        # Enum checks
        if item.get("importance") not in VALID_IMPORTANCE:
            errors.append(f"{prefix}: invalid importance '{item.get('importance')}'")
        if item.get("bias") not in VALID_BIAS:
            errors.append(f"{prefix}: invalid bias '{item.get('bias')}'")
        if item.get("confidence") not in VALID_CONFIDENCE:
            errors.append(f"{prefix}: invalid confidence '{item.get('confidence')}'")

        # news_number tracking
        num = item.get("news_number")
        if num is not None:
            seen_nums.add(num)

    # Check news_numbers match
    if isinstance(news_analysis, list) and len(news_analysis) == expected_count:
        if seen_nums != expected_nums:
            missing = expected_nums - seen_nums
            extra = seen_nums - expected_nums
            if missing:
                errors.append(f"news_analysis: missing news_number(s) {missing}")
            if extra:
                errors.append(f"news_analysis: unexpected news_number(s) {extra}")

    # 4. combined_view required fields
    cv = result.get("combined_view", {})
    if not isinstance(cv, dict):
        errors.append("combined_view is missing or not a dict")
    else:
        for field in ["final_bias", "final_confidence",
                      "executive_summary", "why_this_stock_is_important_today",
                      "combined_trading_thesis", "combined_invalidation",
                      "key_risks", "conflict_detected", "conflict_reason",
                      "reasoning", "should_pass_to_agent_2", "pass_reason"]:
            if field not in cv:
                errors.append(f"combined_view: missing field '{field}'")

        if cv.get("final_bias") not in VALID_BIAS:
            errors.append(f"combined_view: invalid final_bias '{cv.get('final_bias')}'")
        if cv.get("final_confidence") not in VALID_CONFIDENCE:
            errors.append(f"combined_view: invalid final_confidence '{cv.get('final_confidence')}'")

        # should_pass rules
        should_pass = cv.get("should_pass_to_agent_2", False)
        thesis = cv.get("combined_trading_thesis", "")
        conf = cv.get("final_confidence", "")
        rsn = cv.get("reasoning", {})
        
        if should_pass:
            if conf == "LOW":
                errors.append(
                    "combined_view: should_pass_to_agent_2=true but final_confidence is LOW"
                )
            if not thesis or not thesis.strip():
                errors.append(
                    "combined_view: should_pass_to_agent_2=true but combined_trading_thesis is empty"
                )
            
            # Step 4: Strictness for HIGH confidence
            if conf == "HIGH":
                main_driver = rsn.get("main_driver", "")
                sup_points = rsn.get("supporting_points", [])
                if not main_driver or not main_driver.strip():
                    errors.append("combined_view: HIGH confidence requires a non-empty reasoning.main_driver")
                if not isinstance(sup_points, list) or len(sup_points) < 1:
                    errors.append("combined_view: HIGH confidence requires at least 1 reasoning.supporting_points")

        # 4b. reasoning block validation
        rsn = cv.get("reasoning", {})
        if not isinstance(rsn, dict):
            errors.append("combined_view.reasoning must be a dict")
        else:
            for req_field in ["why_agent_gave_this_view", "main_driver",
                              "supporting_points", "risk_points",
                              "confidence_reason", "what_agent_2_should_validate"]:
                if req_field not in rsn:
                    errors.append(f"combined_view.reasoning: missing field '{req_field}'")

            if not rsn.get("why_agent_gave_this_view", "").strip():
                errors.append("combined_view.reasoning.why_agent_gave_this_view is empty")
            if not rsn.get("main_driver", "").strip():
                errors.append("combined_view.reasoning.main_driver is empty")
            if not rsn.get("confidence_reason", "").strip():
                errors.append("combined_view.reasoning.confidence_reason is empty")
            if not isinstance(rsn.get("supporting_points"), list):
                errors.append("combined_view.reasoning.supporting_points must be an array")
            if not isinstance(rsn.get("risk_points"), list):
                errors.append("combined_view.reasoning.risk_points must be an array")
            if not isinstance(rsn.get("what_agent_2_should_validate"), list):
                errors.append("combined_view.reasoning.what_agent_2_should_validate must be an array")

            # When passing, what_agent_2_should_validate must be non-empty
            if should_pass and not rsn.get("what_agent_2_should_validate"):
                errors.append(
                    "combined_view.reasoning.what_agent_2_should_validate is empty "
                    "but should_pass_to_agent_2=true"
                )

    if errors:
        raise Agent1ValidationError("; ".join(errors))

    return result


# ── Main Analysis Function ───────────────────────────────────────────────────

def analyze_stock(
    symbol: str,
    articles: list[dict],
    stock_data: dict,
    market_date: str,
) -> dict:
    """
    Agent 1 main entry point.

    Accepts legacy call signature (symbol, articles, stock_data, market_date)
    and internally builds the new structured input contract.

    Returns new-schema output dict.
    """
    exchange = "NSE"
    company_name = stock_data.get("company_name", symbol) if stock_data else symbol

    input_data, bundle_meta = build_agent1_input(
        symbol=symbol,
        exchange=exchange,
        articles=articles,
        company_name=company_name,
    )

    # Log input
    logger.info(
        "[AGENT 1] INPUT | symbol=%s | news_count=%d | latest_age_min=%.1f | oldest_age_min=%.1f",
        symbol,
        bundle_meta["total_news_count"],
        bundle_meta["latest_news_age_minutes"],
        bundle_meta["oldest_news_age_minutes"],
    )

    if not _client:
        logger.warning("[AGENT 1] Gemini client unavailable — using fallback for %s", symbol)
        return _fallback_analysis(input_data)

    prompt = ANALYSIS_PROMPT + "\n\n==================================================\nINPUT DATA\n==================================================\n\n" + json.dumps(input_data, indent=2)

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.1,
                max_output_tokens=2048,
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

        # Validate
        try:
            result = validate_agent1_output(result, input_data)
        except Agent1ValidationError as ve:
            logger.error("[AGENT 1] VALIDATION FAILED for %s: %s", symbol, ve)
            result["_validation_errors"] = str(ve)
            result["_source"] = "gemini_invalid"
            result["_model"] = MODEL_NAME
            return result

        # Attach metadata
        result["_source"] = "gemini"
        result["_model"] = MODEL_NAME

        cv = result.get("combined_view", {})
        rsn = cv.get("reasoning", {})
        logger.info(
            "[AGENT 1] OUTPUT | symbol=%s | final_bias=%s | "
            "final_confidence=%s | should_pass=%s",
            symbol,
            cv.get("final_bias"),
            cv.get("final_confidence"),
            cv.get("should_pass_to_agent_2"),
        )
        logger.info("[AGENT 1] reasoning.main_driver = %s", rsn.get("main_driver", ""))
        logger.info("[AGENT 1] reasoning.confidence_reason = %s", rsn.get("confidence_reason", ""))
        logger.info(
            "[AGENT 1] Agent2 validation checklist count = %d",
            len(rsn.get("what_agent_2_should_validate", [])),
        )

        return result

    except json.JSONDecodeError as e:
        logger.error("[AGENT 1] JSON parse error for %s: %s", symbol, e)
        return _fallback_analysis(input_data)
    except Exception as e:
        logger.error("[AGENT 1] Gemini error for %s: %s", symbol, e)
        return _fallback_analysis(input_data)


# ── Fallback Analysis ────────────────────────────────────────────────────────

def _fallback_analysis(input_data: dict) -> dict:
    """New-schema fallback when Gemini is unavailable."""
    stock = input_data.get("stock", {})
    symbol = stock.get("symbol", "UNKNOWN")
    news_bundle = input_data.get("news_bundle", [])

    news_analysis = []
    for item in news_bundle:
        news_analysis.append({
            "news_number": item.get("news_number", 1),
            "event_type": "other",
            "what_happened": "AI analysis unavailable.",
            "confirmed_facts": [],
            "unknowns": ["All facts unverified — Gemini API unavailable"],
            "importance": "LOW",
            "importance_reason": "Cannot determine — AI fallback only.",
            "impact_mechanism": "unclear",
            "bias": "NEUTRAL",
            "trading_thesis": "",
            "invalidation": "Entire thesis unverified.",
            "confidence": "LOW",
        })

    return {
        "stock": stock,
        "news_analysis": news_analysis,
        "combined_view": {
            "final_bias": "NEUTRAL",
            "final_confidence": "LOW",
            "executive_summary": "Gemini API unavailable or failed. Manual review required.",
            "why_this_stock_is_important_today": "",
            "combined_trading_thesis": "",
            "combined_invalidation": "",
            "key_risks": ["AI analysis unavailable"],
            "conflict_detected": False,
            "conflict_reason": "",
            "reasoning": {
                "why_agent_gave_this_view": "Gemini API unavailable — fallback only, no real analysis performed.",
                "main_driver": "Fallback — no data",
                "supporting_points": [],
                "risk_points": ["AI analysis unavailable"],
                "confidence_reason": "LOW because Gemini API is unavailable and no analysis was performed.",
                "what_agent_2_should_validate": [],
            },
            "should_pass_to_agent_2": False,
            "pass_reason": "Fallback: no AI analysis available.",
        },
        "_source": "fallback",
        "_model": "none",
    }


# ── Compatibility Mapping ────────────────────────────────────────────────────

    # The system now uses the combined_view schema natively across all agents and the frontend.
    return result
