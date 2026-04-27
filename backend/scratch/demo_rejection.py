import sys
import io

sys.path.append("d:/ATS/backend")
from agent.risk.risk_monitor import _log_decision
from agent.execution.risk_agent_validator import validate_agent_output

def demo_rejected_decision():
    print("Simulating a scenario where the AI Agent tries to make an invalid move...\n")
    
    # 1. The market features (current state of trade)
    features = {
        "symbol": "UNIMECH",
        "is_long": True,
        "entry_price": 1015.40,
        "ltp": 1020.00,
        "stop_loss": 998.00,
        "pnl_percent": 0.45,
        "pnl_rupees_total": 69,
        "mfe_pct": 0.5,
        "mae_pct": -0.2,
        "time_in_trade_seconds": 600, # 10 mins
        "quantity": 15,
        "direction": "BUY"
    }
    
    # 2. What the LLM "Agent" decided (A bad decision)
    # E.g. The agent tries to widen the stop loss (which is illegal) and has low confidence.
    raw_agent_decision = {
        "decision": "TIGHTEN_STOPLOSS",
        "reason_code": "VOLATILITY_ADJUSTMENT",
        "confidence": 30, # Low confidence
        "primary_reason": "I think the market is volatile, so I am moving the stop loss down to give it room.",
        "updated_stop_loss": 950.00, # WIDENING the SL (Illegal for a long trade, current SL is 998.00)
        "thesis_status": "weakening",
        "urgency": "low",
        "triggered_factors": ["volatility_spike"],
        "_source": "gemini_agent4"
    }
    
    # 3. Pass it through the validator (Hard Rules)
    validated_result = validate_agent_output(
        raw_output=raw_agent_decision,
        features=features,
        apply_hard_overrides=True
    )
    
    # 4. Print the log exactly as the Risk Monitor would
    _log_decision(
        trade_id="pt-test-123",
        symbol="UNIMECH",
        features=features,
        result=validated_result,
        old_sl=features["stop_loss"],
        decision_source="agent"
    )

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    demo_rejected_decision()
