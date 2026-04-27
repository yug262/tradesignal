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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL")

_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "":
    _client = genai.Client(api_key=GEMINI_API_KEY)


AGENT3_SYSTEM_INSTRUCTION = """You are Agent 3 -- the Execution Planner in a multi-agent Indian equities trading system.

YOUR SOLE PURPOSE:
Convert validated intelligence from upstream agents into a precise, executable trade plan.
Or reject it cleanly if execution is unsafe.

YOU MUST NOT:
- Re-analyze or re-interpret news (Agent 1 already did this)
- Redo technical analysis or compute indicators (Agent 2.5 already did this)
- Override Agent 2 or Agent 2.5 conclusions
- Perform post-entry monitoring, trailing stops, or profit locking (Risk Agent handles this)
- Generate narrative or commentary outside the JSON schema
- Force a trade because the thesis sounds good

YOU ONLY ANSWER:
Given the upstream agent outputs, live market context, and hard risk limits --
is there a safe and executable trade plan RIGHT NOW?

OPERATING PRINCIPLE:
A false positive is worse than a missed trade.
When uncertain, prefer WAIT or AVOID over ENTER_NOW.
A valid thesis can still be a bad execution.

DECISION VALUES:
- ENTER_NOW: immediately executable, structure clean, sizing valid, RR acceptable
- WAIT_FOR_PULLBACK: thesis alive but price location is stretched, need retrace
- WAIT_FOR_BREAKOUT: thesis alive but structure needs a clear break first
- AVOID: rejected -- constraints fail, structure broken, contradictions present, or unsafe

Respond ONLY with valid JSON matching the required V2 schema. No other text."""


AGENT3_PROMPT_TEMPLATE = """You are proposing an execution plan for {symbol} ({company_name}).

This is a LIVE-MONEY environment. Be conservative. Do not force trades.

=== HARD RISK LIMITS (NON-NEGOTIABLE) ===
Total Capital               : Rs.{total_capital}
Max Loss Per Trade          : {max_loss_pct}% (Rs.{max_loss_amount})
Max Capital Per Trade       : Rs.{max_position_capital} ({max_capital_pct}% of capital)
Min Risk:Reward Required    : {min_rr}:1
Max Daily Loss Budget       : Rs.{max_daily_loss_amount} ({max_daily_loss_pct}% of capital)

=== POSITION SIZING FORMULA -- USE EXACTLY ===
LONG (BUY):
  risk_per_share = entry_price - stop_loss
SHORT (SELL):
  risk_per_share = stop_loss - entry_price

max_shares_by_loss    = floor(max_loss_amount / risk_per_share)
max_shares_by_capital = floor(max_position_capital / entry_price)
quantity              = min(max_shares_by_loss, max_shares_by_capital)
capital_used          = quantity * entry_price
risk_amount           = quantity * risk_per_share

Do not round up. Do not approximate. Do not invent alternate formulas.

=== INPUT DATA ===
{input_json}

=== DECISION PRIORITY (MANDATORY ORDER) ===

You MUST evaluate in this exact order. Stop at the first failing gate.

STEP 1 -- AGENT 2 GATE
Read agent2_view:
- If decision.should_pass_to_agent_3 is false -> AVOID
- If validation.status is not CONFIRMED -> AVOID
- If decision.agent_3_instruction = DO_NOT_PROCEED -> AVOID
Do NOT reinterpret. Do NOT rescue a rejected trade.

STEP 2 -- AGENT 2.5 GATE (if agent25_technical_analysis exists)
Read agent25_technical_analysis.technical_analysis:
- If agent_3_handoff.technical_go_no_go = NO_GO -> AVOID
- If agent_3_handoff.technical_go_no_go = WAIT -> WAIT_FOR_PULLBACK or WAIT_FOR_BREAKOUT
- If overall.trade_readiness = AVOID -> AVOID
- If overall.execution_support = NO_SUPPORT -> AVOID
Do NOT redo technical analysis. Accept Agent 2.5 conclusions as given.

STEP 3 -- BIAS ALIGNMENT
Compare:
- Agent 1 final_bias (from agent2_view.agent_1_view)
- Agent 2.5 overall.technical_bias (if available)
If direct contradiction (BULLISH vs BEARISH with strong confidence) -> AVOID
If weak contradiction -> WAIT_FOR_PULLBACK

STEP 4 -- ENTRY FEASIBILITY
Using live_execution_context, evaluate current price location:
- ltp, vwap, distance_from_vwap_percent
- distance_from_day_high_percent, distance_from_day_low_percent
- intraday_structure, opening_move_quality

ENTER_NOW only when:
- Location is clean (not stretched, not near exhaustion)
- Structure supports immediate entry
- Agent 2.5 technical_go_no_go = GO (or absent)
- Agent 2.5 execution_support = STRONG_SUPPORT or MODERATE_SUPPORT

WAIT if:
- Thesis alive but location stretched or structure needs confirmation

AVOID if:
- Move largely done, structure broken, or edge absorbed

STEP 5 -- RISK GATE
For ENTER_NOW proposals, verify ALL of these:
1. stop_loss on correct side of entry_price
2. risk_per_share > 0
3. quantity >= 1
4. risk_amount <= max_loss_amount (Rs.{max_loss_amount})
5. capital_used <= max_position_capital (Rs.{max_position_capital})
6. risk_reward >= {min_rr}

If any check fails:
- If thesis is still live, downgrade to WAIT
- If thesis is dead, output AVOID

=== OUTPUT SCHEMA (V2) ===
Respond with EXACTLY this JSON and nothing else:

{{
  "stock": {{
    "symbol": "{symbol}",
    "exchange": "NSE"
  }},
  "execution_decision": {{
    "action": "ENTER_NOW | WAIT_FOR_PULLBACK | WAIT_FOR_BREAKOUT | AVOID",
    "trade_mode": "INTRADAY | DELIVERY | NONE",
    "direction": "LONG | SHORT | NONE",
    "confidence": "LOW | MEDIUM | HIGH",
    "reason": "<3-5 sentences explaining the execution verdict>"
  }},
  "trade_plan": {{
    "entry_price": <number>,
    "stop_loss": <number>,
    "target_price": <number>,
    "risk_reward": <number>,
    "invalidation": "<exact condition that breaks the setup>",
    "plan_notes": "<one sentence execution verdict>"
  }},
  "position_sizing": {{
    "quantity": <integer>,
    "capital_used": <number>,
    "risk_amount": <number>,
    "risk_per_share": <number>
  }},
  "order_payload": {{
    "transaction_type": "BUY | SELL | NONE",
    "product": "INTRADAY | DELIVERY | NONE",
    "quantity": <integer>,
    "order_type": "MARKET | LIMIT | NONE",
    "price": <number>
  }}
}}

=== OUTPUT CONSISTENCY RULES ===

If action = AVOID:
- direction = NONE, trade_mode = NONE
- All prices = 0, risk_reward = 0, quantity = 0
- order_payload: transaction_type = NONE, product = NONE, order_type = NONE, quantity = 0, price = 0

If action = WAIT_FOR_PULLBACK or WAIT_FOR_BREAKOUT:
- direction may be LONG or SHORT (based on thesis)
- trade_mode may be INTRADAY or DELIVERY
- order_payload: transaction_type = BUY or SELL (based on direction), product matches trade_mode, order_type = LIMIT, price = entry_price (this is a pre-staged limit order ready to trigger)
- trade_plan MUST include all projected price levels (entry_price, stop_loss, target_price, risk_reward). Use structurally justified values — breakout level, S/R, ATR-derived SL, minimum RR target. Do NOT set them to 0.
- position_sizing MUST be fully computed at the projected entry_price using EXACTLY the same formula as ENTER_NOW. The trader is pre-sizing before the trigger so they are ready to fill immediately when price hits the level.

If action = ENTER_NOW:
- direction must be LONG or SHORT
- trade_mode must be INTRADAY or DELIVERY
- entry_price > 0, stop_loss > 0, target_price > 0
- risk_reward >= {min_rr}
- quantity >= 1
- order_payload: transaction_type = BUY or SELL, product matches trade_mode, quantity = position_sizing.quantity, order_type = MARKET or LIMIT, price = entry_price

=== BEHAVIORAL RULES ===
- Never re-argue the thesis. Accept upstream conclusions.
- Never output narrative outside the JSON.
- Never soften AVOID with conditional language.
- Never inflate confidence to make a weak setup look acceptable.
- Never include trailing stop, profit locking, or monitoring logic -- that is the Risk Agent's job.
- If the setup is dead, say so clearly and stop."""
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


