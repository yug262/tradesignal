"""Integration test for all 5 gap fixes."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from agent.risk_agent_validator import validate_agent_output, _get_source_label
from agent.risk_monitor import (
    _record_decision, _get_previous_state, _check_flip_flop, _decision_memory
)
from agent.gemini_risk_monitor import _build_agent_input_payload

# ═══════════════════════════════════════════════════════════════════════════════
# TEST SUITE
# ═══════════════════════════════════════════════════════════════════════════════

features = {
    "symbol": "RELIANCE", "is_long": True, "stop_loss": 2400, "ltp": 2500,
    "pnl_percent": 2.0, "pnl_rupees_total": 200, "time_in_trade_seconds": 3600,
    "trade_mode": "INTRADAY", "entry_price": 2450, "target_price": 2600,
    "mfe_pct": 3.0, "mae_pct": -0.5, "distance_to_sl": 4.0,
    "distance_to_target": 4.0, "distance_from_entry": 2.0,
    "relative_volume": 1.2, "structure_state": "healthy",
    "quantity": 10, "direction": "BUY",
    # NEW: depth features
    "depth_pressure": "moderate_buy_pressure",
    "depth_imbalance": 2.1,
    "depth_absorption_buy": True,
    "depth_absorption_sell": False,
    "depth_against_position": False,
}

# ─── GAP 1: Depth data in payload ────────────────────────────────────────────
print("=== GAP 1: Depth Data ===")
payload = _build_agent_input_payload(features, {})
assert "depth_pressure" in payload
assert payload["depth_pressure"] == "moderate_buy_pressure"
assert payload["depth_absorption_buy"] == True
assert payload["depth_against_position"] == False
print(f"  PASS: Depth fields present: pressure={payload['depth_pressure']}, "
      f"absorption_buy={payload['depth_absorption_buy']}, "
      f"against={payload['depth_against_position']}")

# ─── GAP 2: Decision memory + flip-flop ─────────────────────────────────────
print("\n=== GAP 2: Decision Memory & Flip-Flop ===")

# Clear memory
_decision_memory.clear()

# First decision: HOLD
result1 = {"decision": "HOLD", "confidence": 70, "_features_snapshot": {}, "risk_flags": []}
_record_decision("trade-001", result1)
prev = _get_previous_state("trade-001")
assert prev is not None
assert prev["decision"] == "HOLD"
print(f"  PASS: Decision memory stores HOLD")

# Second decision: EXIT_NOW (rapid flip)
result2 = {"decision": "EXIT_NOW", "confidence": 80, "_features_snapshot": {}, "risk_flags": []}
flags = _check_flip_flop("trade-001", result2)
assert len(flags) > 0
assert any("flip_flop" in f for f in flags)
print(f"  PASS: Flip-flop detected: {flags}")

# Record it and check reversal count
_record_decision("trade-001", result2)
entry = _decision_memory["trade-001"]
assert entry["reversals"] == 1
print(f"  PASS: Reversal count = {entry['reversals']}")

# No previous state for unknown trade
assert _get_previous_state("trade-unknown") is None
print(f"  PASS: Unknown trade returns None")

# ─── GAP 3: Change detection (delta payload) ────────────────────────────────
print("\n=== GAP 3: Change Detection ===")

prev_state = {
    "decision": "HOLD",
    "pnl_percent": 1.0,
    "_features_snapshot": {
        "ltp": 2480,
        "pnl_percent": 1.0,
        "structure_state": "neutral",
        "distance_to_sl": 3.5,
    },
}
payload_with_delta = _build_agent_input_payload(features, {}, previous_state=prev_state)
assert "changes_since_last_check" in payload_with_delta
delta = payload_with_delta["changes_since_last_check"]
assert "pnl_change_since_last" in delta
assert "ltp_change_pct" in delta
assert "structure_changed" in delta
assert "previous_decision" in delta
assert delta["previous_decision"] == "HOLD"
print(f"  PASS: Delta payload present:")
print(f"    pnl_change: {delta.get('pnl_change_since_last')}")
print(f"    ltp_change: {delta.get('ltp_change_pct')}%")
print(f"    structure:  {delta.get('structure_changed')}")
print(f"    prev_dec:   {delta.get('previous_decision')}")

# Without previous state, no delta
payload_no_delta = _build_agent_input_payload(features, {}, previous_state=None)
assert "changes_since_last_check" not in payload_no_delta
print(f"  PASS: No delta when previous_state is None")

# ─── GAP 4: Confidence weighting ────────────────────────────────────────────
print("\n=== GAP 4: Confidence Gating ===")

# Low-confidence EXIT_NOW should be downgraded (trade not in deep loss)
low_conf_exit = {
    "decision": "EXIT_NOW", "reason_code": "NERVOUS",
    "primary_reason": "Seems bad", "updated_stop_loss": None,
    "exit_fraction": 1.0, "confidence": 25, "thesis_status": "weakening",
    "urgency": "high", "triggered_factors": [], "risk_flags": [],
    "monitoring_note": "", "_source": "gemini_agent4",
}
result = validate_agent_output(low_conf_exit, features)
assert result["decision"] == "PARTIAL_EXIT", f"Expected PARTIAL_EXIT, got {result['decision']}"
assert "low_confidence_downgrade" in result["risk_flags"]
print(f"  PASS: EXIT_NOW conf=25 downgraded to {result['decision']}")

# Low-confidence PARTIAL_EXIT should be downgraded to HOLD
low_conf_partial = {
    "decision": "PARTIAL_EXIT", "reason_code": "UNCERTAIN",
    "primary_reason": "Maybe reduce", "updated_stop_loss": None,
    "exit_fraction": 0.5, "confidence": 20, "thesis_status": "weakening",
    "urgency": "medium", "triggered_factors": [], "risk_flags": [],
    "monitoring_note": "", "_source": "gemini_agent4",
}
result2 = validate_agent_output(low_conf_partial, features)
assert result2["decision"] == "HOLD"
assert result2["exit_fraction"] == 0.0
print(f"  PASS: PARTIAL_EXIT conf=20 downgraded to {result2['decision']}")

# High-confidence EXIT_NOW should pass through
high_conf_exit = dict(low_conf_exit)
high_conf_exit["confidence"] = 85
result3 = validate_agent_output(high_conf_exit, features)
assert result3["decision"] == "EXIT_NOW"
print(f"  PASS: EXIT_NOW conf=85 passes through as {result3['decision']}")

# Deep loss should NOT be gated (safety override takes priority)
deep_loss_features = dict(features)
deep_loss_features["pnl_percent"] = -4.0  # Significant loss
low_conf_exit_deep = dict(low_conf_exit)
low_conf_exit_deep["confidence"] = 25
result4 = validate_agent_output(low_conf_exit_deep, deep_loss_features)
# Should stay EXIT_NOW because -4% is in significant loss territory
assert result4["decision"] == "EXIT_NOW"
print(f"  PASS: Deep loss (-4%) bypasses confidence gate: {result4['decision']}")

# ─── GAP 5: Source labeling ──────────────────────────────────────────────────
print("\n=== GAP 5: Source Labeling ===")

# Test source labels
assert _get_source_label("gemini_agent4") == "AI Agent (Gemini)"
assert _get_source_label("rule_engine_fallback") == "Rule Engine (Fallback)"
assert _get_source_label("agent4_fallback") == "Safe Default (Agent Unavailable)"
assert _get_source_label("data_error") == "Safe Default (Data Unavailable)"
print(f"  PASS: All source labels correct")

# Test that validated output includes source label
agent_output = {
    "decision": "HOLD", "reason_code": "OK",
    "primary_reason": "Fine", "updated_stop_loss": None,
    "exit_fraction": 0.0, "confidence": 70, "thesis_status": "intact",
    "urgency": "low", "triggered_factors": [], "risk_flags": [],
    "monitoring_note": "", "_source": "gemini_agent4",
}
result5 = validate_agent_output(agent_output, features)
assert "_decision_source_label" in result5
assert result5["_decision_source_label"] == "AI Agent (Gemini)"
assert result5["_decision_source"] == "gemini_agent4"
print(f"  PASS: Validated output has source label: {result5['_decision_source_label']}")

# Test fallback source label
fallback_output = dict(agent_output)
fallback_output["_source"] = "rule_engine_fallback"
result6 = validate_agent_output(fallback_output, features)
assert result6["_decision_source_label"] == "Rule Engine (Fallback)"
print(f"  PASS: Fallback source label: {result6['_decision_source_label']}")

print("\n" + "=" * 50)
print(" ALL GAP TESTS PASSED (5/5)")
print("=" * 50)
