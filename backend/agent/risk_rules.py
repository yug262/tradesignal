"""Risk Rules Engine — strict priority-based rule engine for live trade protection.

NO scoring. NO weighted buckets. NO composite risk scores.
NO RSI, MACD, Supertrend, ATR, or indicator-based logic.

Architecture:
  - Strict rule priority order (1-7)
  - First rule that triggers = final decision
  - Decisions: HOLD | TIGHTEN_STOPLOSS | PARTIAL_EXIT | EXIT_NOW
  - No HOLD_WITH_CAUTION

Stop-loss philosophy:
  - SL is dynamic (managed by this engine)
  - NEVER moves backward, ONLY tightens forward
  - Broker handles actual SL execution
  - This engine acts BEFORE SL gets hit

Priority order:
  1. Max Loss Protection
  2. Profit Locking
  3. Trailing Stop-Loss
  4. Time-Based Exit
  5. Volume Spike Against Position
  6. Trend Reversal Detection
  7. Default → HOLD
"""

import logging
from typing import Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("risk_rules")

IST = timezone(timedelta(hours=5, minutes=30))

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — Tunable thresholds
# ═══════════════════════════════════════════════════════════════════════════════

# Priority 1: Max Loss Protection
MAX_LOSS_PERCENT = 3.0          # Exit if trade loses more than 3% of entry
MAX_LOSS_RUPEES_TOTAL = 5000.0  # Exit if total position loss exceeds ₹5000

# Priority 2: Profit Locking tiers
BREAKEVEN_TRIGGER_PCT = 0.5     # Move SL to breakeven after +0.5% profit
PROFIT_LOCK_TIER1_PCT = 1.5     # After +1.5% profit, lock SL at +0.5%
PROFIT_LOCK_TIER2_PCT = 3.0     # After +3.0% profit, lock SL at +1.5%

# Priority 3: Trailing SL
TRAIL_STEP_PCT = 0.5            # Trail SL every 0.5% move in favor
TRAIL_BUFFER_PCT = 1.0          # Keep SL 1.0% behind LTP

# Priority 4: Time-based exit
INTRADAY_STALE_SECONDS = 14400      # 4 hours without meaningful progress
INTRADAY_CLOSE_EXIT_HHMM = 1510     # Exit before 3:10 PM for intraday
INTRADAY_NO_PROGRESS_SECONDS = 7200 # 2 hours with no profit
INTRADAY_NO_PROGRESS_MIN_PCT = 0.3  # Must be at least +0.3% by this time

DELIVERY_STALE_DAYS = 4             # ~4 days with no meaningful progress
DELIVERY_NO_PROGRESS_MIN_PCT = 1.0  # Must be at least +1.0% by this time

# Priority 5: Volume spike
VOLUME_SPIKE_THRESHOLD = 2.5    # Relative volume > 2.5x = spike