# ═══════════════════════════════════════════════════════════════════════════════
# NEW STRICT OUTPUT SCHEMA — V2
# ═══════════════════════════════════════════════════════════════════════════════

VALID_ACTIONS = {"ENTER_NOW", "WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT", "AVOID"}
VALID_TRADE_MODES = {"INTRADAY", "DELIVERY", "NONE"}
VALID_DIRECTIONS = {"LONG", "SHORT", "NONE"}
VALID_CONFIDENCES = {"LOW", "MEDIUM", "HIGH"}
VALID_TRANSACTION_TYPES = {"BUY", "SELL", "NONE"}
VALID_PRODUCTS = {"INTRADAY", "DELIVERY", "NONE"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "NONE"}


def _build_avoid_result(symbol: str, reason: str, source: str, rp: dict) -> dict:
    """Build a fully valid AVOID result in the new strict schema."""
    result = {
        "stock": {"symbol": symbol, "exchange": "NSE"},
        "execution_decision": {
            "action": "AVOID",
            "trade_mode": "NONE",
            "direction": "NONE",
            "confidence": "LOW",
            "reason": reason,
        },
        "trade_plan": {
            "entry_price": 0,
            "stop_loss": 0,
            "target_price": 0,
            "risk_reward": 0,
            "invalidation": reason,
            "plan_notes": "",
        },
        "position_sizing": {
            "quantity": 0,
            "capital_used": 0,
            "risk_amount": 0,
            "risk_per_share": 0,
        },
        "order_payload": {
            "transaction_type": "NONE",
            "product": "NONE",
            "quantity": 0,
            "order_type": "NONE",
            "price": 0,
        },
        "_source": source,
        "_risk_params": rp,
    }
    return _add_backward_compat(result)


def _convert_old_to_new_schema(old: dict, symbol: str) -> dict:
    """Convert old Gemini LLM output format to the new strict schema.

    The LLM still outputs the old format (action/execution_decision/entry_plan etc).
    This function maps those fields into the new canonical structure.
    """
    old_action = str(old.get("action", "AVOID")).upper()
    old_exec_dec = str(old.get("execution_decision", "NO TRADE")).upper()
    old_trade_mode = str(old.get("trade_mode", "NONE")).upper()

    # Map old execution_decision string → new action enum
    action_map = {
        "ENTER NOW": "ENTER_NOW",
        "WAIT FOR PULLBACK": "WAIT_FOR_PULLBACK",
        "WAIT FOR BREAKOUT": "WAIT_FOR_BREAKOUT",
        "AVOID CHASE": "AVOID",
        "NO TRADE": "AVOID",
    }
    new_action = action_map.get(old_exec_dec, "AVOID")

    # Direction
    if old_action == "BUY":
        direction = "LONG"
    elif old_action == "SELL":
        direction = "SHORT"
    elif old_action == "WAIT" and new_action in ("WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT"):
        # Try to infer from context — default to NONE (will be fixed in Part 2 with agent alignment)
        direction = "NONE"
    else:
        direction = "NONE"

    # Confidence: integer 0-100 → LOW/MEDIUM/HIGH
    raw_conf = old.get("confidence", 0)
    try:
        conf_int = int(float(raw_conf)) if raw_conf else 0
    except (TypeError, ValueError):
        conf_int = 0
    if conf_int >= 70:
        confidence = "HIGH"
    elif conf_int >= 40:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # Extract prices from old nested dicts
    ep = old.get("entry_plan", {}) or {}
    sl = old.get("stop_loss", {}) or {}
    tg = old.get("target", {}) or {}
    sizing = old.get("position_sizing", {}) or {}

    entry_price = _safe_float(ep.get("entry_price"), 0.0)
    stop_loss = _safe_float(sl.get("price"), 0.0)
    target_price = _safe_float(tg.get("price"), 0.0)

    # Risk-reward: "1:2.5" → 2.5 (numeric)
    rr_raw = old.get("risk_reward", "")
    risk_reward = 0.0
    if isinstance(rr_raw, str) and ":" in rr_raw:
        try:
            risk_reward = round(float(rr_raw.split(":")[-1]), 2)
        except (ValueError, IndexError):
            risk_reward = 0.0
    elif isinstance(rr_raw, (int, float)):
        risk_reward = round(float(rr_raw), 2)

    # Position sizing mapping
    quantity = int(sizing.get("position_size_shares", 0))
    capital_used = _safe_float(sizing.get("position_size_inr"), 0.0)
    risk_amount = _safe_float(sizing.get("max_loss_at_sl"), 0.0)
    risk_per_share = _safe_float(sizing.get("risk_per_share"), 0.0)

    # Order payload — only for ENTER_NOW
    if new_action == "ENTER_NOW":
        txn_type = "BUY" if direction == "LONG" else "SELL" if direction == "SHORT" else "NONE"
        product = old_trade_mode if old_trade_mode in ("INTRADAY", "DELIVERY") else "NONE"
        entry_type = str(ep.get("entry_type", "MARKET")).upper()
        order_type = entry_type if entry_type in ("MARKET", "LIMIT") else "MARKET"
        order_price = entry_price
        order_qty = quantity
    else:
        txn_type = "NONE"
        product = "NONE"
        order_type = "NONE"
        order_price = 0
        order_qty = 0

    # Trade mode — force NONE for AVOID
    trade_mode = old_trade_mode if old_trade_mode in ("INTRADAY", "DELIVERY") else "NONE"
    if new_action == "AVOID":
        trade_mode = "NONE"
        direction = "NONE"
        entry_price = 0
        stop_loss = 0
        target_price = 0
        risk_reward = 0
        quantity = 0
        capital_used = 0
        risk_amount = 0
        risk_per_share = 0

    reason = old.get("why_now_or_why_wait", old.get("final_summary", ""))
    invalidation = old.get("invalidation", "")
    plan_notes = old.get("final_summary", "")

    return {
        "stock": {"symbol": symbol, "exchange": "NSE"},
        "execution_decision": {
            "action": new_action,
            "trade_mode": trade_mode,
            "direction": direction,
            "confidence": confidence,
            "reason": reason,
        },
        "trade_plan": {
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_loss, 2),
            "target_price": round(target_price, 2),
            "risk_reward": risk_reward,
            "invalidation": invalidation,
            "plan_notes": plan_notes,
        },
        "position_sizing": {
            "quantity": quantity,
            "capital_used": round(capital_used, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_per_share": round(risk_per_share, 2),
        },
        "order_payload": {
            "transaction_type": txn_type,
            "product": product,
            "quantity": order_qty,
            "order_type": order_type,
            "price": round(order_price, 2),
        },
    }


