"""Risk Agent Validator — guardrails and safety enforcement for Agent 4 output.

This module sits between the LLM risk agent and the execution layer.
It validates, sanitizes, and enforces hard safety rules on the agent's output.

Architecture:
  Agent Raw Output → validate_agent_output() → Safe Final Output

The validator ensures:
  1. Schema completeness — all required fields present with correct types
  2. Enum legality — decision, thesis_status, urgency are valid values
  3. Stop-loss legality — never widens, never crosses LTP, direction-correct
  4. Exit fraction bounds — between 0 and 1
  5. Confidence bounds — integer 0-100
  6. Decision consistency — decision matches other fields logically
  7. Hard overrides — catastrophic conditions override agent judgment

The validator NEVER crashes. On any validation failure, it produces a
safe fallback output with full audit trail of what was changed and why.
"""

import logging
from typing import Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("agent.execution.risk_agent_validator")

IST = timezone(timedelta(hours=5, minutes=30))

# ═══════════════════════════════════════════════════════════════════════════════
# ALLOWED VALUES
# ═══════════════════════════════════════════════════════════════════════════════

ALLOWED_DECISIONS = {"HOLD", "TIGHTEN_STOPLOSS", "PARTIAL_EXIT", "EXIT_NOW"}
ALLOWED_THESIS_STATUS = {"intact", "weakening", "broken"}
ALLOWED_URGENCY = {"low", "medium", "high"}

# Hard safety thresholds (non-negotiable)
HARD_MAX_LOSS_PERCENT = 5.0             # Absolute max loss before forced exit
HARD_MAX_LOSS_RUPEES_TOTAL = 10000.0    # Absolute max rupee loss
INTRADAY_FORCED_EXIT_HHMM = 1520       # Force exit intraday trades after 15:20

