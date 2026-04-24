import os
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from datetime import timedelta
import httpx

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL")

_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "":
    _client = genai.Client(api_key=GEMINI_API_KEY)


AGENT3_SYSTEM_INSTRUCTION = """You are Agent 3 — the execution proposal layer of a live-money Indian trading system.

Your output may be used by a deterministic risk engine that can place real orders on a broker platform.
Because real capital is at risk, your job is to be conservative, practical, and strict.

Your role:
- convert a validated trade thesis into a concrete execution proposal
- or reject it cleanly if it cannot be executed safely right now

You are NOT:
- a discovery agent
- a market-open validation agent
- a discretionary trader
- the final authority to place a trade

You do NOT:
- re-evaluate whether the news matters
- override Agent 2
- force a trade because the thesis sounds good
- give decorative reasoning

You only answer:
Given Agent 2's output, current live structure, and hard user risk limits, is there a safe and executable trade plan right now?

LIVE-MONEY OPERATING PRINCIPLE:
- A false positive is worse than a missed trade.
- When uncertain, prefer WAIT, AVOID CHASE, or NO TRADE.
- A valid thesis can still be a bad execution.
- A confirmed direction can still be too stretched to enter.
- If structure, sizing, or reward is unclear, reject the trade.

NON-NEGOTIABLE RULES:
- If Agent 2 decision = NO TRADE, you must output NO TRADE.
- If any hard risk constraint fails for the proposed entry, you must not output ENTER NOW.
- If actual risk-reward is below minimum required, you must not output ENTER NOW.
- If position size is 0 shares, you must output NO TRADE.
- If stop loss is on the wrong side of entry, you must output NO TRADE.
- Do not create arbitrary levels without structural logic.
- Do not create a mathematically valid but practically poor trade.
- Do not sound dramatic, aggressive, or overconfident.

EXECUTION DECISION MEANINGS:
- ENTER NOW = immediately executable, structure acceptable, price location acceptable, sizing valid, reward acceptable
- WAIT FOR BREAKOUT = thesis still valid, but entry requires a meaningful structural break first
- WAIT FOR PULLBACK = thesis still valid, but current location is too stretched and a better retrace is needed
- AVOID CHASE = thesis may still be valid, but the move is too extended and most edge is gone
- NO TRADE = Agent 2 rejected it, invalidation is active, structure is broken, hard constraints fail, or execution is unsafe

Write in clear, practical, direct English.
Respond ONLY with valid JSON matching the required schema."""