def validate_execution_schema(result: dict) -> tuple[bool, str]:
    """Validate a result dict against the strict V2 execution schema.

    Returns (is_valid, error_message).
    Covers: structural integrity, enum validation, action-specific rules,
    price ordering, payload consistency, and direction alignment.
    """
    # Required top-level sections
    for section in ("stock", "execution_decision", "trade_plan", "position_sizing", "order_payload"):
        if section not in result or not isinstance(result[section], dict):
            return False, f"missing required section: {section}"

    ed = result["execution_decision"]
    tp = result["trade_plan"]
    ps = result["position_sizing"]
    op = result["order_payload"]

    # ── Enum validation ──────────────────────────────────────────────────────
    if ed.get("action") not in VALID_ACTIONS:
        return False, f"invalid action: {ed.get('action')}"
    if ed.get("trade_mode") not in VALID_TRADE_MODES:
        return False, f"invalid trade_mode: {ed.get('trade_mode')}"
    if ed.get("direction") not in VALID_DIRECTIONS:
        return False, f"invalid direction: {ed.get('direction')}"
    if ed.get("confidence") not in VALID_CONFIDENCES:
        return False, f"invalid confidence: {ed.get('confidence')}"
    if op.get("transaction_type") not in VALID_TRANSACTION_TYPES:
        return False, f"invalid transaction_type: {op.get('transaction_type')}"
    if op.get("product") not in VALID_PRODUCTS:
        return False, f"invalid product: {op.get('product')}"
    if op.get("order_type") not in VALID_ORDER_TYPES:
        return False, f"invalid order_type: {op.get('order_type')}"

    action = ed["action"]
    direction = ed.get("direction", "NONE")
    trade_mode = ed.get("trade_mode", "NONE")

    # ── AVOID rules: zero everything ─────────────────────────────────────────
    if action == "AVOID":
        if tp.get("entry_price", 0) != 0 or tp.get("stop_loss", 0) != 0 or tp.get("target_price", 0) != 0:
            return False, "AVOID must have zero prices"
        if direction != "NONE":
            return False, "AVOID must have direction=NONE"
        if trade_mode != "NONE":
            return False, "AVOID must have trade_mode=NONE"
        if op.get("transaction_type") != "NONE":
            return False, "AVOID must have transaction_type=NONE"
        if op.get("product") != "NONE":
            return False, "AVOID must have product=NONE"
        if op.get("order_type") != "NONE":
            return False, "AVOID must have order_type=NONE"
        if op.get("quantity", 0) != 0:
            return False, "AVOID must have order_payload.quantity=0"
        if ps.get("quantity", 0) != 0:
            return False, "AVOID must have position_sizing.quantity=0"

    # ── ENTER_NOW rules: must have valid executable plan ─────────────────────
    if action == "ENTER_NOW":
        entry = _safe_float(tp.get("entry_price"), 0.0)
        sl = _safe_float(tp.get("stop_loss"), 0.0)
        tgt = _safe_float(tp.get("target_price"), 0.0)
        rr = _safe_float(tp.get("risk_reward"), 0.0)
        qty = int(ps.get("quantity", 0))
        rps = _safe_float(ps.get("risk_per_share"), 0.0)

        # Basic price checks
        if entry <= 0:
            return False, "ENTER_NOW must have entry_price > 0"
        if sl <= 0:
            return False, "ENTER_NOW must have stop_loss > 0"
        if tgt <= 0:
            return False, "ENTER_NOW must have target_price > 0"
        if rr <= 0:
            return False, "ENTER_NOW must have risk_reward > 0"
        if qty <= 0:
            return False, "ENTER_NOW must have quantity > 0"
        if rps <= 0:
            return False, "ENTER_NOW must have risk_per_share > 0"

        # Direction and trade_mode required
        if direction not in ("LONG", "SHORT"):
            return False, "ENTER_NOW must have direction LONG or SHORT"
        if trade_mode not in ("INTRADAY", "DELIVERY"):
            return False, "ENTER_NOW must have trade_mode INTRADAY or DELIVERY"

        # Price ordering
        if direction == "LONG" and not (sl < entry < tgt):
            return False, f"LONG price order invalid: need SL({sl}) < entry({entry}) < target({tgt})"
        if direction == "SHORT" and not (tgt < entry < sl):
            return False, f"SHORT price order invalid: need target({tgt}) < entry({entry}) < SL({sl})"

        # Order payload checks
        if op.get("transaction_type") not in ("BUY", "SELL"):
            return False, "ENTER_NOW must have transaction_type BUY or SELL"
        if int(op.get("quantity", 0)) <= 0:
            return False, "ENTER_NOW must have order_payload.quantity > 0"

        # Direction-transaction consistency: BUY=LONG, SELL=SHORT
        txn = op.get("transaction_type")
        if direction == "LONG" and txn != "BUY":
            return False, f"LONG direction requires BUY, got {txn}"
        if direction == "SHORT" and txn != "SELL":
            return False, f"SHORT direction requires SELL, got {txn}"

        # Product-trade_mode consistency
        op_product = op.get("product", "NONE")
        if trade_mode == "INTRADAY" and op_product != "INTRADAY":
            return False, f"trade_mode=INTRADAY requires product=INTRADAY, got {op_product}"
        if trade_mode == "DELIVERY" and op_product != "DELIVERY":
            return False, f"trade_mode=DELIVERY requires product=DELIVERY, got {op_product}"

        # Quantity consistency: order_payload.quantity must match position_sizing.quantity
        if int(op.get("quantity", 0)) != qty:
            return False, f"order_payload.quantity({op.get('quantity')}) != position_sizing.quantity({qty})"

    # ── WAIT rules: Allow pre-staged limit orders ────────────────────────────
    if action in ("WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT"):
        # If payload is provided, it must be consistent
        txn = op.get("transaction_type", "NONE")
        if txn != "NONE":
            if txn not in ("BUY", "SELL"):
                return False, f"{action} has invalid transaction_type: {txn}"
            if direction == "LONG" and txn != "BUY":
                return False, f"{action} LONG requires BUY, got {txn}"
            if direction == "SHORT" and txn != "SELL":
                return False, f"{action} SHORT requires SELL, got {txn}"
            
            # If txn provided, qty should match sizing
            qty = int(ps.get("quantity", 0))
            if int(op.get("quantity", 0)) != qty:
                return False, f"{action} order_payload.quantity({op.get('quantity')}) != position_sizing.quantity({qty})"
            
            # If txn provided, product should match trade_mode
            op_product = op.get("product", "NONE")
            if trade_mode == "INTRADAY" and op_product != "INTRADAY":
                return False, f"{action} trade_mode=INTRADAY requires product=INTRADAY, got {op_product}"
            if trade_mode == "DELIVERY" and op_product != "DELIVERY":
                return False, f"{action} trade_mode=DELIVERY requires product=DELIVERY, got {op_product}"

    return True, "ok"