# Confidence thresholds for decision gating
MIN_CONFIDENCE_FOR_EXIT = 40            # Below this, EXIT_NOW requires hard override
MIN_CONFIDENCE_FOR_PARTIAL = 35         # Below this, PARTIAL_EXIT downgrades to TIGHTEN/HOLD


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN VALIDATOR ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def validate_agent_output(
    raw_output: dict,
    features: dict,
    apply_hard_overrides: bool = True,
) -> dict:
    """Validate and sanitize the risk agent's raw output.

    Args:
        raw_output: Raw dict from the LLM agent (or fallback)
        features: The extracted risk features for this trade
        apply_hard_overrides: If True, apply catastrophic protection overrides

    Returns:
        Validated output dict with additional fields:
        - _validation_status: "clean" | "sanitized" | "fallback"
        - _overrides_applied: list of override descriptions
        - _original_decision: original decision before any overrides
    """
    overrides = []
    original_decision = None

    # ── Step 1: Schema validation and sanitization ───────────────────────
    result = _sanitize_schema(raw_output, overrides)

    # ── Step 2: Stop-loss legality ───────────────────────────────────────
    result = _validate_stop_loss(result, features, overrides)

    # ── Step 3: Exit fraction bounds ─────────────────────────────────────
    result = _validate_exit_fraction(result, overrides)

    # ── Step 4: Decision consistency ─────────────────────────────────────
    result = _validate_decision_consistency(result, overrides)

    # ── Step 5: Confidence weighting (Gate 4) ──────────────────────────
    result = _apply_confidence_gating(result, features, overrides)

    # ── Step 6: Hard overrides (catastrophic protection) ─────────────────
    if apply_hard_overrides:
        original_decision = result.get("decision", "HOLD")
        result = _apply_hard_overrides(result, features, overrides)

    # ── Attach audit metadata ────────────────────────────────────────────
    if overrides:
        result["_validation_status"] = "sanitized"
    else:
        result["_validation_status"] = "clean"

    result["_overrides_applied"] = overrides
    if original_decision and original_decision != result.get("decision"):
        result["_original_decision"] = original_decision

    # ── Gap 5: Explicit source tagging for UI ──────────────────────────
    source = raw_output.get("_source", "unknown")
    result["_decision_source"] = source
    result["_decision_source_label"] = _get_source_label(source)

    # Preserve features snapshot for downstream logging
    result["_features_snapshot"] = _build_features_snapshot(features)

    # Carry forward PnL data for dashboard display
    result["pnl_percent"] = features.get("pnl_percent", 0)
    result["pnl_rupees_total"] = features.get("pnl_rupees_total", 0)
    result["time_in_trade_seconds"] = features.get("time_in_trade_seconds", 0)

    # Map triggered_factors to triggered_rules for backward compatibility
    result["triggered_rules"] = result.get("triggered_factors", [])

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA SANITIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def _sanitize_schema(raw: dict, overrides: list) -> dict:
    """Ensure all required fields exist with correct types."""
    result = dict(raw) if isinstance(raw, dict) else {}

    # Decision
    decision = str(result.get("decision", "HOLD")).upper().strip()
    if decision not in ALLOWED_DECISIONS:
        overrides.append(f"decision '{decision}' invalid, defaulted to HOLD")
        decision = "HOLD"
    result["decision"] = decision

    # Reason code
    reason_code = result.get("reason_code")
    if not isinstance(reason_code, str) or not reason_code.strip():
        result["reason_code"] = "UNKNOWN"
        overrides.append("reason_code was missing or empty")

    # Primary reason
    primary_reason = result.get("primary_reason")
    if not isinstance(primary_reason, str) or not primary_reason.strip():
        result["primary_reason"] = f"Agent decided {decision}."
        overrides.append("primary_reason was missing")

    # Updated stop loss
    updated_sl = result.get("updated_stop_loss")
    if updated_sl is not None:
        try:
            result["updated_stop_loss"] = round(float(updated_sl), 2)
        except (ValueError, TypeError):
            result["updated_stop_loss"] = None
            overrides.append("updated_stop_loss was not a valid number")

    # Exit fraction
    exit_fraction = result.get("exit_fraction")
    try:
        result["exit_fraction"] = float(exit_fraction) if exit_fraction is not None else 0.0
    except (ValueError, TypeError):
        result["exit_fraction"] = 0.0
        overrides.append("exit_fraction was not a valid number")

    # Confidence
    conf = result.get("confidence", 50)
    try:
        conf = int(conf)
    except (ValueError, TypeError):
        conf = 50
        overrides.append("confidence was not a valid integer")
    result["confidence"] = max(0, min(100, conf))

    # Thesis status
    thesis = str(result.get("thesis_status", "intact")).lower().strip()
    if thesis not in ALLOWED_THESIS_STATUS:
        overrides.append(f"thesis_status '{thesis}' invalid, defaulted to intact")
        thesis = "intact"
    result["thesis_status"] = thesis

    # Urgency
    urgency = str(result.get("urgency", "low")).lower().strip()
    if urgency not in ALLOWED_URGENCY:
        overrides.append(f"urgency '{urgency}' invalid, defaulted to low")
        urgency = "low"
    result["urgency"] = urgency

    # List fields
    for field in ("triggered_factors", "risk_flags"):
        val = result.get(field)
        if not isinstance(val, list):
            result[field] = []
            if val is not None:
                overrides.append(f"{field} was not a list")

    # Monitoring note
    note = result.get("monitoring_note")
    if not isinstance(note, str):
        result["monitoring_note"] = ""

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STOP-LOSS VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_stop_loss(result: dict, features: dict, overrides: list) -> dict:
    """Enforce stop-loss direction and legality rules.

    Rules:
    1. For LONG trades: new SL must be ABOVE current SL (tighter)
    2. For LONG trades: new SL must be BELOW LTP (not crossed)
    3. For SHORT trades: new SL must be BELOW current SL (tighter)
    4. For SHORT trades: new SL must be ABOVE LTP (not crossed)
    5. If any rule is violated, the SL update is nullified
    """
    new_sl = result.get("updated_stop_loss")
    if new_sl is None:
        return result

    decision = result.get("decision", "HOLD")
    if decision not in ("TIGHTEN_STOPLOSS",):
        # Only TIGHTEN_STOPLOSS should have a new SL
        if decision in ("HOLD", "EXIT_NOW"):
            result["updated_stop_loss"] = None
            if decision == "HOLD":
                overrides.append("cleared updated_stop_loss on HOLD decision")
        return result

    is_long = features.get("is_long", True)
    current_sl = features.get("stop_loss", 0)
    ltp = features.get("ltp", 0)

    if current_sl <= 0 or ltp <= 0:
        result["updated_stop_loss"] = None
        overrides.append("cleared SL update: current SL or LTP is zero/invalid")
        return result

    if is_long:
        # Long: new SL must be above current SL
        if new_sl <= current_sl:
            result["updated_stop_loss"] = None
            overrides.append(
                f"rejected SL update: new SL ₹{new_sl:.2f} <= current SL ₹{current_sl:.2f} (long)"
            )
            return result

        # Long: new SL must be below LTP
        if new_sl >= ltp:
            result["updated_stop_loss"] = None
            overrides.append(
                f"rejected SL update: new SL ₹{new_sl:.2f} >= LTP ₹{ltp:.2f} (long, crosses price)"
            )
            return result
    else:
        # Short: new SL must be below current SL
        if new_sl >= current_sl:
            result["updated_stop_loss"] = None
            overrides.append(
                f"rejected SL update: new SL ₹{new_sl:.2f} >= current SL ₹{current_sl:.2f} (short)"
            )
            return result

        # Short: new SL must be above LTP
        if new_sl <= ltp:
            result["updated_stop_loss"] = None
            overrides.append(
                f"rejected SL update: new SL ₹{new_sl:.2f} <= LTP ₹{ltp:.2f} (short, crosses price)"
            )
            return result

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# EXIT FRACTION VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_exit_fraction(result: dict, overrides: list) -> dict:
    """Ensure exit_fraction is within bounds and consistent with decision."""
    decision = result.get("decision", "HOLD")
    ef = result.get("exit_fraction", 0.0)

    if decision == "EXIT_NOW":
        if ef != 1.0:
            result["exit_fraction"] = 1.0
            overrides.append("forced exit_fraction to 1.0 for EXIT_NOW")

    elif decision == "PARTIAL_EXIT":
        if ef <= 0.0 or ef >= 1.0:
            result["exit_fraction"] = 0.5
            overrides.append(f"exit_fraction {ef} invalid for PARTIAL_EXIT, defaulted to 0.5")
        else:
            result["exit_fraction"] = round(max(0.01, min(0.99, ef)), 2)

    elif decision in ("HOLD", "TIGHTEN_STOPLOSS"):
        if ef != 0.0:
            result["exit_fraction"] = 0.0
            overrides.append(f"forced exit_fraction to 0.0 for {decision}")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# DECISION CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_decision_consistency(result: dict, overrides: list) -> dict:
    """Ensure internal consistency between decision and other fields."""
    decision = result.get("decision", "HOLD")

    # TIGHTEN_STOPLOSS without a valid new SL is degraded to HOLD
    if decision == "TIGHTEN_STOPLOSS" and result.get("updated_stop_loss") is None:
        result["decision"] = "HOLD"
        overrides.append("degraded TIGHTEN_STOPLOSS to HOLD: no valid stop-loss update")

    # EXIT_NOW should have broken or weakening thesis
    if decision == "EXIT_NOW" and result.get("thesis_status") == "intact":
        result["thesis_status"] = "weakening"
        overrides.append("changed thesis_status to weakening for EXIT_NOW (was intact)")

    # HOLD should not have high urgency (contradictory)
    if decision == "HOLD" and result.get("urgency") == "high":
        result["urgency"] = "medium"
        overrides.append("lowered urgency to medium for HOLD (high urgency contradicts HOLD)")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# HARD OVERRIDES — catastrophic protection
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_hard_overrides(result: dict, features: dict, overrides: list) -> dict:
    """Apply non-negotiable safety overrides that supersede agent judgment.

    These are absolute last-resort protections that fire regardless of
    what the agent decided. They handle scenarios where the agent might
    have been too lenient or failed to detect a critical condition.
    """
    pnl_pct = features.get("pnl_percent", 0)
    pnl_rupees_total = features.get("pnl_rupees_total", 0)
    trade_mode = features.get("trade_mode", "INTRADAY")
    current_decision = result.get("decision", "HOLD")

    # ── Override 1: Catastrophic loss protection ─────────────────────────
    if pnl_pct <= -HARD_MAX_LOSS_PERCENT:
        if current_decision != "EXIT_NOW":
            overrides.append(
                f"HARD OVERRIDE: forced EXIT_NOW due to catastrophic loss "
                f"({pnl_pct:.1f}% exceeds -{HARD_MAX_LOSS_PERCENT}%)"
            )
            result["decision"] = "EXIT_NOW"
            result["reason_code"] = "HARD_MAX_LOSS_PERCENT"
            result["primary_reason"] = (
                f"Catastrophic loss override: trade at {pnl_pct:.1f}% loss "
                f"exceeds hard limit of -{HARD_MAX_LOSS_PERCENT}%."
            )
            result["exit_fraction"] = 1.0
            result["confidence"] = 99
            result["thesis_status"] = "broken"
            result["urgency"] = "high"
            result["updated_stop_loss"] = None

    # ── Override 2: Catastrophic rupee loss protection ────────────────────
    if pnl_rupees_total <= -HARD_MAX_LOSS_RUPEES_TOTAL:
        if current_decision != "EXIT_NOW":
            overrides.append(
                f"HARD OVERRIDE: forced EXIT_NOW due to rupee loss "
                f"(₹{abs(pnl_rupees_total):.0f} exceeds ₹{HARD_MAX_LOSS_RUPEES_TOTAL:.0f})"
            )
            result["decision"] = "EXIT_NOW"
            result["reason_code"] = "HARD_MAX_LOSS_RUPEES"
            result["primary_reason"] = (
                f"Catastrophic loss override: total loss ₹{abs(pnl_rupees_total):.0f} "
                f"exceeds hard limit of ₹{HARD_MAX_LOSS_RUPEES_TOTAL:.0f}."
            )
            result["exit_fraction"] = 1.0
            result["confidence"] = 99
            result["thesis_status"] = "broken"
            result["urgency"] = "high"
            result["updated_stop_loss"] = None

    # ── Override 3: Intraday forced exit before close ────────────────────
    if trade_mode == "INTRADAY":
        now_ist = datetime.now(IST)
        hhmm = now_ist.hour * 100 + now_ist.minute
        if hhmm >= INTRADAY_FORCED_EXIT_HHMM:
            if current_decision != "EXIT_NOW":
                overrides.append(
                    f"HARD OVERRIDE: forced EXIT_NOW for intraday trade "
                    f"at {now_ist.strftime('%H:%M')} IST (past {INTRADAY_FORCED_EXIT_HHMM})"
                )
                result["decision"] = "EXIT_NOW"
                result["reason_code"] = "HARD_INTRADAY_EXIT_BEFORE_CLOSE"
                result["primary_reason"] = (
                    f"Market close forced exit: {now_ist.strftime('%H:%M')} IST. "
                    f"Intraday position must be closed."
                )
                result["exit_fraction"] = 1.0
                result["confidence"] = 99
                result["urgency"] = "high"
                result["updated_stop_loss"] = None

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURES SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════════