# Priority 6: Trend reversal
# Uses structure_state from features (reversing/healthy/neutral)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_trade(features: dict, config: dict = None) -> dict:
    """Run the strict priority rule engine on a single trade.

    Args:
        features: Output from risk_features.extract_risk_features()
        config: Optional overrides for thresholds (from system config)

    Returns:
        Decision dict with: decision, reason_code, primary_reason,
        updated_stop_loss, exit_fraction, confidence, triggered_rules,
        pnl_percent, time_in_trade_seconds
    """
    cfg = _merge_config(config)
    is_long = features.get("is_long", True)
    ltp = features.get("ltp", 0)
    entry_price = features.get("entry_price", 0)
    stop_loss = features.get("stop_loss", 0)
    target_price = features.get("target_price", 0)
    pnl_pct = features.get("pnl_percent", 0)
    pnl_rupees_total = features.get("pnl_rupees_total", 0)
    time_in_trade = features.get("time_in_trade_seconds", 0)
    trade_mode = features.get("trade_mode", "INTRADAY")
    symbol = features.get("symbol", "UNKNOWN")

    triggered_rules = []

    # ── PRIORITY 1: Max Loss Protection ──────────────────────────────────
    result = _check_max_loss(pnl_pct, pnl_rupees_total, cfg, triggered_rules)
    if result:
        return _build_output(result, features, triggered_rules)

    # ── PRIORITY 2: Profit Locking ───────────────────────────────────────
    result = _check_profit_lock(
        pnl_pct, ltp, entry_price, stop_loss, is_long, cfg, triggered_rules
    )
    if result:
        return _build_output(result, features, triggered_rules)

    # ── PRIORITY 3: Trailing Stop-Loss ───────────────────────────────────
    result = _check_trailing_sl(
        features, cfg, triggered_rules
    )
    if result:
        return _build_output(result, features, triggered_rules)

    # ── PRIORITY 4: Time-Based Exit ──────────────────────────────────────
    result = _check_time_exit(
        time_in_trade, pnl_pct, trade_mode, cfg, triggered_rules
    )
    if result:
        return _build_output(result, features, triggered_rules)

    # ── PRIORITY 5: Volume Spike Against Position ────────────────────────
    result = _check_volume_spike(features, cfg, triggered_rules)
    if result:
        return _build_output(result, features, triggered_rules)

    # ── PRIORITY 6: Trend Reversal Detection ─────────────────────────────
    result = _check_trend_reversal(features, cfg, triggered_rules)
    if result:
        return _build_output(result, features, triggered_rules)

    # ── PRIORITY 7: Default → HOLD ───────────────────────────────────────
    return _build_output(
        {
            "decision": "HOLD",
            "reason_code": "NO_RISK_TRIGGERED",
            "primary_reason": "All checks passed. Trade is healthy. Continue holding.",
            "updated_stop_loss": None,
            "exit_fraction": 0.0,
            "confidence": 85,
        },
        features,
        triggered_rules,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY 1: MAX LOSS PROTECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _check_max_loss(pnl_pct: float, pnl_rupees_total: float, cfg: dict, triggered: list) -> Optional[dict]:
    """Exit if trade loss exceeds allowed thresholds."""

    if pnl_pct <= -cfg["max_loss_percent"]:
        triggered.append("max_loss_percent")
        return {
            "decision": "EXIT_NOW",
            "reason_code": "MAX_LOSS_PERCENT",
            "primary_reason": (
                f"Trade loss ({pnl_pct:.1f}%) exceeds max allowed "
                f"(-{cfg['max_loss_percent']:.1f}%). Exiting to protect capital."
            ),
            "updated_stop_loss": None,
            "exit_fraction": 1.0,
            "confidence": 95,
        }

    if pnl_rupees_total <= -cfg["max_loss_rupees_total"]:
        triggered.append("max_loss_rupees")
        return {
            "decision": "EXIT_NOW",
            "reason_code": "MAX_LOSS_RUPEES",
            "primary_reason": (
                f"Total position loss (₹{abs(pnl_rupees_total):.0f}) exceeds max allowed "
                f"(₹{cfg['max_loss_rupees_total']:.0f}). Exiting to protect capital."
            ),
            "updated_stop_loss": None,
            "exit_fraction": 1.0,
            "confidence": 95,
        }

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY 2: PROFIT LOCKING
# ═══════════════════════════════════════════════════════════════════════════════

def _check_profit_lock(
    pnl_pct: float,
    ltp: float,
    entry_price: float,
    stop_loss: float,
    is_long: bool,
    cfg: dict,
    triggered: list,
) -> Optional[dict]:
    """Lock profits by moving SL to breakeven or into profit zone."""

    if entry_price <= 0 or ltp <= 0:
        return None

    if pnl_pct <= 0:
        return None

    new_sl = None
    reason_code = None
    reason_text = None

    # Tier 2: Strong profit → lock SL at entry + profit cushion
    if pnl_pct >= cfg["profit_lock_tier2_pct"]:
        if is_long:
            proposed_sl = round(entry_price * (1 + cfg["profit_lock_tier1_pct"] / 100), 2)
        else:
            proposed_sl = round(entry_price * (1 - cfg["profit_lock_tier1_pct"] / 100), 2)

        if _is_better_sl(proposed_sl, stop_loss, is_long):
            new_sl = proposed_sl
            reason_code = "PROFIT_LOCK_TIER_2"
            reason_text = (
                f"Trade is +{pnl_pct:.1f}%. Locking stop-loss at "
                f"+{cfg['profit_lock_tier1_pct']:.1f}% above entry to protect gains."
            )
            triggered.append("profit_lock_tier_2")

    # Tier 1: Moderate profit → lock SL at entry + small cushion
    elif pnl_pct >= cfg["profit_lock_tier1_pct"]:
        if is_long:
            proposed_sl = round(entry_price * (1 + cfg["breakeven_trigger_pct"] / 100), 2)
        else:
            proposed_sl = round(entry_price * (1 - cfg["breakeven_trigger_pct"] / 100), 2)

        if _is_better_sl(proposed_sl, stop_loss, is_long):
            new_sl = proposed_sl
            reason_code = "PROFIT_LOCK_TIER_1"
            reason_text = (
                f"Trade is +{pnl_pct:.1f}%. Locking stop-loss at "
                f"+{cfg['breakeven_trigger_pct']:.1f}% above entry."
            )
            triggered.append("profit_lock_tier_1")

    # Breakeven: Move SL to entry
    elif pnl_pct >= cfg["breakeven_trigger_pct"]:
        proposed_sl = entry_price
        if _is_better_sl(proposed_sl, stop_loss, is_long):
            new_sl = proposed_sl
            reason_code = "MOVE_TO_BREAKEVEN"
            reason_text = (
                f"Trade is +{pnl_pct:.1f}%. Moving stop-loss to breakeven "
                f"(₹{entry_price:.2f}) to eliminate downside risk."
            )
            triggered.append("move_to_breakeven")

    if new_sl is not None:
        return {
            "decision": "TIGHTEN_STOPLOSS",
            "reason_code": reason_code,
            "primary_reason": reason_text,
            "updated_stop_loss": new_sl,
            "exit_fraction": 0.0,
            "confidence": 90,
        }

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY 3: TRAILING STOP-LOSS
# ═══════════════════════════════════════════════════════════════════════════════

def _check_trailing_sl(
    features: dict,
    cfg: dict,
    triggered: list,
) -> Optional[dict]:
    """Trail stop-loss intelligently using structure, MFE, and fallback percentages."""
    
    pnl_pct = features.get("pnl_percent", 0)
    ltp = features.get("ltp", 0)
    entry_price = features.get("entry_price", 0)
    stop_loss = features.get("stop_loss", 0)
    target_price = features.get("target_price", 0)
    is_long = features.get("is_long", True)
    mfe_pct = features.get("mfe_pct", 0)
    recent_low = features.get("recent_swing_low", 0)
    recent_high = features.get("recent_swing_high", 0)

    if entry_price <= 0 or ltp <= 0 or stop_loss <= 0:
        return None

    # Only trail when in profit beyond breakeven trigger
    if pnl_pct < cfg["breakeven_trigger_pct"]:
        return None

    proposed_sl = 0.0
    reason_code = "TRAILING_SL_UPDATE"
    reason_text = "Trailing stop-loss to protect gains."
    
    # Check if target was touched/passed
    target_touched = False
    if target_price > 0:
        if is_long and mfe_pct >= _pct_diff(target_price, entry_price):
            target_touched = True
        elif not is_long and mfe_pct >= _pct_diff(entry_price, target_price):
            target_touched = True

    # 1. Preferred: Structure-aware trailing
    structure_sl = 0.0
    if is_long and recent_low > 0:
        structure_sl = round(recent_low * (1 - 0.002), 2)  # slightly below recent low
    elif not is_long and recent_high > 0:
        structure_sl = round(recent_high * (1 + 0.002), 2) # slightly above recent high
        
    # 2. Secondary: Percentage/Buffer trailing
    buffer_pct = cfg["trail_buffer_pct"]
    if target_touched:
        buffer_pct = buffer_pct * 0.4  # Aggressive trail if target touched
    elif mfe_pct > cfg["profit_lock_tier2_pct"]:
        buffer_pct = buffer_pct * 0.7  # Tighter trail on high MFE
        
    if is_long:
        pct_sl = round(ltp * (1 - buffer_pct / 100), 2)
    else:
        pct_sl = round(ltp * (1 + buffer_pct / 100), 2)
        
    # Choose the best SL (safest/tightest)
    if structure_sl > 0 and _is_better_sl(structure_sl, pct_sl, is_long):
        proposed_sl = structure_sl
        reason_code = "TRAIL_STRUCTURE"
        reason_text = f"Trailing stop-loss along recent market structure to ₹{proposed_sl:.2f}."
        triggered.append("trail_structure")
    else:
        proposed_sl = pct_sl
        if target_touched:
            reason_code = "TRAIL_AFTER_TARGET"
            reason_text = f"Target reached. Trailing stop-loss aggressively to ₹{proposed_sl:.2f}."
            triggered.append("trail_after_target")
        else:
            reason_code = "TRAIL_PERCENTAGE"
            reason_text = f"Price moved in favor (+{pnl_pct:.1f}%). Trailing SL to ₹{proposed_sl:.2f}."
            triggered.append("trail_percentage")

    # Only update if the proposed SL is strictly better than current SL
    if not _is_better_sl(proposed_sl, stop_loss, is_long):
        return None

    return {
        "decision": "TIGHTEN_STOPLOSS",
        "reason_code": reason_code,
        "primary_reason": reason_text,
        "updated_stop_loss": proposed_sl,
        "exit_fraction": 0.0,
        "confidence": 90,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY 4: TIME-BASED EXIT
# ═══════════════════════════════════════════════════════════════════════════════

def _check_time_exit(
    time_in_trade: float,
    pnl_pct: float,
    trade_mode: str,
    cfg: dict,
    triggered: list,
) -> Optional[dict]:
    """Exit stale intraday trades or trades nearing market close."""

    if trade_mode == "INTRADAY":
        # Check market close proximity
        now = datetime.now(IST)
        hhmm = now.hour * 100 + now.minute

        if hhmm >= cfg["intraday_close_exit_hhmm"]:
            triggered.append("exit_before_close")
            return {
                "decision": "EXIT_NOW",
                "reason_code": "EXIT_BEFORE_CLOSE",
                "primary_reason": (
                    f"Market close approaching ({now.strftime('%H:%M')} IST). "
                    f"Exiting intraday position to avoid overnight risk."
                ),
                "updated_stop_loss": None,
                "exit_fraction": 1.0,
                "confidence": 95,
            }

        # Check stale trade
        if time_in_trade >= cfg["intraday_stale_seconds"] and pnl_pct < cfg["intraday_no_progress_min_pct"]:
            triggered.append("trade_stale")
            hours = int(time_in_trade // 3600)
            mins = int((time_in_trade % 3600) // 60)
            return {
                "decision": "EXIT_NOW",
                "reason_code": "TRADE_STALE",
                "primary_reason": (
                    f"Intraday trade open for {hours}h {mins}m with only "
                    f"{pnl_pct:+.1f}% progress. Edge has expired."
                ),
                "updated_stop_loss": None,
                "exit_fraction": 1.0,
                "confidence": 85,
            }

        # Check no progress after 2 hours
        if time_in_trade >= cfg["intraday_no_progress_seconds"] and pnl_pct < cfg["intraday_no_progress_min_pct"]:
            triggered.append("no_progress")
            hours = int(time_in_trade // 3600)
            mins = int((time_in_trade % 3600) // 60)
            return {
                "decision": "PARTIAL_EXIT",
                "reason_code": "NO_PROGRESS",
                "primary_reason": (
                    f"Trade open for {hours}h {mins}m with minimal progress "
                    f"({pnl_pct:+.1f}%). Reducing exposure."
                ),
                "updated_stop_loss": None,
                "exit_fraction": 0.5,
                "confidence": 75,
            }

    elif trade_mode == "DELIVERY":
        days_in_trade = time_in_trade / 86400.0
        
        if days_in_trade >= cfg["delivery_stale_days"] and pnl_pct < cfg["delivery_no_progress_min_pct"]:
            triggered.append("delivery_trade_stale")
            return {
                "decision": "PARTIAL_EXIT",
                "reason_code": "DELIVERY_TRADE_STALE",
                "primary_reason": (
                    f"Delivery trade open for {days_in_trade:.1f} days with only "
                    f"{pnl_pct:+.1f}% progress. Dead capital reduction."
                ),
                "updated_stop_loss": None,
                "exit_fraction": 0.5,
                "confidence": 80,
            }

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY 5: VOLUME SPIKE AGAINST POSITION
# ═══════════════════════════════════════════════════════════════════════════════

def _check_volume_spike(features: dict, cfg: dict, triggered: list) -> Optional[dict]:
    """Detect abnormal volume spikes working against the position."""

    volume_spike_against = features.get("volume_spike_against", False)
    relative_volume = features.get("relative_volume", 0)
    strong_reversal = features.get("strong_reversal_candle", False)
    dist_to_target = features.get("distance_to_target", 999)

    if not volume_spike_against:
        return None

    # Volume spike near target might be exhaustion/take-profit
    if relative_volume >= cfg["volume_spike_threshold"] and dist_to_target < 1.0:
        triggered.append("exhaustion_spike")
        return {
            "decision": "PARTIAL_EXIT",
            "reason_code": "EXHAUSTION_SPIKE",
            "primary_reason": (
                f"High volume rejection ({relative_volume:.1f}x) near target. "
                "Securing partial profits before reversal."
            ),
            "updated_stop_loss": None,
            "exit_fraction": 0.5,
            "confidence": 85,
        }

    # Volume spike + reversal candle = panic move
    if relative_volume >= cfg["volume_spike_threshold"] and strong_reversal:
        triggered.append("panic_move")
        return {
            "decision": "EXIT_NOW",
            "reason_code": "PANIC_MOVE",
            "primary_reason": (
                f"Volume spike ({relative_volume:.1f}x average) with strong "
                f"reversal candle against position. Exiting before further damage."
            ),
            "updated_stop_loss": None,
            "exit_fraction": 1.0,
            "confidence": 90,
        }

    # Volume spike without reversal = partial exit
    if relative_volume >= cfg["volume_spike_threshold"]:
        triggered.append("volume_spike_against_position")
        return {
            "decision": "PARTIAL_EXIT",
            "reason_code": "VOLUME_SPIKE_AGAINST_POSITION",
            "primary_reason": (
                f"Unusual volume ({relative_volume:.1f}x average) moving against "
                f"position. Reducing exposure as precaution."
            ),
            "updated_stop_loss": None,
            "exit_fraction": 0.5,
            "confidence": 78,
        }

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY 6: TREND REVERSAL DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _check_trend_reversal(features: dict, cfg: dict, triggered: list) -> Optional[dict]:
    """Detect simple structure-based trend reversals."""

    structure_state = features.get("structure_state", "unknown")
    strong_reversal = features.get("strong_reversal_candle", False)
    ltp = features.get("ltp", 0)
    stop_loss = features.get("stop_loss", 0)
    is_long = features.get("is_long", True)
    distance_to_sl = features.get("distance_to_sl", 999)
    mfe_pct = features.get("mfe_pct", 0)

    if structure_state != "reversing":
        return None

    # High MFE followed by structure breakdown -> secure remaining profit
    if mfe_pct > 2.0 and strong_reversal:
        triggered.append("profit_surrender")
        return {
            "decision": "PARTIAL_EXIT",
            "reason_code": "PROFIT_SURRENDER",
            "primary_reason": (
                "Trade had strong favorable excursion but structure is now "
                "reversing aggressively. Securing profits."
            ),
            "updated_stop_loss": None,
            "exit_fraction": 0.5,
            "confidence": 85,
        }

    # Structure reversing + reversal candle + close to SL = EXIT_NOW
    if strong_reversal and distance_to_sl < 1.0:
        triggered.append("structure_reversal_critical")
        return {
            "decision": "EXIT_NOW",
            "reason_code": "STRUCTURE_REVERSAL_CRITICAL",
            "primary_reason": (
                "Price structure is reversing with strong reversal candle "
                "and stop-loss is very close. Exiting to prevent SL hit."
            ),
            "updated_stop_loss": None,
            "exit_fraction": 1.0,
            "confidence": 88,
        }

    # Structure reversing alone = TIGHTEN
    triggered.append("structure_weakening")
    # Tighten SL closer to current price
    new_sl = None
    if ltp > 0 and stop_loss > 0:
        if is_long:
            proposed = round(ltp * 0.99, 2)  # 1% below LTP
            if _is_better_sl(proposed, stop_loss, is_long):
                new_sl = proposed
        else:
            proposed = round(ltp * 1.01, 2)  # 1% above LTP
            if _is_better_sl(proposed, stop_loss, is_long):
                new_sl = proposed

    return {
        "decision": "TIGHTEN_STOPLOSS",
        "reason_code": "STRUCTURE_WEAKENING",
        "primary_reason": (
            "Price structure showing early reversal signs (lower highs). "
            "Tightening stop-loss as a precaution."
        ),
        "updated_stop_loss": new_sl,
        "exit_fraction": 0.0,
        "confidence": 72,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _build_output(result: dict, features: dict, triggered_rules: list) -> dict:
    """Build the final standardized risk monitor output."""
    return {
        "decision": result["decision"],
        "reason_code": result["reason_code"],
        "primary_reason": result["primary_reason"],
        "updated_stop_loss": result.get("updated_stop_loss"),
        "exit_fraction": result.get("exit_fraction", 0.0),
        "confidence": result.get("confidence", 50),
        "triggered_rules": triggered_rules,
        "pnl_percent": features.get("pnl_percent", 0),
        "pnl_rupees_total": features.get("pnl_rupees_total", 0),
        "time_in_trade_seconds": features.get("time_in_trade_seconds", 0),
        # Snapshot for logging/debugging
        "_features_snapshot": {
            "symbol": features.get("symbol"),
            "quantity": features.get("quantity"),
            "trade_mode": features.get("trade_mode"),
            "direction": features.get("direction"),
            "ltp": features.get("ltp"),
            "entry_price": features.get("entry_price"),
            "stop_loss": features.get("stop_loss"),
            "target_price": features.get("target_price"),
            "mfe_pct": features.get("mfe_pct"),
            "mae_pct": features.get("mae_pct"),
            "distance_to_sl": features.get("distance_to_sl"),
            "relative_volume": features.get("relative_volume"),
            "structure_state": features.get("structure_state"),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _pct_diff(price1: float, price2: float) -> float:
    """Calculate absolute percentage difference between two prices."""
    if price2 == 0:
        return 0.0
    return abs(price1 - price2) / price2 * 100.0

def _is_better_sl(proposed: float, current: float, is_long: bool) -> bool:
    """Check if proposed SL is strictly better (tighter) than current SL."""
    if current <= 0:
        return True
    if is_long:
        return proposed > current
    else:
        return proposed < current


def _merge_config(config: Optional[dict]) -> dict:
    """Merge user config overrides with defaults."""
    defaults = {
        "max_loss_percent": MAX_LOSS_PERCENT,
        "max_loss_rupees_total": MAX_LOSS_RUPEES_TOTAL,
        "breakeven_trigger_pct": BREAKEVEN_TRIGGER_PCT,
        "profit_lock_tier1_pct": PROFIT_LOCK_TIER1_PCT,
        "profit_lock_tier2_pct": PROFIT_LOCK_TIER2_PCT,
        "trail_step_pct": TRAIL_STEP_PCT,
        "trail_buffer_pct": TRAIL_BUFFER_PCT,
        "intraday_stale_seconds": INTRADAY_STALE_SECONDS,
        "intraday_close_exit_hhmm": INTRADAY_CLOSE_EXIT_HHMM,
        "intraday_no_progress_seconds": INTRADAY_NO_PROGRESS_SECONDS,
        "intraday_no_progress_min_pct": INTRADAY_NO_PROGRESS_MIN_PCT,
        "delivery_stale_days": DELIVERY_STALE_DAYS,
        "delivery_no_progress_min_pct": DELIVERY_NO_PROGRESS_MIN_PCT,
        "volume_spike_threshold": VOLUME_SPIKE_THRESHOLD,
    }
    if config:
        defaults.update(config)
    return defaults