def _add_backward_compat(result: dict) -> dict:
    """Inject old-format flat fields so execution_agent.py keeps working.

    execution_agent.py reads:
      - result.get("action")  → "BUY"/"SELL"/"WAIT"/"AVOID"
      - result.get("execution_decision")  → "ENTER NOW"/"NO TRADE"/...
      - result.get("confidence")  → int
      - result.get("entry_plan", {}).get("entry_price")
      - result.get("stop_loss", {}).get("price")
      - result.get("target", {}).get("price")
      - result.get("position_sizing", {}).get("position_size_shares")
      - result.get("why_now_or_why_wait")

    We store the V2 execution_decision dict under "_v2_execution_decision"
    and overwrite "execution_decision" with the old-format string.
    We also merge old-format position_sizing keys into the existing dict.
    """
    ed = result.get("execution_decision", {}) if isinstance(result.get("execution_decision"), dict) else {}
    tp = result.get("trade_plan", {})
    ps = result.get("position_sizing", {})

    new_action = ed.get("action", "AVOID")
    direction = ed.get("direction", "NONE")

    # Map new action → old "action" field
    if new_action == "ENTER_NOW":
        old_action = "BUY" if direction == "LONG" else "SELL" if direction == "SHORT" else "AVOID"
    elif new_action in ("WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT"):
        old_action = "WAIT"
    else:
        old_action = "AVOID"

    # Map new action → old "execution_decision" string
    old_exec_dec_map = {
        "ENTER_NOW": "ENTER NOW",
        "WAIT_FOR_PULLBACK": "WAIT FOR PULLBACK",
        "WAIT_FOR_BREAKOUT": "WAIT FOR BREAKOUT",
        "AVOID": "NO TRADE",
    }
    old_exec_dec = old_exec_dec_map.get(new_action, "NO TRADE")

    # Confidence: HIGH→80, MEDIUM→50, LOW→20
    conf_map = {"HIGH": 80, "MEDIUM": 50, "LOW": 20}
    old_confidence = conf_map.get(ed.get("confidence", "LOW"), 20)

    # RR: numeric → string "1:X"
    rr_num = tp.get("risk_reward", 0)
    old_rr = f"1:{rr_num}" if rr_num > 0 else "N/A"

    # Preserve the V2 execution_decision dict before overwriting
    result["_v2_execution_decision"] = ed

    # Inject old-format top-level fields
    result["action"] = old_action
    result["execution_decision"] = old_exec_dec  # overwrite dict → string for compat
    result["confidence"] = old_confidence
    result["trade_mode"] = ed.get("trade_mode", "NONE")
    result["risk_reward"] = old_rr
    result["invalidation"] = tp.get("invalidation", "")
    result["why_now_or_why_wait"] = ed.get("reason", "")
    result["final_summary"] = tp.get("plan_notes", "")

    # Old-format nested dicts for entry/sl/target
    result["entry_plan"] = {
        "entry_type": result.get("order_payload", {}).get("order_type", "NONE"),
        "entry_price": tp.get("entry_price", 0),
        "condition": ed.get("reason", ""),
    }
    result["stop_loss"] = {
        "price": tp.get("stop_loss", 0),
        "reason": tp.get("invalidation", ""),
    }
    result["target"] = {
        "price": tp.get("target_price", 0),
        "reason": tp.get("plan_notes", ""),
    }

    # Merge old-format keys into position_sizing
    ps["position_size_shares"] = ps.get("quantity", 0)
    ps["position_size_inr"] = ps.get("capital_used", 0)
    ps["max_loss_at_sl"] = ps.get("risk_amount", 0)
    ps["capital_used_pct"] = round(
        (ps.get("capital_used", 0) / result.get("_risk_params", {}).get("total_capital", 1)) * 100, 2
    ) if result.get("_risk_params", {}).get("total_capital", 0) > 0 else 0
    ps["sizing_note"] = ed.get("reason", "")

    return result


def _blocked_execution(reason: str, rp: dict, source: str = "agent3_precheck") -> dict:
    """Build a blocked (AVOID) result in new schema with backward compat."""
    return _build_avoid_result("UNKNOWN", reason, source, rp)


def _build_wait_result(
    symbol: str, wait_action: str, reason: str,
    source: str, rp: dict, trade_mode: str = "NONE",
    direction: str = "NONE", confidence: str = "LOW",
) -> dict:
    """Build a valid WAIT_FOR_PULLBACK or WAIT_FOR_BREAKOUT result in V2 schema."""
    if wait_action not in ("WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT"):
        wait_action = "WAIT_FOR_PULLBACK"
    result = {
        "stock": {"symbol": symbol, "exchange": "NSE"},
        "execution_decision": {
            "action": wait_action,
            "trade_mode": trade_mode if trade_mode in ("INTRADAY", "DELIVERY") else "NONE",
            "direction": direction if direction in ("LONG", "SHORT") else "NONE",
            "confidence": confidence if confidence in ("LOW", "MEDIUM", "HIGH") else "LOW",
            "reason": reason,
        },
        "trade_plan": {
            "entry_price": 0, "stop_loss": 0, "target_price": 0,
            "risk_reward": 0, "invalidation": reason, "plan_notes": "",
        },
        "position_sizing": {
            "quantity": 0, "capital_used": 0, "risk_amount": 0, "risk_per_share": 0,
        },
        "order_payload": {
            "transaction_type": "NONE", "product": "NONE",
            "quantity": 0, "order_type": "NONE", "price": 0,
        },
        "_source": source,
        "_risk_params": rp,
    }
    return _add_backward_compat(result)


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-LLM DETERMINISTIC GATES
# ═══════════════════════════════════════════════════════════════════════════════