AGENT3_PROMPT_TEMPLATE = """You are proposing an execution plan for {symbol} ({company_name}).

This is a LIVE-MONEY environment.
Your output may be passed to a broker only after deterministic validation.
Be conservative. Do not force trades.

=== HARD RISK LIMITS (NON-NEGOTIABLE) ===
Total Capital               : Rs.{total_capital}
Max Loss Per Trade          : {max_loss_pct}% of the amount invested (Rs.{max_loss_amount} if fully deployed)
Max Capital Per Trade       : Rs.{max_position_capital} ({max_capital_pct}% of capital)
Min Risk:Reward Required    : {min_rr}:1
Max Daily Loss Budget       : Rs.{max_daily_loss_amount} ({max_daily_loss_pct}% of capital)

=== POSITION SIZING FORMULA — USE EXACTLY ===
BUY:
  risk_per_share = entry_price - stop_loss_price

SELL/SHORT:
  risk_per_share = stop_loss_price - entry_price

max_shares_by_loss    = floor(max_loss_amount / risk_per_share)
max_shares_by_capital = floor(max_position_capital / entry_price)
position_size_shares  = min(max_shares_by_loss, max_shares_by_capital)
position_size_inr     = position_size_shares × entry_price

Do not round up.
Do not approximate.
Do not invent alternate formulas.

=== INPUT DATA ===
{input_json}

=== TASK ===

STEP 0 — MARKET DATA VALIDITY
Use only the latest live_execution_context provided in this request.
Do not rely on earlier agent price context.
If market_status, market_snapshot_time, snapshot_id, or price fields are missing or inconsistent, output NO TRADE.
If market is CLOSED, interpret structure using the latest official closing snapshot only.

STEP 1 — AGENT 2 HARD GATE
Read Agent 2 output first:
- decision
- direction
- trade_mode
- remaining_impact
- priced_in_status
- priority
- warning_flags
- invalid_if
- why_tradable_or_not

Rules:
- If Agent 2 decision = NO TRADE, your output MUST be NO TRADE.
- If any invalid_if condition is already clearly active in current structure, your output MUST be NO TRADE.
- Do not reinterpret a rejected setup as conditional.
- Do not rescue a dead trade.

STEP 1.5 — TECHNICAL INDICATORS (EXECUTION SUPPORT ONLY)
If technical_context is provided in the input, review it as supplementary execution intelligence:
- indicator_values: TA-Lib computed values requested by Agent 2 (RSI, EMA, ATR, MACD, etc.)
- technical_warnings: automated flags from indicator interpretation
- technical_confirmations: automated confirmations from indicator interpretation

Use indicators ONLY to:
- Confirm or flag exhaustion (e.g., RSI overbought = caution for long entry)
- Confirm trend alignment (e.g., price above rising EMA = supportive)
- Estimate volatility for stop placement (e.g., ATR expanding = wider stop needed)
- Avoid chasing (e.g., RSI extreme + stretched price = AVOID CHASE)

Indicators must NOT:
- Override Agent 2 decision (if Agent 2 = NO TRADE, indicators are irrelevant)
- Override hard risk limits or RR validation
- Create a trade on their own — they are supporting evidence only
- Replace structural analysis of price location

STEP 2 — PRICE LOCATION AND STRUCTURE
Evaluate current execution context using:
- ltp
- vwap
- distance_from_vwap_percent
- distance_from_day_high_percent
- distance_from_day_low_percent
- intraday_structure
- opening_move_quality

Classify the current location mentally as one of:
- CLEAN = not stretched, structure intact, entry location acceptable
- STRETCHED = thesis still alive but current location is late or extended
- EXHAUSTED = move largely done, close to day extreme, edge mostly absorbed
- STRUCTURALLY POOR = broken structure, incoherent location, or bad invalidation placement

Rules:
- A valid thesis with STRETCHED or EXHAUSTED location must not become ENTER NOW.
- If price is too far from VWAP or too close to exhaustion, prefer WAIT FOR PULLBACK or AVOID CHASE.
- If structure is poor, prefer NO TRADE.

STEP 3 — CHOOSE EXECUTION DECISION
Choose exactly one:
- ENTER NOW
- WAIT FOR BREAKOUT
- WAIT FOR PULLBACK
- AVOID CHASE
- NO TRADE

Use them this way:
- ENTER NOW only when immediately executable and still offers acceptable edge
- WAIT FOR BREAKOUT when structure needs a clear break first
- WAIT FOR PULLBACK when thesis is intact but current location is poor
- AVOID CHASE when move is too extended and edge is mostly gone
- NO TRADE when Agent 2 rejected it, invalidation is active, constraints fail, or execution is unsafe

STEP 4 — DESIGN LEVELS
Set:
- entry
- stop loss
- target

All three must be structurally justified.

Entry rules:
- Must match the execution decision
- Must not sit inside obvious noise
- Must not assume a price condition that has already passed

Stop loss rules:
- Must clearly invalidate the setup if hit
- Must be on the correct side of entry
- Must not be so tight that normal noise likely hits it immediately
- Must not be so wide that sizing becomes impossible

Target rules:
- Must be realistic for the structure and move context
- Must not be a random round number guess
- Must not be so close that RR falls below minimum
- Must not require perfect execution to be achievable

STEP 5 — HARD RISK GATE
For the proposed plan, verify all of these:

1. stop is on the correct side of entry
2. risk_per_share > 0
3. position_size_shares >= 1
4. max_loss_at_sl <= max_loss_amount
5. position_size_inr <= max_position_capital
6. actual risk_reward >= {min_rr}:1 for ENTER NOW

Rules:
- If actual RR is below minimum required, ENTER NOW is forbidden.
- If position_size_shares = 0, ENTER NOW is forbidden.
- If no structurally valid setup can satisfy these constraints, output NO TRADE.
- If the thesis is still live but current location fails these constraints, prefer WAIT FOR PULLBACK or WAIT FOR BREAKOUT where appropriate.
- If actual risk_reward is below minimum required, WAIT is allowed only if a realistic future entry could satisfy the requirement; otherwise output NO TRADE.

STEP 6 — PRACTICALITY FILTER
Reject any setup that is mathematically possible but practically poor.

Reject or downgrade setups that are:
- too late in the move
- too stretched
- too close to invalidation
- too wide for the user's risk budget
- too weak for the required reward
- too dependent on perfect execution
- already mostly priced in

If the trade passes math but fails practical judgment, output AVOID CHASE or NO TRADE.

=== OUTPUT ===
Respond with exactly this JSON and nothing else:

{{
  "action": "BUY | SELL | WAIT | AVOID",
  "execution_decision": "ENTER NOW | WAIT FOR BREAKOUT | WAIT FOR PULLBACK | AVOID CHASE | NO TRADE",
  "trade_mode": "INTRADAY | DELIVERY | NONE",
  "confidence": <integer 0-100>,
  "entry_plan": {{
    "entry_type": "MARKET | BREAKOUT | PULLBACK | NONE",
    "entry_price": <number>,
    "condition": "<exact condition required to enter>"
  }},
  "stop_loss": {{
    "price": <number>,
    "reason": "<structural basis for this stop>"
  }},
  "target": {{
    "price": <number>,
    "reason": "<structural basis for this target>"
  }},
  "position_sizing": {{
    "position_size_shares": <integer>,
    "position_size_inr": <number>,
    "risk_per_share": <number>,
    "max_loss_at_sl": <number>,
    "capital_used_pct": <number>,
    "sizing_note": "<brief compact summary of which Step 5 checks passed and failed>"
  }},
  "risk_reward": "<e.g. 1:2 | Below minimum>",
  "invalidation": "<exact condition that breaks the setup>",
  "why_now_or_why_wait": "<3-5 sentences in plain English explaining whether the setup is executable now, must wait, should be avoided, or must be rejected>",
  "final_summary": "<one sentence stating the execution verdict>"
}}

=== OUTPUT CONSISTENCY RULES ===

If execution_decision = NO TRADE:
- action = AVOID
- trade_mode = NONE
- entry_type = NONE
- entry_price = 0
- stop_loss.price = 0
- target.price = 0
- position_size_shares = 0

If execution_decision = AVOID CHASE:
- action = AVOID
- do not output ENTER NOW logic

If execution_decision = WAIT FOR BREAKOUT or WAIT FOR PULLBACK:
- action = WAIT
- trade_mode = INTRADAY or DELIVERY only if the thesis is still live
- entry_type must match the wait condition

If execution_decision = ENTER NOW:
- action must be BUY or SELL
- entry_type must not be NONE
- entry_price > 0
- stop_loss.price > 0
- target.price > 0
- position_size_shares >= 1
- risk_reward must meet or exceed {min_rr}:1
- all six Step 5 checks must have passed
- Agent 2 decision must not be NO TRADE

=== BEHAVIORAL RULES ===
- Never re-argue the thesis
- Never output narrative outside the JSON
- Never soften NO TRADE with conditional language
- Never inflate confidence to make a weak setup look acceptable
- If the setup is dead, say so clearly and stop"""
# ---------------------------
# Helpers
# ---------------------------