def _build_features_snapshot(features: dict) -> dict:
    """Build a compact features snapshot for logging/debugging."""
    return {
        "symbol": features.get("symbol"),
        "quantity": features.get("quantity"),
        "trade_mode": features.get("trade_mode"),
        "direction": features.get("direction"),
        "ltp": features.get("ltp"),
        "entry_price": features.get("entry_price"),
        "stop_loss": features.get("stop_loss"),
        "target_price": features.get("target_price"),
        "pnl_percent": features.get("pnl_percent"),
        "mfe_pct": features.get("mfe_pct"),
        "mae_pct": features.get("mae_pct"),
        "distance_to_sl": features.get("distance_to_sl"),
        "relative_volume": features.get("relative_volume"),
        "structure_state": features.get("structure_state"),
        "depth_pressure": features.get("depth_pressure"),
        "depth_against_position": features.get("depth_against_position"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIDENCE GATING
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_confidence_gating(result: dict, features: dict, overrides: list) -> dict:
    """Gate aggressive decisions behind confidence thresholds.

    Low-confidence aggressive decisions are downgraded:
    - EXIT_NOW with confidence < 40 -> PARTIAL_EXIT (unless hard loss override applies)
    - PARTIAL_EXIT with confidence < 35 -> HOLD

    This prevents nervous/uncertain agent decisions from triggering
    irreversible actions. Hard overrides still fire after this stage.
    """
    decision = result.get("decision", "HOLD")
    confidence = result.get("confidence", 50)
    pnl_pct = features.get("pnl_percent", 0)

    # Don't gate if we're already in significant loss territory
    # (hard overrides will handle those regardless)
    in_significant_loss = pnl_pct <= -(HARD_MAX_LOSS_PERCENT * 0.6)  # ~-3.0%

    if decision == "EXIT_NOW" and confidence < MIN_CONFIDENCE_FOR_EXIT and not in_significant_loss:
        result["decision"] = "PARTIAL_EXIT"
        result["exit_fraction"] = 0.5
        overrides.append(
            f"confidence_gate: EXIT_NOW downgraded to PARTIAL_EXIT "
            f"(confidence={confidence} < {MIN_CONFIDENCE_FOR_EXIT}, pnl={pnl_pct:+.1f}%)"
        )
        result["risk_flags"] = result.get("risk_flags", []) + ["low_confidence_downgrade"]

    elif decision == "PARTIAL_EXIT" and confidence < MIN_CONFIDENCE_FOR_PARTIAL and not in_significant_loss:
        result["decision"] = "HOLD"
        result["exit_fraction"] = 0.0
        overrides.append(
            f"confidence_gate: PARTIAL_EXIT downgraded to HOLD "
            f"(confidence={confidence} < {MIN_CONFIDENCE_FOR_PARTIAL})"
        )
        result["risk_flags"] = result.get("risk_flags", []) + ["low_confidence_downgrade"]

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE LABELING
# ═══════════════════════════════════════════════════════════════════════════════

def _get_source_label(source: str) -> str:
    """Return a human-readable label for the decision source.

    This label is intended for display in the UI/dashboard.
    """
    labels = {
        "gemini_agent4": "AI Agent (Gemini)",
        "rule_engine_fallback": "Rule Engine (Fallback)",
        "agent4_fallback": "Safe Default (Agent Unavailable)",
        "agent4_parse_error": "Rule Engine (Agent Parse Error)",
        "data_error": "Safe Default (Data Unavailable)",
    }
    return labels.get(source, f"Unknown ({source})")