def _run_pre_llm_gates(
    symbol: str, agent2_view: dict, agent25_data: dict | None, rp: dict,
) -> dict | None:
    """Run all deterministic pre-LLM gate checks.

    Returns a blocked/wait V2 result if any gate fails, or None if all pass.
    Gates are checked in strict priority order:
      1. Agent 2 gate (status + should_pass + instruction)
      2. Agent 2.5 gate (NO_GO / AVOID / NO_SUPPORT)  — only if data exists
      3. Agent 2.5 WAIT handling                       — only if data exists
      4. Bias contradiction (Agent 1 vs Agent 2.5)     — only if data exists
      5. Confidence gate                               — only if data exists
    """

    # ── Gate 1: Agent 2 Hard Gate ─────────────────────────────────────────────
    decision = agent2_view.get("decision", {})
    validation = agent2_view.get("validation", {})

    # 1a. should_pass_to_agent_3
    should_pass = decision.get("should_pass_to_agent_3", False)
    if not should_pass:
        reason = "Agent 2 decision: should_pass_to_agent_3 = false"
        print(f"[AGENT 3 GATE] {symbol}: blocked by Agent 2 should_pass=false")
        return _build_avoid_result(symbol, reason, "gate_agent2_should_pass", rp)

    # 1b. validation.status must be CONFIRMED
    val_status = str(validation.get("status", "")).upper()
    if val_status and val_status != "CONFIRMED":
        reason = f"Agent 2 validation.status = {val_status} (expected CONFIRMED)"
        print(f"[AGENT 3 GATE] {symbol}: blocked by Agent 2 status={val_status}")
        return _build_avoid_result(symbol, reason, "gate_agent2_status", rp)

    # 1c. agent_3_instruction = DO_NOT_PROCEED
    a3_instruction = str(decision.get("agent_3_instruction", "")).upper().strip()
    if a3_instruction == "DO_NOT_PROCEED":
        reason = "Agent 2 instruction: DO_NOT_PROCEED"
        print(f"[AGENT 3 GATE] {symbol}: blocked by Agent 2 DO_NOT_PROCEED")
        return _build_avoid_result(symbol, reason, "gate_agent2_instruction", rp)

    # ── If no Agent 2.5 data, skip gates 2-5 (legacy fallback path) ──────────
    if not agent25_data or not isinstance(agent25_data, dict):
        return None  # All Agent 2 gates passed, no Agent 2.5 to check

    ta = agent25_data.get("technical_analysis", {})
    overall = ta.get("overall", {})
    handoff = ta.get("agent_3_handoff", {})

    go_no_go = str(handoff.get("technical_go_no_go", "")).upper()
    trade_readiness = str(overall.get("trade_readiness", "")).upper()
    execution_support = str(overall.get("execution_support", "")).upper()
    tech_bias = str(overall.get("technical_bias", "")).upper()
    tech_confidence = str(overall.get("confidence", "")).upper()
    tech_risk_level = str(overall.get("technical_risk_level", "")).upper()

    # ── Gate 2: Agent 2.5 Hard Block ──────────────────────────────────────────
    if go_no_go == "NO_GO":
        go_reason = handoff.get("go_no_go_reason", "Agent 2.5 technical_go_no_go = NO_GO")
        print(f"[AGENT 3 GATE] {symbol}: blocked by Agent 2.5 NO_GO -- {go_reason}")
        return _build_avoid_result(symbol, go_reason, "gate_agent25_no_go", rp)

    if trade_readiness == "AVOID":
        reason = "Agent 2.5 trade_readiness = AVOID"
        print(f"[AGENT 3 GATE] {symbol}: blocked by Agent 2.5 trade_readiness=AVOID")
        return _build_avoid_result(symbol, reason, "gate_agent25_readiness", rp)

    if execution_support == "NO_SUPPORT":
        reason = "Agent 2.5 execution_support = NO_SUPPORT"
        print(f"[AGENT 3 GATE] {symbol}: blocked by Agent 2.5 NO_SUPPORT")
        return _build_avoid_result(symbol, reason, "gate_agent25_no_support", rp)

    # ── Gate 3: Agent 2.5 WAIT Handling ───────────────────────────────────────
    if go_no_go == "WAIT":
        go_reason = handoff.get("go_no_go_reason", "Agent 2.5 technical_go_no_go = WAIT")
        # Determine WAIT type from handoff context
        must_confirm = handoff.get("must_confirm_before_entry", "")
        if must_confirm and "breakout" in str(must_confirm).lower():
            wait_action = "WAIT_FOR_BREAKOUT"
        else:
            wait_action = "WAIT_FOR_PULLBACK"

        # Infer direction from Agent 1 bias
        agent1 = agent2_view.get("agent_1_view", {})
        a1_bias = str(agent1.get("final_bias", "NEUTRAL")).upper()
        direction = "LONG" if a1_bias == "BULLISH" else "SHORT" if a1_bias == "BEARISH" else "NONE"

        # Infer trade mode from Agent 2
        trade_suitability = agent2_view.get("trade_suitability", {})
        trade_mode = str(trade_suitability.get("mode", agent2_view.get("trade_mode", "NONE"))).upper()

        print(f"[AGENT 3 GATE] {symbol}: WAIT from Agent 2.5 -- {go_reason} -> {wait_action}")
        return _build_wait_result(
            symbol, wait_action, go_reason, "gate_agent25_wait", rp,
            trade_mode=trade_mode, direction=direction, confidence="MEDIUM",
        )

    # ── Gate 4: Bias Contradiction ────────────────────────────────────────────
    agent1 = agent2_view.get("agent_1_view", {})
    a1_bias = str(agent1.get("final_bias", "NEUTRAL")).upper()

    if a1_bias in ("BULLISH", "BEARISH") and tech_bias in ("BULLISH", "BEARISH"):
        if (a1_bias == "BULLISH" and tech_bias == "BEARISH") or \
           (a1_bias == "BEARISH" and tech_bias == "BULLISH"):
            reason = f"Bias contradiction: Agent 1={a1_bias}, Agent 2.5={tech_bias}"
            # Check if it's a weak/partial contradiction
            if tech_confidence == "LOW" or execution_support in ("WEAK_SUPPORT", "MODERATE_SUPPORT"):
                # Weak contradiction -> WAIT
                trade_suitability = agent2_view.get("trade_suitability", {})
                trade_mode = str(trade_suitability.get("mode", agent2_view.get("trade_mode", "NONE"))).upper()
                direction = "LONG" if a1_bias == "BULLISH" else "SHORT"
                print(f"[AGENT 3 GATE] {symbol}: bias contradiction (weak) -- {reason} -> WAIT")
                return _build_wait_result(
                    symbol, "WAIT_FOR_PULLBACK",
                    f"{reason} (weak contradiction, waiting for confirmation)",
                    "gate_bias_contradiction_weak", rp,
                    trade_mode=trade_mode, direction=direction, confidence="LOW",
                )
            else:
                # Strong contradiction -> AVOID
                print(f"[AGENT 3 GATE] {symbol}: bias contradiction (direct) -- {reason} -> AVOID")
                return _build_avoid_result(symbol, reason, "gate_bias_contradiction", rp)

    # ── Gate 5: Confidence Gate ───────────────────────────────────────────────
    a1_confidence = str(agent1.get("final_confidence", "")).upper()

    # 5a. Agent 1 LOW confidence
    if a1_confidence == "LOW":
        reason = "Agent 1 final_confidence = LOW"
        print(f"[AGENT 3 GATE] {symbol}: low confidence -- {reason}")
        return _build_avoid_result(symbol, reason, "gate_agent1_low_confidence", rp)

    # 5b. Agent 2.5 LOW confidence
    if tech_confidence == "LOW":
        reason = "Agent 2.5 confidence = LOW"
        print(f"[AGENT 3 GATE] {symbol}: low confidence -- {reason}")
        return _build_avoid_result(symbol, reason, "gate_agent25_low_confidence", rp)

    # 5c. HIGH technical risk with weak execution support
    if tech_risk_level == "HIGH" and execution_support not in ("STRONG_SUPPORT",):
        reason = f"Agent 2.5 technical_risk_level=HIGH with execution_support={execution_support}"
        print(f"[AGENT 3 GATE] {symbol}: high risk / weak support -- {reason}")
        return _build_avoid_result(symbol, reason, "gate_high_risk_weak_support", rp)

    # All gates passed
    return None


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

