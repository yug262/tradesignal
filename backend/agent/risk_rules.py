"""Risk Rules Engine — hard invalidation checks + weighted multi-factor scoring.

This module contains:
  1. Hard invalidation rules (override everything)
  2. Grouped risk scoring across 5 health buckets
  3. Final decision mapping from composite risk score

Architecture philosophy:
  - Hard rules fire first and can force EXIT_NOW regardless of other signals
  - Soft scoring groups indicators into logical buckets
  - NO single indicator alone triggers exit (except hard invalidations)
  - Time decay and trade mode (INTRADAY vs DELIVERY) affect thresholds
"""

from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS / CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

DECISIONS = ("HOLD", "HOLD_WITH_CAUTION", "TIGHTEN_STOPLOSS", "PARTIAL_EXIT", "EXIT_NOW")

THESIS_STATES = ("intact", "weakening", "damaged", "broken")

URGENCY_LEVELS = ("none", "low", "medium", "high", "critical")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HARD INVALIDATION RULES
# ═══════════════════════════════════════════════════════════════════════════════

def check_hard_invalidations(features: dict) -> Optional[dict]:
    """Check for hard invalidation conditions that override all soft logic.

    Returns None if no hard invalidation is triggered.
    Returns a dict with decision info if a hard rule fires.
    """
    triggered = []
    is_long = features.get("is_long", True)
    ltp = features.get("ltp", 0)
    stop_loss = features.get("stop_loss", 0)
    entry_price = features.get("entry_price", 0)
    sl_proximity = features.get("sl_proximity", "safe")

    # ── RULE 1: Stop-loss breached ────────────────────────────────────────
    if sl_proximity == "breached":
        return {
            "decision": "EXIT_NOW",
            "confidence": 99,
            "risk_score": 100,
            "thesis_status": "broken",
            "exit_urgency": "critical",
            "primary_reason": "Stop-loss has been breached. Hard exit required.",
            "triggered_risks": ["sl_breached"],
            "execution_note": "Exit immediately at market. Stop-loss invalidation.",
        }

    # ── RULE 2: SL in danger zone + aggressive selling + bearish reversal ─
    if (
        sl_proximity == "danger"
        and features.get("aggressive_selling_detected", False)
        and features.get("strong_bearish_reversal_candle", False)
    ):
        triggered.append("sl_danger_with_aggressive_selling_and_reversal")
        return {
            "decision": "EXIT_NOW",
            "confidence": 95,
            "risk_score": 95,
            "thesis_status": "broken",
            "exit_urgency": "critical",
            "primary_reason": (
                "Price near stop-loss with aggressive selling pressure "
                "and strong reversal candle. Trade thesis is clearly broken."
            ),
            "triggered_risks": triggered,
            "execution_note": "Exit immediately. Multiple hard signals confirm breakdown.",
        }

    # ── RULE 3: Major structure broken (lower high + close near low + pullback aggressive) ─
    if is_long and all([
        features.get("lower_high_detected", False),
        features.get("close_near_low", False),
        features.get("pullback_behavior") == "aggressive",
        sl_proximity in ("danger", "close"),
    ]):
        triggered.append("structure_breakdown_for_long")
        return {
            "decision": "EXIT_NOW",
            "confidence": 92,
            "risk_score": 92,
            "thesis_status": "broken",
            "exit_urgency": "critical",
            "primary_reason": (
                "Long trade structure has broken: lower highs forming, "
                "close near day low, aggressive pullback, and approaching stop-loss."
            ),
            "triggered_risks": triggered,
            "execution_note": "Exit. Structural breakdown confirmed.",
        }

    # ── RULE 4: Intraday time expiry ─────────────────────────────────────
    trade_mode = features.get("trade_mode", "INTRADAY")
    time_in_trade = features.get("time_in_trade_seconds", 0)
    time_decay = features.get("time_decay_state", "fresh")

    if trade_mode == "INTRADAY" and time_in_trade > 18000:  # > 5 hours
        if not features.get("follow_through_seen", False):
            triggered.append("intraday_time_expired_without_followthrough")
            return {
                "decision": "EXIT_NOW",
                "confidence": 88,
                "risk_score": 88,
                "thesis_status": "damaged",
                "exit_urgency": "high",
                "primary_reason": (
                    "Intraday trade has been open for over 5 hours "
                    "without meaningful follow-through. "
                    "Impact window has likely passed."
                ),
                "triggered_risks": triggered,
                "execution_note": "Exit before close. Intraday edge has expired.",
            }

    # No hard invalidation triggered
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. WEIGHTED RISK SCORING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def compute_risk_score(features: dict) -> dict:
    """Compute multi-factor risk score across 5 health buckets.

    Buckets and their weights:
      A. Thesis Health       (25%) — entry zone, follow-through, time decay
      B. Price Action Health (25%) — pullback, structure, candle behavior
      C. Momentum Health     (20%) — RSI, MACD, Supertrend
      D. Volatility/Volume   (15%) — ATR, volume, overbought/oversold
      E. Microstructure      (15%) — market depth, selling detection

    Each bucket scores 0-100 (0 = no risk, 100 = maximum risk).
    Composite is the weighted average.

    Returns:
        Dict with bucket_scores, composite_score, triggered_risks, thesis_status
    """
    is_long = features.get("is_long", True)
    trade_mode = features.get("trade_mode", "INTRADAY")
    triggered_risks = []

    # ── BUCKET A: Thesis Health (25%) ────────────────────────────────────
    a_score = 0

    # Distance from entry (for longs, negative = underwater)
    dist_entry = features.get("distance_from_entry_percent", 0)
    if is_long:
        if dist_entry < -2.0:
            a_score += 30
            triggered_risks.append("significantly_underwater")
        elif dist_entry < -0.5:
            a_score += 15
            triggered_risks.append("slightly_underwater")
        elif dist_entry > 1.0:
            a_score -= 10  # Reward: in profit
    else:
        if dist_entry > 2.0:
            a_score += 30
            triggered_risks.append("significantly_underwater_short")
        elif dist_entry > 0.5:
            a_score += 15

    # Follow-through
    if not features.get("follow_through_seen", False):
        time_decay = features.get("time_decay_state", "fresh")
        if time_decay == "fresh":
            a_score += 5   # Still early, no penalty
        elif time_decay == "acceptable":
            a_score += 15
        elif time_decay == "aging":
            a_score += 25
            triggered_risks.append("no_followthrough_aging")
        elif time_decay in ("decaying", "stale"):
            a_score += 35
            triggered_risks.append("no_followthrough_stale")

    # Entry zone lost
    if not features.get("entry_zone_held", True):
        a_score += 15
        triggered_risks.append("entry_zone_lost")

    # Time decay itself
    td = features.get("time_decay_state", "fresh")
    if td == "decaying":
        a_score += 10
    elif td == "stale":
        a_score += 20
        triggered_risks.append("time_decay_stale")

    a_score = max(0, min(100, a_score))

    # ── BUCKET B: Price Action Health (25%) ──────────────────────────────
    b_score = 0

    # Pullback behavior
    pb = features.get("pullback_behavior", "unknown")
    if pb == "aggressive":
        b_score += 30
        triggered_risks.append("aggressive_pullback")
    elif pb == "moderate":
        b_score += 15
    elif pb == "healthy_small":
        b_score += 5  # Normal

    # SL proximity
    sl_prox = features.get("sl_proximity", "safe")
    if sl_prox == "danger":
        b_score += 25
        triggered_risks.append("sl_proximity_danger")
    elif sl_prox == "close":
        b_score += 15
        triggered_risks.append("sl_proximity_close")

    # Structure
    struct = features.get("recent_structure", "unknown")
    if is_long and struct == "lower_lows":
        b_score += 20
        triggered_risks.append("lower_lows_in_long")
    elif not is_long and struct == "higher_highs":
        b_score += 20

    # Bearish reversal candle
    if features.get("strong_bearish_reversal_candle", False) and is_long:
        b_score += 15
        triggered_risks.append("bearish_reversal_candle")

    # Close near low (for longs)
    if features.get("close_near_low", False) and is_long:
        b_score += 10
        triggered_risks.append("close_near_low")

    # Lower high detection
    if features.get("lower_high_detected", False) and is_long:
        b_score += 15
        triggered_risks.append("lower_high_pattern")

    b_score = max(0, min(100, b_score))

    # ── BUCKET C: Momentum Health (20%) ──────────────────────────────────
    c_score = 0

    # RSI state
    rsi_state = features.get("rsi_state", "unavailable")
    if rsi_state == "overbought_extreme" and is_long:
        c_score += 15
        triggered_risks.append("rsi_overbought_extreme")
    elif rsi_state == "overbought" and is_long:
        c_score += 8
    elif rsi_state == "weakening" and is_long:
        c_score += 20
        triggered_risks.append("rsi_weakening")
    elif rsi_state == "oversold" and is_long:
        c_score += 25
        triggered_risks.append("rsi_oversold_long")
    elif rsi_state == "oversold_extreme" and is_long:
        c_score += 30
        triggered_risks.append("rsi_oversold_extreme_long")
    elif rsi_state == "supportive":
        c_score -= 5  # Reward

    # Supertrend
    st = features.get("supertrend_state", "unknown")
    if is_long and st == "red":
        c_score += 20
        triggered_risks.append("supertrend_red_long")
    elif not is_long and st == "green":
        c_score += 20
    elif is_long and st == "green":
        c_score -= 5

    # MACD
    macd = features.get("macd_cross_state", "unknown")
    if is_long and macd == "bearish_cross":
        c_score += 15
        triggered_risks.append("macd_bearish_cross")
    elif is_long and macd == "bearish":
        c_score += 8
    elif not is_long and macd == "bullish_cross":
        c_score += 15
    elif is_long and macd in ("bullish", "bullish_cross"):
        c_score -= 5

    c_score = max(0, min(100, c_score))

    # ── BUCKET D: Volatility / Volume Health (15%) ───────────────────────
    d_score = 0

    # ATR context
    atr = features.get("atr_context", "normal")
    if atr == "high_volatility":
        d_score += 15
        triggered_risks.append("high_volatility")
    elif atr == "elevated":
        d_score += 8

    # Volume pressure
    vp = features.get("volume_pressure", "normal")
    if vp == "surge" and features.get("strong_bearish_reversal_candle", False):
        d_score += 25
        triggered_risks.append("volume_surge_with_reversal")
    elif vp == "surge":
        d_score += 10
    elif vp == "below_average":
        d_score += 5  # Low conviction move

    # Overbought/oversold with context
    obs = features.get("overbought_oversold_state", "neutral")
    if obs == "overbought_with_rejection":
        d_score += 25
        triggered_risks.append("overbought_rejection")
    elif obs == "overbought_with_volume":
        d_score += 15
        triggered_risks.append("overbought_with_volume")
    elif obs == "overbought_mild":
        d_score += 5

    # Volatility state
    vs = features.get("volatility_state", "normal")
    if vs == "extreme":
        d_score += 10

    d_score = max(0, min(100, d_score))

    # ── BUCKET E: Microstructure Health (15%) ────────────────────────────
    e_score = 0

    # Market depth
    md = features.get("market_depth_state", "balanced")
    if is_long:
        if md == "seller_heavy":
            e_score += 25
            triggered_risks.append("seller_heavy_depth")
        elif md == "seller_leaning":
            e_score += 12
        elif md == "buyer_supportive":
            e_score -= 5
        elif md == "buyer_heavy":
            e_score -= 10
    else:
        if md == "buyer_heavy":
            e_score += 25
        elif md == "buyer_supportive":
            e_score += 12
        elif md == "seller_leaning":
            e_score -= 5

    # Aggressive selling detection
    if features.get("aggressive_selling_detected", False):
        e_score += 30
        triggered_risks.append("aggressive_selling")

    e_score = max(0, min(100, e_score))

    # ── COMPOSITE SCORE ──────────────────────────────────────────────────
    weights = {
        "thesis_health": 0.25,
        "price_action_health": 0.25,
        "momentum_health": 0.20,
        "volatility_volume_health": 0.15,
        "microstructure_health": 0.15,
    }

    composite = (
        a_score * weights["thesis_health"]
        + b_score * weights["price_action_health"]
        + c_score * weights["momentum_health"]
        + d_score * weights["volatility_volume_health"]
        + e_score * weights["microstructure_health"]
    )
    composite = round(max(0, min(100, composite)), 1)

    # ── Thesis status derived from score ─────────────────────────────────
    if composite >= 75:
        thesis_status = "broken"
    elif composite >= 50:
        thesis_status = "damaged"
    elif composite >= 30:
        thesis_status = "weakening"
    else:
        thesis_status = "intact"

    return {
        "bucket_scores": {
            "thesis_health": round(a_score, 1),
            "price_action_health": round(b_score, 1),
            "momentum_health": round(c_score, 1),
            "volatility_volume_health": round(d_score, 1),
            "microstructure_health": round(e_score, 1),
        },
        "composite_score": composite,
        "triggered_risks": list(set(triggered_risks)),
        "thesis_status": thesis_status,
        "weights_used": weights,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FINAL DECISION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def determine_risk_decision(
    features: dict,
    risk_scoring: dict,
    hard_invalidation: Optional[dict] = None,
) -> dict:
    """Merge hard invalidation + soft scoring into a final risk monitor decision.

    Returns the complete risk monitor output dict.
    """
    # If hard invalidation fired, it takes priority
    if hard_invalidation is not None:
        return _build_output(
            features=features,
            decision=hard_invalidation["decision"],
            confidence=hard_invalidation["confidence"],
            risk_score=hard_invalidation["risk_score"],
            thesis_status=hard_invalidation["thesis_status"],
            exit_urgency=hard_invalidation["exit_urgency"],
            primary_reason=hard_invalidation["primary_reason"],
            triggered_risks=hard_invalidation["triggered_risks"],
            execution_note=hard_invalidation["execution_note"],
            updated_stop_loss=None,
            source="hard_invalidation",
        )

    # Use soft scoring
    composite = risk_scoring["composite_score"]
    thesis_status = risk_scoring["thesis_status"]
    triggered = risk_scoring["triggered_risks"]
    buckets = risk_scoring["bucket_scores"]

    # Decision thresholds — vary by trade mode
    trade_mode = features.get("trade_mode", "INTRADAY")

    if trade_mode == "INTRADAY":
        exit_now_threshold = 70
        partial_exit_threshold = 55
        tighten_threshold = 40
        caution_threshold = 25
    else:  # DELIVERY — more patient
        exit_now_threshold = 80
        partial_exit_threshold = 65
        tighten_threshold = 50
        caution_threshold = 35

    # Multi-risk amplification: if 3+ distinct risks are triggered, escalate
    risk_count = len(triggered)
    if risk_count >= 5:
        composite = min(100, composite * 1.15)
    elif risk_count >= 3:
        composite = min(100, composite * 1.08)

    # Determine decision
    if composite >= exit_now_threshold:
        decision = "EXIT_NOW"
        exit_urgency = "critical"
        confidence = min(95, int(50 + composite * 0.45))
    elif composite >= partial_exit_threshold:
        decision = "PARTIAL_EXIT"
        exit_urgency = "high"
        confidence = min(85, int(40 + composite * 0.45))
    elif composite >= tighten_threshold:
        decision = "TIGHTEN_STOPLOSS"
        exit_urgency = "medium"
        confidence = min(80, int(50 + composite * 0.3))
    elif composite >= caution_threshold:
        decision = "HOLD_WITH_CAUTION"
        exit_urgency = "low"
        confidence = min(75, int(55 + composite * 0.2))
    else:
        decision = "HOLD"
        exit_urgency = "none"
        confidence = min(85, int(70 + (100 - composite) * 0.15))

    # Build primary reason from top risk bucket
    top_bucket = max(buckets, key=buckets.get)
    top_bucket_score = buckets[top_bucket]
    primary_reason = _build_primary_reason(decision, top_bucket, top_bucket_score, triggered, features)

    # Compute updated stop loss for TIGHTEN_STOPLOSS
    updated_sl = None
    if decision == "TIGHTEN_STOPLOSS":
        updated_sl = _compute_tightened_stoploss(features)

    execution_note = _build_execution_note(decision, features, triggered)

    return _build_output(
        features=features,
        decision=decision,
        confidence=confidence,
        risk_score=round(composite, 1),
        thesis_status=thesis_status,
        exit_urgency=exit_urgency,
        primary_reason=primary_reason,
        triggered_risks=triggered,
        execution_note=execution_note,
        updated_stop_loss=updated_sl,
        source="rule_engine",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _build_output(
    features: dict,
    decision: str,
    confidence: int,
    risk_score: float,
    thesis_status: str,
    exit_urgency: str,
    primary_reason: str,
    triggered_risks: list,
    execution_note: str,
    updated_stop_loss: Optional[float],
    source: str,
) -> dict:
    """Build the final standardized risk monitor output."""
    return {
        "decision": decision,
        "confidence": confidence,
        "risk_score": risk_score,
        "thesis_status": thesis_status,
        "exit_urgency": exit_urgency,
        "action_type": decision,
        "updated_stop_loss": updated_stop_loss,
        "primary_reason": primary_reason,
        "detailed_reasoning": {
            "distance_to_stoploss": features.get("sl_proximity", "unknown"),
            "impact_persistence": _infer_impact_persistence(features),
            "pullback_behavior": features.get("pullback_behavior", "unknown"),
            "time_decay": features.get("time_decay_state", "unknown"),
            "invalidation_status": (
                "triggered" if decision == "EXIT_NOW" else
                "approaching" if decision in ("PARTIAL_EXIT", "TIGHTEN_STOPLOSS") else
                "not_triggered"
            ),
            "rsi_state": features.get("rsi_state", "unavailable"),
            "supertrend_state": features.get("supertrend_state", "unknown"),
            "macd_state": features.get("macd_cross_state", "unknown"),
            "atr_volatility_state": features.get("atr_context", "unknown"),
            "volume_state": features.get("volume_pressure", "unknown"),
            "market_depth_state": features.get("market_depth_state", "unknown"),
            "ohlc_structure_state": features.get("recent_structure", "unknown"),
        },
        "triggered_risks": triggered_risks[:10],
        "execution_note": execution_note,
        "next_review_priority": (
            "urgent" if decision == "EXIT_NOW" else
            "high" if decision in ("PARTIAL_EXIT", "TIGHTEN_STOPLOSS") else
            "normal"
        ),
        "_source": source,
        "_features_snapshot": {
            "ltp": features.get("ltp"),
            "entry_price": features.get("entry_price"),
            "stop_loss": features.get("stop_loss"),
            "target_price": features.get("target_price"),
            "time_in_trade_seconds": features.get("time_in_trade_seconds"),
            "trade_mode": features.get("trade_mode"),
            "direction": features.get("direction"),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _infer_impact_persistence(features: dict) -> str:
    """Infer whether the original trade catalyst is still active."""
    follow = features.get("follow_through_seen", False)
    entry_held = features.get("entry_zone_held", True)
    time_decay = features.get("time_decay_state", "fresh")

    if follow and entry_held and time_decay in ("fresh", "acceptable"):
        return "stable"
    elif follow and time_decay in ("aging",):
        return "fading"
    elif not follow and time_decay in ("decaying", "stale"):
        return "expired"
    elif not entry_held:
        return "reversed"
    else:
        return "uncertain"


def _build_primary_reason(
    decision: str,
    top_bucket: str,
    top_score: float,
    triggered: list,
    features: dict,
) -> str:
    """Build a human-readable primary reason for the decision."""
    bucket_names = {
        "thesis_health": "trade thesis health",
        "price_action_health": "price action",
        "momentum_health": "momentum indicators",
        "volatility_volume_health": "volatility and volume",
        "microstructure_health": "market microstructure",
    }

    bucket_label = bucket_names.get(top_bucket, top_bucket)

    if decision == "HOLD":
        return (
            "Trade thesis remains intact and risk levels are within acceptable range. "
            "Continue holding while structure remains supportive."
        )
    elif decision == "HOLD_WITH_CAUTION":
        return (
            f"Trade is still viable but showing early warning signs in {bucket_label}. "
            f"Monitor closely for deterioration."
        )
    elif decision == "TIGHTEN_STOPLOSS":
        return (
            f"Risk is elevated due to {bucket_label} degradation. "
            f"Tighten stop-loss to protect existing gains and reduce exposure."
        )
    elif decision == "PARTIAL_EXIT":
        risk_names = ", ".join(triggered[:3]) if triggered else "multiple factors"
        return (
            f"Multiple risk signals aligning ({risk_names}). "
            f"Reduce position to manage downside while keeping partial exposure."
        )
    elif decision == "EXIT_NOW":
        risk_names = ", ".join(triggered[:3]) if triggered else "severe risk"
        return (
            f"Trade edge has deteriorated significantly. "
            f"Exit is recommended due to: {risk_names}."
        )
    return "Risk assessment complete."


def _build_execution_note(decision: str, features: dict, triggered: list) -> str:
    """Build actionable execution note."""
    mode = features.get("trade_mode", "INTRADAY")
    ltp = features.get("ltp", 0)

    if decision == "HOLD":
        return f"Continue holding. Current LTP: ₹{ltp:.2f}. No action required."
    elif decision == "HOLD_WITH_CAUTION":
        return (
            f"Hold with tighter monitoring. Watch for: "
            f"{', '.join(triggered[:2]) if triggered else 'further deterioration'}."
        )
    elif decision == "TIGHTEN_STOPLOSS":
        new_sl = _compute_tightened_stoploss(features)
        sl_note = f" Suggested new SL: ₹{new_sl:.2f}." if new_sl else ""
        return f"Move stop-loss closer to protect position.{sl_note}"
    elif decision == "PARTIAL_EXIT":
        return (
            f"Exit 50% of position at market (₹{ltp:.2f}). "
            f"Trail remaining with tight stop."
        )
    elif decision == "EXIT_NOW":
        return f"Exit full position immediately at market. Current LTP: ₹{ltp:.2f}."
    return "Monitor trade."


def _compute_tightened_stoploss(features: dict) -> Optional[float]:
    """Compute a tightened stop-loss level."""
    ltp = features.get("ltp", 0)
    entry_price = features.get("entry_price", 0)
    stop_loss = features.get("stop_loss", 0)
    is_long = features.get("is_long", True)
    vwap = features.get("vwap", 0)
    day_low = features.get("day_low", 0)

    if ltp <= 0 or entry_price <= 0:
        return None

    if is_long:
        # Move SL to breakeven or just below recent structure
        candidates = [entry_price]  # At minimum, breakeven
        if vwap > 0 and vwap < ltp:
            candidates.append(round(vwap * 0.998, 2))  # Just below VWAP
        if day_low > 0 and day_low < ltp:
            candidates.append(round(day_low * 0.998, 2))  # Just below day low

        # Pick the highest candidate that is above current SL
        valid = [c for c in candidates if c > stop_loss and c < ltp]
        if valid:
            return round(max(valid), 2)
    else:
        # For shorts, tighten SL downward
        candidates = [entry_price]
        if vwap > 0 and vwap > ltp:
            candidates.append(round(vwap * 1.002, 2))

        valid = [c for c in candidates if c < stop_loss and c > ltp]
        if valid:
            return round(min(valid), 2)

    return None