def _compute_risk_params(risk_config: dict) -> dict:
    capital = float(risk_config.get("capital", 100_000))
    max_loss_pct = float(risk_config.get("max_loss_per_trade_pct", 1.0))
    max_capital_pct = float(risk_config.get("max_capital_per_trade_pct", 20.0))
    min_rr = float(risk_config.get("min_rr", 1.5))
    max_daily_loss_pct = float(risk_config.get("max_daily_loss_pct", 3.0))

    safe_cap_pct = min(max_capital_pct, 50.0)

    return {
        "total_capital": round(capital, 2),
        "max_loss_pct": max_loss_pct,
        "max_loss_amount": round((capital * safe_cap_pct / 100) * max_loss_pct / 100, 2),
        "max_capital_pct": safe_cap_pct,
        "max_position_capital": round(capital * safe_cap_pct / 100, 2),
        "min_rr": min_rr,
        "max_daily_loss_pct": max_daily_loss_pct,
        "max_daily_loss_amount": round(capital * max_daily_loss_pct / 100, 2),
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _compute_position_size(entry: float, stop: float, direction: str, rp: dict) -> dict:
    if entry <= 0 or stop <= 0:
        return {
            "position_size_shares": 0,
            "position_size_inr": 0.0,
            "risk_per_share": 0.0,
            "max_loss_at_sl": 0.0,
            "capital_used_pct": 0.0,
            "sizing_note": "invalid prices"
        }

    if direction == "BULLISH":
        risk_per_share = entry - stop
    else:
        risk_per_share = stop - entry

    if risk_per_share <= 0:
        return {
            "position_size_shares": 0,
            "position_size_inr": 0.0,
            "risk_per_share": 0.0,
            "max_loss_at_sl": 0.0,
            "capital_used_pct": 0.0,
            "sizing_note": "stop on wrong side of entry"
        }

    # Hard check: is the SL distance (%) > user's max loss limit?
    sl_distance_pct = (risk_per_share / entry) * 100
    if sl_distance_pct > rp["max_loss_pct"] + 0.001: # allow tiny float margin
        return {
            "position_size_shares": 0,
            "position_size_inr": 0.0,
            "risk_per_share": round(risk_per_share, 2),
            "max_loss_at_sl": 0.0,
            "capital_used_pct": 0.0,
            "sizing_note": f"REJECTED: SL is {sl_distance_pct:.2f}%, which exceeds {rp['max_loss_pct']}% limit of invested amount"
        }

    max_shares_by_loss = rp["max_loss_amount"] / risk_per_share
    max_shares_by_capital = rp["max_position_capital"] / entry

    shares = math.floor(min(max_shares_by_loss, max_shares_by_capital))
    if shares < 1:
        return {
            "position_size_shares": 0,
            "position_size_inr": 0.0,
            "risk_per_share": round(risk_per_share, 2),
            "max_loss_at_sl": 0.0,
            "capital_used_pct": 0.0,
            "sizing_note": f"risk/share Rs.{risk_per_share:.2f} too wide — 0 shares within limits"
        }

    position_inr = round(shares * entry, 2)
    loss_at_sl = round(shares * risk_per_share, 2)
    cap_used_pct = round(position_inr / rp["total_capital"] * 100, 2)

    return {
        "position_size_shares": shares,
        "position_size_inr": position_inr,
        "risk_per_share": round(risk_per_share, 2),
        "max_loss_at_sl": loss_at_sl,
        "capital_used_pct": cap_used_pct,
        "sizing_note": f"sized by {'loss limit' if max_shares_by_loss < max_shares_by_capital else 'capital limit'}"
    }


def _validate_rr(entry: float, stop: float, target: float, direction: str, min_rr: float) -> tuple[float, bool]:
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


def _blocked_execution(reason: str, rp: dict, source: str = "agent3_precheck") -> dict:
    return {
        "action": "AVOID",
        "execution_decision": "NO TRADE",
        "trade_mode": "NONE",
        "confidence": 0,
        "entry_plan": {
            "entry_type": "NONE",
            "entry_price": 0.0,
            "condition": reason
        },
        "stop_loss": {
            "price": 0.0,
            "reason": "trade blocked"
        },
        "target": {
            "price": 0.0,
            "reason": "trade blocked"
        },
        "position_sizing": {
            "position_size_shares": 0,
            "position_size_inr": 0.0,
            "risk_per_share": 0.0,
            "max_loss_at_sl": 0.0,
            "capital_used_pct": 0.0,
            "sizing_note": reason
        },
        "risk_reward": "N/A",
        "invalidation": reason,
        "why_now_or_why_wait": reason,
        "final_summary": f"NO TRADE: {reason}",
        "_source": source,
        "_risk_params": rp,
    }


def _parse_iso_datetime(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validate_market_snapshot(ctx: dict) -> tuple[bool, str]:
    ltp = _safe_float(ctx.get("ltp"), 0.0)
    market_status = str(ctx.get("market_status", "")).upper().strip()
    snapshot_time = str(ctx.get("market_snapshot_time", "")).strip()
    snapshot_id = str(ctx.get("snapshot_id", "")).strip()

    if ltp <= 0:
        return False, "missing or invalid ltp"

    if not market_status:
        return False, "missing market_status"

    if market_status not in {"OPEN", "CLOSED", "PREOPEN", "HALTED"}:
        return False, f"invalid market_status: {market_status}"

    if not snapshot_time:
        return False, "missing market_snapshot_time"

    if not snapshot_id:
        return False, "missing snapshot_id"

    try:
        snap_dt = _parse_iso_datetime(snapshot_time)
    except Exception:
        return False, "invalid market_snapshot_time format"

    age_sec = (datetime.now(timezone.utc) - snap_dt).total_seconds()

    if market_status == "OPEN" and age_sec > 60:
        return False, f"snapshot too old for open market ({int(age_sec)}s)"
    if market_status == "PREOPEN" and age_sec > 120:
        return False, f"snapshot too old for preopen market ({int(age_sec)}s)"
    if market_status == "CLOSED" and age_sec > 6 * 3600:
        return False, f"snapshot too old for closed market ({int(age_sec)}s)"

    return True, "ok"


def _normalize_result_no_trade(result: dict, reason: str) -> dict:
    result["action"] = "AVOID"
    result["execution_decision"] = "NO TRADE"
    result["trade_mode"] = "NONE"
    result["entry_plan"] = {
        "entry_type": "NONE",
        "entry_price": 0.0,
        "condition": reason
    }
    result["stop_loss"] = {
        "price": 0.0,
        "reason": reason
    }
    result["target"] = {
        "price": 0.0,
        "reason": reason
    }
    result["position_sizing"] = {
        "position_size_shares": 0,
        "position_size_inr": 0.0,
        "risk_per_share": 0.0,
        "max_loss_at_sl": 0.0,
        "capital_used_pct": 0.0,
        "sizing_note": reason
    }
    result["risk_reward"] = "N/A"
    result["invalidation"] = reason
    result["why_now_or_why_wait"] = reason
    result["final_summary"] = f"NO TRADE: {reason}"
    return result


# ---------------------------
# Replace this with your live source
# ---------------------------

IST = timezone(timedelta(hours=5, minutes=30))


def _compute_intraday_structure(ltp: float, day_high: float, day_low: float, vwap: float) -> str:
    if not all(x is not None for x in [ltp, day_high, day_low, vwap]):
        return "UNCLEAR"

    try:
        range_size = max(day_high - day_low, 0.01)

        if ltp >= day_high * 0.999:
            return "BREAKOUT_HIGH"
        if ltp <= day_low * 1.001:
            return "BREAKDOWN_LOW"
        if abs(ltp - vwap) / max(vwap, 0.01) <= 0.003:
            return "VWAP_BALANCED"
        if ltp > vwap and (day_high - ltp) / range_size < 0.25:
            return "UPTREND_HOLDING"
        if ltp < vwap and (ltp - day_low) / range_size < 0.25:
            return "DOWNTREND_HOLDING"
        return "RANGE"
    except Exception:
        return "UNCLEAR"


def _compute_opening_move_quality(
    ltp: float,
    open_price: float,
    day_high: float,
    day_low: float,
    change_percent: float,
    vwap: float,
) -> str:
    if open_price in (None, 0) or ltp is None:
        return "UNCLEAR"

    try:
        move_from_open_pct = ((ltp - open_price) / open_price) * 100
        range_size = max((day_high or ltp) - (day_low or ltp), 0.01)

        if abs(move_from_open_pct) < 0.2 and abs(change_percent or 0) < 0.3:
            return "WEAK"

        if ltp > open_price:
            if ltp >= (day_high or ltp) * 0.998 and (vwap is None or ltp >= vwap):
                return "STRONG"
            if vwap is not None and ltp < vwap:
                return "FADING"
            return "HOLDING"

        if ltp < open_price:
            if ltp <= (day_low or ltp) * 1.002 and (vwap is None or ltp <= vwap):
                return "STRONG"
            if vwap is not None and ltp > vwap:
                return "REVERSING"
            return "HOLDING"

        return "WEAK"
    except Exception:
        return "UNCLEAR"


def fetch_fresh_execution_context(symbol: str) -> dict:
    """
    Fetch fresh execution context every time Agent 3 runs.

    Uses Groww live API as primary source.
    Returns a normalized execution-context payload for Agent 3.
    """
    clean = symbol.replace(".NS", "").strip().upper()

    now_ist = datetime.now(IST)
    market_status = "CLOSED"
    if now_ist.weekday() < 5:
        hhmm = now_ist.hour * 100 + now_ist.minute
        if 915 <= hhmm <= 1530:
            market_status = "OPEN"
        elif 900 <= hhmm < 915:
            market_status = "PREOPEN"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    live_url = (
        f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/"
        f"exchange/NSE/segment/CASH/{clean}/latest"
    )

    with httpx.Client(timeout=10.0, headers=headers) as client:
        res = client.get(live_url)
        res.raise_for_status()
        live = res.json()

    ltp = live.get("ltp")
    if ltp is None:
        # fallback to close if ltp missing
        ltp = live.get("close")

    open_price = live.get("open")
    day_high = live.get("high")
    day_low = live.get("low")
    prev_close = live.get("close")
    volume = live.get("volume")
    change_percent = live.get("dayChangePerc")
    change_amount = live.get("dayChange")

    # Groww payloads can vary. Try common keys for VWAP.
    vwap = (
        live.get("vwap")
        or live.get("averagePrice")
        or live.get("avgPrice")
        or ltp
    )

    distance_from_vwap_percent = None
    distance_from_day_high_percent = None
    distance_from_day_low_percent = None

    try:
        if vwap:
            distance_from_vwap_percent = round(((ltp - vwap) / vwap) * 100, 2)
    except Exception:
        distance_from_vwap_percent = None

    try:
        if day_high:
            distance_from_day_high_percent = round(((day_high - ltp) / day_high) * 100, 2)
    except Exception:
        distance_from_day_high_percent = None

    try:
        if day_low:
            distance_from_day_low_percent = round(((ltp - day_low) / day_low) * 100, 2)
    except Exception:
        distance_from_day_low_percent = None

    intraday_structure = _compute_intraday_structure(
        ltp=ltp,
        day_high=day_high,
        day_low=day_low,
        vwap=vwap,
    )

    opening_move_quality = _compute_opening_move_quality(
        ltp=ltp,
        open_price=open_price,
        day_high=day_high,
        day_low=day_low,
        change_percent=change_percent,
        vwap=vwap,
    )

    snapshot_time = now_ist.isoformat()
    snapshot_id = f"{clean}_{now_ist.strftime('%Y%m%d_%H%M%S')}"

    return {
        "symbol": clean,
        "ltp": round(float(ltp), 2) if ltp is not None else 0.0,
        "open": round(float(open_price), 2) if open_price is not None else 0.0,
        "high": round(float(day_high), 2) if day_high is not None else 0.0,
        "low": round(float(day_low), 2) if day_low is not None else 0.0,
        "previous_close": round(float(prev_close), 2) if prev_close is not None else 0.0,
        "vwap": round(float(vwap), 2) if vwap is not None else 0.0,
        "volume": int(volume) if volume is not None else 0,
        "change_percent": round(float(change_percent), 2) if change_percent is not None else 0.0,
        "change_amount": round(float(change_amount), 2) if change_amount is not None else 0.0,
        "distance_from_vwap_percent": distance_from_vwap_percent,
        "distance_from_day_high_percent": distance_from_day_high_percent,
        "distance_from_day_low_percent": distance_from_day_low_percent,
        "intraday_structure": intraday_structure,
        "opening_move_quality": opening_move_quality,
        "market_status": market_status,
        "market_snapshot_time": snapshot_time,
        "snapshot_id": snapshot_id,
        "quote_source": "groww_live_api",
    }


# ---------------------------
# Main planner
# ---------------------------

def plan_execution(input_data: dict, risk_config: dict = None) -> dict:
    symbol = input_data.get("symbol", "UNKNOWN")
    company_name = input_data.get("company_name", symbol)
    risk_config = risk_config or {}
    rp = _compute_risk_params(risk_config)

    # 1. Always fetch fresh execution context
    try:
        fresh_ctx = fetch_fresh_execution_context(symbol)
    except Exception as e:
        return _blocked_execution(f"fresh execution context fetch failed: {e}", rp, source="agent3_fetch_block")

    ok, reason = _validate_market_snapshot(fresh_ctx)
    if not ok:
        return _blocked_execution(f"invalid market snapshot: {reason}", rp, source="agent3_snapshot_block")

    # 2. Overwrite stale upstream execution context completely
    input_data = dict(input_data)
    input_data["live_execution_context"] = fresh_ctx

    # Optional snapshot consistency check with Agent 2
    agent2_view = input_data.get("agent2_view", {}) or {}
    agent2_snapshot_id = str(agent2_view.get("snapshot_id_used", "")).strip()
    if agent2_snapshot_id:
        if agent2_snapshot_id != str(fresh_ctx.get("snapshot_id", "")).strip():
            # strict mode: block mismatch
            return _blocked_execution(
                f"snapshot mismatch: agent2={agent2_snapshot_id}, agent3={fresh_ctx.get('snapshot_id')}",
                rp,
                source="agent3_snapshot_mismatch"
            )

    # 3. Hard gate: if Agent 2 rejected, block before LLM
    if str(agent2_view.get("decision", "NO TRADE")).upper() == "NO TRADE":
        return _blocked_execution("Agent 2 rejected the trade", rp, source="agent3_agent2_gate")

    # --- LOGGING: [AGENT 3 INPUT] ---
    print(f"==============================")
    print(f"[AGENT 3 INPUT]")
    print(f"==============================")
    print(f"symbol: {symbol}")
    print(f"direction: {agent2_view.get('direction')}")
    print(f"ltp: {fresh_ctx.get('ltp')}")
    print(f"vwap: {fresh_ctx.get('vwap')}")
    print(f"structure: {fresh_ctx.get('intraday_structure')}")
    
    tech_view = input_data.get("technical_context", {})
    ind_vals = tech_view.get("indicator_values", {})
    if ind_vals:
        print(f"\nIndicators summary:")
        for k, v in ind_vals.items():
            status = v.get("interpretation") if v.get("valid") else "INVALID"
            print(f" - {k}: {v.get('latest')} ({status})")
    print(f"==============================\n")

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

        try:
            conf = result.get("confidence", 0)
            if isinstance(conf, float) and conf <= 1.0:
                result["confidence"] = int(conf * 100)
            else:
                result["confidence"] = int(conf)
        except Exception:
            result["confidence"] = 0

        ep = result.get("entry_plan", {}) or {}
        sl = result.get("stop_loss", {}) or {}
        tg = result.get("target", {}) or {}

        direction = str(input_data.get("agent2_view", {}).get("direction", "NEUTRAL")).upper()
        exec_dec = str(result.get("execution_decision", "NO TRADE")).upper()

        entry_price = _safe_float(ep.get("entry_price"), 0.0)
        stop_price = _safe_float(sl.get("price"), 0.0)
        target_price = _safe_float(tg.get("price"), 0.0)

        # Hard pre-block if Agent 2 somehow rejected later
        if str(input_data.get("agent2_view", {}).get("decision", "NO TRADE")).upper() == "NO TRADE":
            result = _normalize_result_no_trade(result, "Agent 2 rejected the trade")
        else:
            # Live plan validation
            if exec_dec == "ENTER NOW":
                if direction not in ("BULLISH", "BEARISH"):
                    result = _normalize_result_no_trade(result, "invalid Agent 2 direction for live entry")
                elif entry_price <= 0 or stop_price <= 0 or target_price <= 0:
                    result = _normalize_result_no_trade(result, "invalid entry/stop/target for live entry")
                else:
                    sizing = _compute_position_size(entry_price, stop_price, direction, rp)
                    actual_rr, meets_min = _validate_rr(entry_price, stop_price, target_price, direction, rp["min_rr"])

                    # hard block if 0 shares
                    if sizing["position_size_shares"] == 0:
                        result = _normalize_result_no_trade(
                            result,
                            f"position sizing failed: {sizing['sizing_note']}"
                        )
                    # hard block if RR below minimum
                    elif not meets_min:
                        result = _normalize_result_no_trade(
                            result,
                            f"trade rejected because actual risk-reward 1:{actual_rr} is below minimum {rp['min_rr']}:1"
                        )
                    else:
                        result["position_sizing"] = sizing
                        result["risk_reward"] = f"1:{actual_rr}"

            elif exec_dec in ("WAIT FOR_PULLBACK", "WAIT FOR BREAKOUT"):
                # typo protection if model messes up
                exec_dec = "WAIT FOR PULLBACK" if "PULLBACK" in exec_dec else "WAIT FOR BREAKOUT"
                result["execution_decision"] = exec_dec

            if exec_dec in ("WAIT FOR PULLBACK", "WAIT FOR BREAKOUT"):
                ltp = _safe_float(input_data.get("live_execution_context", {}).get("ltp"), 0.0)
                if stop_price > 0 and ltp > 0 and direction in ("BULLISH", "BEARISH"):
                    sizing = _compute_position_size(ltp, stop_price, direction, rp)
                    sizing["sizing_note"] = "(projected — valid only when entry condition is met)"
                    result["position_sizing"] = sizing
                else:
                    result["position_sizing"] = {
                        "position_size_shares": 0,
                        "position_size_inr": 0.0,
                        "risk_per_share": 0.0,
                        "max_loss_at_sl": 0.0,
                        "capital_used_pct": 0.0,
                        "sizing_note": "projected sizing unavailable"
                    }

            if exec_dec in ("NO TRADE", "AVOID CHASE"):
                if exec_dec == "NO TRADE":
                    result = _normalize_result_no_trade(
                        result,
                        str(result.get("why_now_or_why_wait") or "execution rejected")
                    )
                else:
                    result["action"] = "AVOID"
                    if "position_sizing" not in result:
                        result["position_sizing"] = {
                            "position_size_shares": 0,
                            "position_size_inr": 0.0,
                            "risk_per_share": 0.0,
                            "max_loss_at_sl": 0.0,
                            "capital_used_pct": 0.0,
                            "sizing_note": "no live entry planned"
                        }

        result["_source"] = "gemini_agent3"
        result["_model"] = MODEL_NAME
        result["_risk_params"] = rp
        result["_live_snapshot_used"] = input_data.get("live_execution_context", {})

        # --- LOGGING: [AGENT 3 DECISION] ---
        print(f"==============================")
        print(f"[AGENT 3 DECISION]")
        print(f"==============================")
        print(f"execution_decision: {exec_dec}")
        print(f"action: {result.get('action', 'WAIT')}")
        print(f"confidence: {result.get('confidence', 0)}")
        
        if exec_dec == "ENTER NOW":
            ps = result.get("position_sizing", {})
            print(f"\nEntry: {entry_price}")
            print(f"SL: {stop_price}")
            print(f"Target: {target_price}")
            print(f"RR: {result.get('risk_reward')}")
            print(f"Shares: {ps.get('position_size_shares')}")
            print(f"Max Loss: Rs.{ps.get('max_loss_at_sl')}")
        else:
            print(f"Reason: {result.get('why_now_or_why_wait')}")
        print(f"==============================\n")

        return result

    except Exception as e:
        print(f"\n[ERROR] Gemini Agent 3 failed: {e}\n")
        return _fallback_execution(input_data, rp, llm_error=str(e))


# ---------------------------
# Fallback planner
# ---------------------------

def _fallback_execution(input_data: dict, rp: dict = None, llm_error: str = "") -> dict:
    if rp is None:
        rp = _compute_risk_params({})

    agent2 = input_data.get("agent2_view", {}) or {}
    ctx = input_data.get("live_execution_context", {}) or {}

    ok, reason = _validate_market_snapshot(ctx)
    if not ok:
        return _blocked_execution(f"fallback blocked: invalid market snapshot: {reason}", rp, source="agent3_fallback_snapshot")

    decision2 = str(agent2.get("decision", "NO TRADE")).upper()
    direction = str(agent2.get("direction", "NEUTRAL")).upper()
    trade_mode = str(agent2.get("trade_mode", "NONE")).upper()

    if decision2 == "NO TRADE":
        return _blocked_execution("fallback blocked: Agent 2 rejected the trade", rp, source="agent3_fallback_agent2")

    # --- LOGGING: [FALLBACK MODE] ---
    print(f"==============================")
    print(f"[FALLBACK MODE]")
    print(f"==============================")
    print(f"reason: Gemini unavailable OR LLM error")
    if llm_error:
        print(f"error: {llm_error}")
    print(f"==============================\n")

    ltp = _safe_float(ctx.get("ltp"), 0.0)
    vwap = _safe_float(ctx.get("vwap"), 0.0)
    move_quality = str(ctx.get("opening_move_quality", "UNCLEAR")).upper()
    intraday_structure = str(ctx.get("intraday_structure", "UNCLEAR")).upper()
    dist_high = _safe_float(ctx.get("distance_from_day_high_percent"), 999.0)
    dist_low = _safe_float(ctx.get("distance_from_day_low_percent"), 999.0)
    dist_vwap = _safe_float(ctx.get("distance_from_vwap_percent"), 999.0)

    action = "AVOID"
    exec_decision = "NO TRADE"
    entry_type = "NONE"
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    reason_text = "fallback rejected: setup not executable safely"

    if direction == "BULLISH":
        # Too stretched or too close to day high -> avoid chase or wait
        if dist_vwap > 2.0 or dist_high < 0.4:
            action = "AVOID" if dist_vwap > 3.0 or dist_high < 0.2 else "WAIT"
            exec_decision = "AVOID CHASE" if action == "AVOID" else "WAIT FOR PULLBACK"
            entry_type = "PULLBACK" if action == "WAIT" else "NONE"
            entry_price = round(vwap, 2) if entry_type == "PULLBACK" and vwap > 0 else 0.0
            reason_text = "fallback: bullish thesis may still be live, but current location is stretched or near exhaustion"
        elif move_quality in ("STRONG", "HOLDING") and abs(dist_vwap) <= 1.0:
            action = "BUY"
            exec_decision = "ENTER NOW"
            entry_type = "MARKET"
            entry_price = ltp
            stop_price = vwap if 0 < vwap < ltp else round(ltp * 0.99, 2)
            target_price = round(ltp + max((ltp - stop_price) * rp["min_rr"], ltp * 0.01), 2)
            reason_text = "fallback: bullish thesis is confirmed and location is still acceptable"
        else:
            action = "WAIT"
            exec_decision = "WAIT FOR BREAKOUT" if intraday_structure in ("RANGE", "CONSOLIDATION") else "WAIT FOR PULLBACK"
            entry_type = "BREAKOUT" if exec_decision == "WAIT FOR BREAKOUT" else "PULLBACK"
            entry_price = round(ltp, 2)
            reason_text = "fallback: bullish thesis may still be valid, but current entry is not clean enough"

    elif direction == "BEARISH":
        if dist_vwap < -2.0 or dist_low < 0.4:
            action = "AVOID" if dist_vwap < -3.0 or dist_low < 0.2 else "WAIT"
            exec_decision = "AVOID CHASE" if action == "AVOID" else "WAIT FOR PULLBACK"
            entry_type = "PULLBACK" if action == "WAIT" else "NONE"
            entry_price = round(vwap, 2) if entry_type == "PULLBACK" and vwap > 0 else 0.0
            reason_text = "fallback: bearish thesis may still be live, but downside move looks stretched"
        elif move_quality in ("STRONG", "HOLDING") and abs(dist_vwap) <= 1.0 and trade_mode == "INTRADAY":
            action = "SELL"
            exec_decision = "ENTER NOW"
            entry_type = "MARKET"
            entry_price = ltp
            stop_price = vwap if vwap > ltp else round(ltp * 1.01, 2)
            target_price = round(ltp - max((stop_price - ltp) * rp["min_rr"], ltp * 0.01), 2)
            reason_text = "fallback: bearish thesis is confirmed and location is still acceptable"
        else:
            action = "WAIT"
            exec_decision = "WAIT FOR PULLBACK"
            entry_type = "PULLBACK"
            entry_price = round(vwap, 2) if vwap > 0 else round(ltp * 1.01, 2)
            reason_text = "fallback: bearish thesis may still be valid, but current entry is not clean enough"

    # Risk validation for fallback
    if exec_decision == "ENTER NOW":
        sizing = _compute_position_size(entry_price, stop_price, direction, rp)
        actual_rr, meets = _validate_rr(entry_price, stop_price, target_price, direction, rp["min_rr"])

        if sizing["position_size_shares"] == 0:
            return _blocked_execution(
                f"fallback blocked: {sizing['sizing_note']}",
                rp,
                source="agent3_fallback_sizing"
            )

        if not meets:
            return _blocked_execution(
                f"fallback blocked: actual risk-reward 1:{actual_rr} below minimum {rp['min_rr']}:1",
                rp,
                source="agent3_fallback_rr"
            )

        risk_reward = f"1:{actual_rr}"
        position_sizing = sizing
    else:
        risk_reward = "N/A" if exec_decision in ("NO TRADE", "AVOID CHASE") else "Projected"
        position_sizing = {
            "position_size_shares": 0,
            "position_size_inr": 0.0,
            "risk_per_share": 0.0,
            "max_loss_at_sl": 0.0,
            "capital_used_pct": 0.0,
            "sizing_note": "no live entry planned"
        }

    confidence = 0
    try:
        a2_conf = agent2.get("confidence", 0)
        confidence = int(float(a2_conf) * 100) if isinstance(a2_conf, float) and a2_conf <= 1.0 else int(a2_conf or 0)
    except Exception:
        confidence = 0

    result = {
        "action": action,
        "execution_decision": exec_decision,
        "trade_mode": trade_mode if exec_decision not in ("NO TRADE",) else "NONE",
        "confidence": confidence,
        "entry_plan": {
            "entry_type": entry_type,
            "entry_price": round(entry_price, 2),
            "condition": reason_text
        },
        "stop_loss": {
            "price": round(stop_price, 2),
            "reason": "fallback structural stop"
        },
        "target": {
            "price": round(target_price, 2),
            "reason": "fallback structural target"
        },
        "position_sizing": position_sizing,
        "risk_reward": risk_reward,
        "invalidation": "if price breaks the structure used for this setup",
        "why_now_or_why_wait": reason_text + (f" | llm_error={llm_error}" if llm_error else ""),
        "final_summary": f"Fallback execution: {exec_decision}",
        "_source": "agent3_fallback",
        "_risk_params": rp,
        "_live_snapshot_used": ctx,
    }

    if exec_decision == "NO TRADE":
        result = _normalize_result_no_trade(result, reason_text)

    # --- LOGGING: [AGENT 3 DECISION] (FALLBACK) ---
    print(f"==============================")
    print(f"[AGENT 3 DECISION] (FALLBACK)")
    print(f"==============================")
    print(f"execution_decision: {exec_decision}")
    print(f"action: {action}")
    print(f"confidence: {result.get('confidence', 0)}")
    
    if exec_decision == "ENTER NOW":
        ps = result.get("position_sizing", {})
        print(f"\nEntry: {entry_price}")
        print(f"SL: {stop_price}")
        print(f"Target: {target_price}")
        print(f"RR: {result.get('risk_reward')}")
        print(f"Shares: {ps.get('position_size_shares')}")
        print(f"Max Loss: Rs.{ps.get('max_loss_at_sl')}")
    else:
        print(f"Reason: {reason_text}")
    print(f"==============================\n")

    return result

def _blocked_execution(reason: str, rp: dict, source: str) -> dict:
    result = {
        "action": "AVOID",
        "execution_decision": "NO TRADE",
        "confidence": 0,
        "why_now_or_why_wait": reason,
        "_source": source,
        "_risk_params": rp,
    }
    
    # --- LOGGING: [TRADE BLOCKED] ---
    print(f"==============================")
    print(f"[TRADE BLOCKED]")
    print(f"==============================")
    print(f"Reason: {reason}")
    print(f"Source: {source}")
    print(f"==============================\n")
    
    return result