# =============================================================================
# POST-LLM DETERMINISTIC VALIDATION & ENFORCEMENT
# =============================================================================

def _post_llm_validate_and_enforce(result: dict, symbol: str, rp: dict, ctx: dict) -> dict:
    """Deterministic post-LLM enforcement.  Gemini is NEVER trusted for math.

    Runs on V2 schema result after parsing.  For ENTER_NOW:
      1. Validate price ordering (LONG: SL < entry < target, SHORT: target < entry < SL)
      2. Validate direction exists
      3. Recompute sizing deterministically (risk_per_share, quantity, capital_used, risk_amount)
      4. Enforce capital cap (reduce quantity if capital_used > max_position_capital)
      5. Enforce minimum RR
      6. No-chase protection (LONG near resistance, SHORT near support)
      7. Fix-up direction-transaction and product-trade_mode consistency

    Returns the validated/corrected result, or an AVOID result if blocked.
    """
    ed = result.get("execution_decision", {})
    if not isinstance(ed, dict):
        return result

    action = ed.get("action", "AVOID")

    if action not in ("ENTER_NOW", "WAIT_FOR_PULLBACK", "WAIT_FOR_BREAKOUT"):
        return result

    tp = result.get("trade_plan", {})
    op = result.get("order_payload", {})
    dir_str = ed.get("direction", "NONE")
    trade_mode = ed.get("trade_mode", "NONE")
    bias = "BULLISH" if dir_str == "LONG" else "BEARISH" if dir_str == "SHORT" else "NEUTRAL"

    e_p = _safe_float(tp.get("entry_price"), 0.0)
    s_p = _safe_float(tp.get("stop_loss"), 0.0)
    t_p = _safe_float(tp.get("target_price"), 0.0)

    # ── 1. Direction check ──────────────────────────────────────────────────
    if bias not in ("BULLISH", "BEARISH"):
        return _build_avoid_result(symbol, "ENTER_NOW with no valid direction", "postllm_no_direction", rp)

    # ── 2. Price positivity ─────────────────────────────────────────────────
    if e_p <= 0 or s_p <= 0 or t_p <= 0:
        return _build_avoid_result(symbol, "ENTER_NOW with zero/negative prices", "postllm_zero_prices", rp)

    # ── 3. Price ordering ───────────────────────────────────────────────────
    if bias == "BULLISH" and not (s_p < e_p < t_p):
        return _build_avoid_result(
            symbol,
            f"LONG price order invalid: SL({s_p}) < entry({e_p}) < target({t_p})",
            "postllm_long_price_order", rp,
        )
    if bias == "BEARISH" and not (t_p < e_p < s_p):
        return _build_avoid_result(
            symbol,
            f"SHORT price order invalid: target({t_p}) < entry({e_p}) < SL({s_p})",
            "postllm_short_price_order", rp,
        )

    # ── 4. Deterministic sizing override ────────────────────────────────────
    #    Gemini is NEVER trusted for math.
    risk_per_share = abs(e_p - s_p)
    if risk_per_share <= 0:
        return _build_avoid_result(symbol, "risk_per_share <= 0", "postllm_zero_risk", rp)

    max_shares_by_loss = int(rp["max_loss_amount"] / risk_per_share)
    max_shares_by_capital = int(rp["max_position_capital"] / e_p) if e_p > 0 else 0
    quantity = min(max_shares_by_loss, max_shares_by_capital)

    if quantity <= 0:
        return _build_avoid_result(symbol, "quantity = 0 after deterministic sizing", "postllm_qty_zero", rp)

    capital_used = round(quantity * e_p, 2)

    # ── 5. Capital cap enforcement ──────────────────────────────────────────
    if capital_used > rp["max_position_capital"]:
        quantity = int(rp["max_position_capital"] / e_p)
        capital_used = round(quantity * e_p, 2)
        if quantity <= 0:
            return _build_avoid_result(symbol, "capital cap reduced quantity to 0", "postllm_capital_cap_zero", rp)

    risk_amount = round(quantity * risk_per_share, 2)

    # ── 6. RR enforcement ───────────────────────────────────────────────────
    actual_rr, meets = _validate_rr(e_p, s_p, t_p, bias, rp["min_rr"])
    if not meets:
        return _build_avoid_result(
            symbol, f"RR 1:{actual_rr} below min {rp['min_rr']}:1",
            "postllm_rr_below_min", rp,
        )

    # ── 7. No-chase protection ──────────────────────────────────────────────
    if ctx and isinstance(ctx, dict):
        day_high = _safe_float(ctx.get("day_high"), 0.0)
        day_low = _safe_float(ctx.get("day_low"), 0.0)

        if bias == "BULLISH" and day_high > 0:
            dist_to_high = abs(day_high - e_p)
            pct_to_high = (dist_to_high / e_p) * 100 if e_p > 0 else 999
            if pct_to_high < 0.2:
                print(f"      [POSTLLM] {symbol}: LONG entry too close to day high ({pct_to_high:.2f}%) -> WAIT")
                return _build_wait_result(
                    symbol, "WAIT_FOR_PULLBACK",
                    f"no-chase: LONG entry {e_p} is within {pct_to_high:.2f}% of day high {day_high}",
                    "postllm_chase_long", rp,
                    trade_mode=trade_mode, direction=dir_str, confidence=ed.get("confidence", "LOW"),
                )

        if bias == "BEARISH" and day_low > 0:
            dist_to_low = abs(e_p - day_low)
            pct_to_low = (dist_to_low / e_p) * 100 if e_p > 0 else 999
            if pct_to_low < 0.2:
                print(f"      [POSTLLM] {symbol}: SHORT entry too close to day low ({pct_to_low:.2f}%) -> WAIT")
                return _build_wait_result(
                    symbol, "WAIT_FOR_PULLBACK",
                    f"no-chase: SHORT entry {e_p} is within {pct_to_low:.2f}% of day low {day_low}",
                    "postllm_chase_short", rp,
                    trade_mode=trade_mode, direction=dir_str, confidence=ed.get("confidence", "LOW"),
                )

    # ── 8. Fix-up consistency ───────────────────────────────────────────────
    # Direction-transaction alignment
    txn_type = "BUY" if dir_str == "LONG" else "SELL"
    # Product-trade_mode alignment
    product = trade_mode if trade_mode in ("INTRADAY", "DELIVERY") else "INTRADAY"
    # Order type
    order_type = op.get("order_type", "MARKET")
    if order_type not in ("MARKET", "LIMIT"):
        order_type = "MARKET"

    # ── Write back deterministic values ─────────────────────────────────────
    result["position_sizing"] = {
        "quantity": quantity,
        "capital_used": capital_used,
        "risk_amount": risk_amount,
        "risk_per_share": round(risk_per_share, 2),
    }
    result["trade_plan"]["risk_reward"] = actual_rr
    result["order_payload"] = {
        "transaction_type": txn_type,
        "product": product,
        "quantity": quantity,
        "order_type": order_type,
        "price": round(e_p, 2),
    }

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

