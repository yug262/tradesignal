"""Quick integration test for the risk agent validator."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from agent.execution.risk_agent_validator import validate_agent_output

# Test 1: Valid agent output passes cleanly
features = {
    "symbol": "RELIANCE", "is_long": True, "stop_loss": 2400, "ltp": 2500,
    "pnl_percent": 2.0, "pnl_rupees_total": 200, "time_in_trade_seconds": 3600,
    "trade_mode": "INTRADAY", "entry_price": 2450, "target_price": 2600,
    "mfe_pct": 3.0, "mae_pct": -0.5, "distance_to_sl": 4.0,
    "relative_volume": 1.2, "structure_state": "healthy",
    "quantity": 10, "direction": "BUY",
}
agent_output = {
    "decision": "TIGHTEN_STOPLOSS", "reason_code": "PROFIT_LOCK",
    "primary_reason": "Locking profits", "updated_stop_loss": 2450,
    "exit_fraction": 0.0, "confidence": 85, "thesis_status": "intact",
    "urgency": "medium", "triggered_factors": ["profit_lock"],
    "risk_flags": [], "monitoring_note": "Watch for continuation",
}
result = validate_agent_output(agent_output, features)
assert result["decision"] == "TIGHTEN_STOPLOSS"
assert result["_validation_status"] == "clean"
print(f"Test 1 PASS: {result['decision']} | {result['_validation_status']}")

# Test 2: Invalid SL direction gets rejected (below current SL for long = widening)
bad_output = dict(agent_output)
bad_output["updated_stop_loss"] = 2350  # below current SL 2400 for long = ILLEGAL
result2 = validate_agent_output(bad_output, features)
# Should degrade to HOLD since SL rejected and TIGHTEN without SL => HOLD
assert result2["decision"] == "HOLD"
assert result2["_validation_status"] == "sanitized"
print(f"Test 2 PASS: {result2['decision']} | {result2['_validation_status']} | overrides={result2['_overrides_applied']}")

# Test 3: Catastrophic loss triggers hard override
loss_features = dict(features)
loss_features["pnl_percent"] = -6.0
loss_features["pnl_rupees_total"] = -600
hold_output = {
    "decision": "HOLD", "reason_code": "SEEMS_OK",
    "primary_reason": "Holding", "updated_stop_loss": None,
    "exit_fraction": 0.0, "confidence": 70, "thesis_status": "intact",
    "urgency": "low", "triggered_factors": [], "risk_flags": [],
    "monitoring_note": "",
}
result3 = validate_agent_output(hold_output, loss_features)
assert result3["decision"] == "EXIT_NOW"
assert result3["exit_fraction"] == 1.0
print(f"Test 3 PASS: {result3['decision']} | hard override applied")

# Test 4: Malformed output gets sanitized
garbage = {"decision": "INVALID_THING", "confidence": "not_a_number"}
result4 = validate_agent_output(garbage, features)
assert result4["decision"] == "HOLD"  # invalid decision defaults to HOLD
assert result4["_validation_status"] == "sanitized"
print(f"Test 4 PASS: {result4['decision']} | sanitized {len(result4['_overrides_applied'])} fields")

# Test 5: EXIT_NOW should get exit_fraction=1.0 even if agent says 0
exit_output = {
    "decision": "EXIT_NOW", "reason_code": "THESIS_BROKEN",
    "primary_reason": "Thesis broken", "updated_stop_loss": None,
    "exit_fraction": 0.0, "confidence": 90, "thesis_status": "broken",
    "urgency": "high", "triggered_factors": ["thesis_broken"],
    "risk_flags": [], "monitoring_note": "",
}
result5 = validate_agent_output(exit_output, features)
assert result5["exit_fraction"] == 1.0
print(f"Test 5 PASS: EXIT_NOW exit_fraction correctly forced to 1.0")

# Test 6: PARTIAL_EXIT should have bounded exit_fraction
partial_output = {
    "decision": "PARTIAL_EXIT", "reason_code": "WEAKENING",
    "primary_reason": "Thesis weakening", "updated_stop_loss": None,
    "exit_fraction": 5.0, "confidence": 70, "thesis_status": "weakening",
    "urgency": "medium", "triggered_factors": ["weakening"],
    "risk_flags": [], "monitoring_note": "",
}
result6 = validate_agent_output(partial_output, features)
assert result6["exit_fraction"] == 0.5  # invalid 5.0 clamped to 0.5
print(f"Test 6 PASS: PARTIAL_EXIT exit_fraction correctly clamped to {result6['exit_fraction']}")

# Test 7: SL that crosses LTP gets rejected (long: SL above LTP)
cross_output = dict(agent_output)
cross_output["updated_stop_loss"] = 2600  # above LTP 2500 for long = crosses price
result7 = validate_agent_output(cross_output, features)
assert result7["decision"] == "HOLD"  # degraded
print(f"Test 7 PASS: SL crossing LTP correctly rejected")

# Test 8: Adapter from rule engine output
from agent.risk.risk_monitor import _adapt_rule_engine_output
rule_result = {
    "decision": "TIGHTEN_STOPLOSS", "reason_code": "TRAIL_PERCENTAGE",
    "primary_reason": "Trailing SL", "updated_stop_loss": 2450,
    "exit_fraction": 0.0, "confidence": 90, "triggered_rules": ["trail_percentage"],
}
failed_agent = {"_error": "timeout", "_model": "gemini-2.5-flash", "_latency_ms": 5000}
adapted = _adapt_rule_engine_output(rule_result, failed_agent)
assert adapted["decision"] == "TIGHTEN_STOPLOSS"
assert "trail_percentage" in adapted["triggered_factors"]
assert adapted["_source"] == "rule_engine_fallback"
print(f"Test 8 PASS: Rule engine adapter works correctly")

print("\n=== ALL 8 TESTS PASSED ===")