def plan_execution(input_data: dict, risk_config: dict = None, chart_image_bytes: bytes = None) -> dict:
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

    # 3. Comprehensive pre-LLM gates (Agent 2 + Agent 2.5 + bias + confidence)
    agent25_data = input_data.get("agent25_technical_analysis")
    gate_result = _run_pre_llm_gates(symbol, agent2_view, agent25_data, rp)
    if gate_result is not None:
        return gate_result

    # --- LOGGING: [AGENT 3 INPUT] ---
    print(f"==============================")
    print(f"[AGENT 3 INPUT]")
    print(f"==============================")
    print(f"symbol: {symbol}")
    
    a1_view = agent2_view.get("agent_1_view", {})
    print(f"direction: {a1_view.get('final_bias')}")
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

    contents = [prompt]
    if chart_image_bytes:
        contents.append(types.Part.from_bytes(data=chart_image_bytes, mime_type="image/png"))

    import time as _time
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            response = _client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=AGENT3_SYSTEM_INSTRUCTION,
                    temperature=0.1,
                    response_mime_type="application/json",
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

            raw = json.loads(text)

            # ── Dual-path parsing: V2 direct → old-schema fallback ──
            is_v2 = isinstance(raw.get("execution_decision"), dict) and "stock" in raw

            if is_v2:
                # Gemini returned V2 schema directly
                result = dict(raw)
                print(f"      [PARSE] V2 schema detected for {symbol}")
            else:
                # Old schema — normalize confidence, then run legacy risk checks, then convert
                print(f"      [PARSE] Old schema detected for {symbol} — converting to V2")
                old_result = dict(raw)
                try:
                    conf = old_result.get("confidence", 0)
                    if isinstance(conf, float) and conf <= 1.0:
                        old_result["confidence"] = int(conf * 100)
                    else:
                        old_result["confidence"] = int(conf)
                except Exception:
                    old_result["confidence"] = 0

                ep = old_result.get("entry_plan", {}) or {}
                sl = old_result.get("stop_loss", {}) or {}
                tg = old_result.get("target", {}) or {}
                agent1 = input_data.get("agent2_view", {}).get("agent_1_view", {})
                direction = str(agent1.get("final_bias", "NEUTRAL")).upper()
                exec_dec = str(old_result.get("execution_decision", "NO TRADE")).upper()
                entry_price = _safe_float(ep.get("entry_price"), 0.0)
                stop_price = _safe_float(sl.get("price"), 0.0)
                target_price = _safe_float(tg.get("price"), 0.0)

                # Legacy risk checks on old format
                agent2_dec = input_data.get("agent2_view", {}).get("decision", {})
                should_pass = agent2_dec.get("should_pass_to_agent_3", False)
                if not should_pass:
                    old_result = _normalize_result_no_trade(old_result, "Agent 2 rejected the trade")
                else:
                    if exec_dec == "ENTER NOW":
                        if direction not in ("BULLISH", "BEARISH"):
                            old_result = _normalize_result_no_trade(old_result, "invalid Agent 2 direction for live entry")
                        elif entry_price <= 0 or stop_price <= 0 or target_price <= 0:
                            old_result = _normalize_result_no_trade(old_result, "invalid entry/stop/target for live entry")
                        else:
                            sizing = _compute_position_size(entry_price, stop_price, direction, rp)
                            actual_rr, meets_min = _validate_rr(entry_price, stop_price, target_price, direction, rp["min_rr"])
                            if sizing["position_size_shares"] == 0:
                                old_result = _normalize_result_no_trade(old_result, f"position sizing failed: {sizing['sizing_note']}")
                            elif not meets_min:
                                old_result = _normalize_result_no_trade(old_result, f"trade rejected: RR 1:{actual_rr} below min {rp['min_rr']}:1")
                            else:
                                old_result["position_sizing"] = sizing
                                old_result["risk_reward"] = f"1:{actual_rr}"

                    elif exec_dec in ("WAIT FOR_PULLBACK", "WAIT FOR BREAKOUT"):
                        exec_dec = "WAIT FOR PULLBACK" if "PULLBACK" in exec_dec else "WAIT FOR BREAKOUT"
                        old_result["execution_decision"] = exec_dec

                    if exec_dec in ("WAIT FOR PULLBACK", "WAIT FOR BREAKOUT"):
                        ltp = _safe_float(input_data.get("live_execution_context", {}).get("ltp"), 0.0)
                        if stop_price > 0 and ltp > 0 and direction in ("BULLISH", "BEARISH"):
                            sizing = _compute_position_size(ltp, stop_price, direction, rp)
                            sizing["sizing_note"] = "(projected)"
                            old_result["position_sizing"] = sizing

                    if exec_dec in ("NO TRADE", "AVOID CHASE"):
                        if exec_dec == "NO TRADE":
                            old_result = _normalize_result_no_trade(old_result, str(old_result.get("why_now_or_why_wait") or "execution rejected"))
                        else:
                            old_result["action"] = "AVOID"

                result = _convert_old_to_new_schema(old_result, symbol)

            # ── Post-LLM deterministic validation & enforcement ──
            result = _post_llm_validate_and_enforce(result, symbol, rp, input_data.get("live_execution_context", {}))

            # ── Attach metadata ──
            result["_source"] = result.get("_source", "gemini_agent3")
            result["_model"] = MODEL_NAME
            result["_risk_params"] = rp
            result["_live_snapshot_used"] = input_data.get("live_execution_context", {})

            # ── Validate final V2 schema ──
            valid, err = validate_execution_schema(result)
            if not valid:
                print(f"      [WARN] Schema validation failed: {err} -- downgrading to AVOID")
                return _build_avoid_result(symbol, f"schema validation failed: {err}", "agent3_schema_fail", rp)

            # ── Add backward compat ──
            result = _add_backward_compat(result)

            # ── Logging ──
            v2 = result.get("_v2_execution_decision", {})
            print(f"==============================")
            print(f"[AGENT 3 DECISION]")
            print(f"==============================")
            print(f"action(v2): {v2.get('action')} | direction: {v2.get('direction')} | confidence: {v2.get('confidence')}")
            print(f"compat: action={result.get('action')} | exec_dec={result.get('execution_decision')}")
            tp = result.get("trade_plan", {})
            if v2.get("action") == "ENTER_NOW":
                ps = result.get("position_sizing", {})
                print(f"\nEntry: {tp.get('entry_price')} | SL: {tp.get('stop_loss')} | Target: {tp.get('target_price')}")
                print(f"RR: {tp.get('risk_reward')} | Qty: {ps.get('quantity')} | Risk: Rs.{ps.get('risk_amount')}")
            else:
                print(f"Reason: {v2.get('reason', '').encode('ascii', errors='replace').decode('ascii')}")
            print(f"==============================\n")

            return result

        except Exception as e:
            err_str = str(e)
            is_503 = "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str
            if is_503 and attempt < max_retries:
                wait_sec = 8 * attempt
                print(f"      [AGENT 3] 503 for {symbol} (attempt {attempt}/{max_retries}) — retrying in {wait_sec}s...")
                _time.sleep(wait_sec)
                continue
            err_msg = err_str.encode('ascii', errors='replace').decode('ascii')
            print(f"\n[ERROR] Gemini Agent 3 failed: {err_msg}\n")
            return _fallback_execution(input_data, rp, llm_error=err_str)



# ---------------------------
# Fallback planner
# ---------------------------

def _fallback_execution(input_data: dict, rp: dict = None, llm_error: str = "") -> dict:
    if rp is None:
        rp = _compute_risk_params({})

    symbol = input_data.get("symbol", "UNKNOWN")
    agent2 = input_data.get("agent2_view", {}) or {}
    ctx = input_data.get("live_execution_context", {}) or {}

    ok, reason = _validate_market_snapshot(ctx)
    if not ok:
        return _blocked_execution(f"fallback blocked: invalid market snapshot: {reason}", rp, source="agent3_fallback_snapshot")

    decision_block = agent2.get("decision", {})
    should_pass = decision_block.get("should_pass_to_agent_3", False)
    agent1 = agent2.get("agent_1_view", {})
    direction = str(agent1.get("final_bias", "NEUTRAL")).upper()
    trade_mode = str(agent2.get("trade_mode", "NONE")).upper()

    if not should_pass:
        return _blocked_execution("Agent 2 rejected the trade", rp, source="agent3_fallback_agent2")

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

    # Fallback uses old-format variables internally, then converts
    action = "AVOID"
    exec_decision = "NO TRADE"
    entry_type = "NONE"
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    reason_text = "fallback rejected: setup not executable safely"

    if direction == "BULLISH":
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

    # Risk validation for fallback ENTER NOW
    if exec_decision == "ENTER NOW":
        sizing = _compute_position_size(entry_price, stop_price, direction, rp)
        actual_rr, meets = _validate_rr(entry_price, stop_price, target_price, direction, rp["min_rr"])

        if sizing["position_size_shares"] == 0:
            return _blocked_execution(f"fallback blocked: {sizing['sizing_note']}", rp, source="agent3_fallback_sizing")
        if not meets:
            return _blocked_execution(f"fallback blocked: actual risk-reward 1:{actual_rr} below minimum {rp['min_rr']}:1", rp, source="agent3_fallback_rr")

        risk_reward_str = f"1:{actual_rr}"
        position_sizing = sizing
    else:
        risk_reward_str = "N/A"
        position_sizing = {
            "position_size_shares": 0, "position_size_inr": 0.0,
            "risk_per_share": 0.0, "max_loss_at_sl": 0.0,
            "capital_used_pct": 0.0, "sizing_note": "no live entry planned"
        }

    confidence = 0
    try:
        a2_conf = agent2.get("confidence", 0)
        confidence = int(float(a2_conf) * 100) if isinstance(a2_conf, float) and a2_conf <= 1.0 else int(a2_conf or 0)
    except Exception:
        confidence = 0

    # Build old-format result then convert
    old_result = {
        "action": action,
        "execution_decision": exec_decision,
        "trade_mode": trade_mode if exec_decision not in ("NO TRADE",) else "NONE",
        "confidence": confidence,
        "entry_plan": {"entry_type": entry_type, "entry_price": round(entry_price, 2), "condition": reason_text},
        "stop_loss": {"price": round(stop_price, 2), "reason": "fallback structural stop"},
        "target": {"price": round(target_price, 2), "reason": "fallback structural target"},
        "position_sizing": position_sizing,
        "risk_reward": risk_reward_str,
        "invalidation": "if price breaks the structure used for this setup",
        "why_now_or_why_wait": reason_text + (f" | llm_error={llm_error}" if llm_error else ""),
        "final_summary": f"Fallback execution: {exec_decision}",
    }

    if exec_decision == "NO TRADE":
        old_result = _normalize_result_no_trade(old_result, reason_text)

    # Convert to V2 schema
    result = _convert_old_to_new_schema(old_result, symbol)
    result["_source"] = "agent3_fallback"
    result["_risk_params"] = rp
    result["_live_snapshot_used"] = ctx

    valid, err = validate_execution_schema(result)
    if not valid:
        return _build_avoid_result(symbol, f"fallback schema validation failed: {err}", "agent3_fallback_schema_fail", rp)

    result = _add_backward_compat(result)

    # --- LOGGING: [AGENT 3 DECISION] (FALLBACK) ---
    print(f"==============================")
    print(f"[AGENT 3 DECISION] (FALLBACK)")
    print(f"==============================")
    v2 = result.get("_v2_execution_decision", {})
    print(f"action(v2): {v2.get('action')} | direction: {v2.get('direction')}")
    print(f"compat: action={result.get('action')} | exec_dec={result.get('execution_decision')}")
    if v2.get("action") == "ENTER_NOW":
        ps = result.get("position_sizing", {})
        tp = result.get("trade_plan", {})
        print(f"\nEntry: {tp.get('entry_price')} | SL: {tp.get('stop_loss')} | Target: {tp.get('target_price')}")
        print(f"RR: {tp.get('risk_reward')} | Shares: {ps.get('quantity')} | Risk: Rs.{ps.get('risk_amount')}")
    else:
        print(f"Reason: {reason_text}")
    print(f"==============================\n")

    return result