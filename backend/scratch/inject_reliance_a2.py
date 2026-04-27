import json
import sys
import os

# Add parent dir to path so we can import from database and db_models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from db_models import DBTradeSignal

# The JSON provided by the user
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

data = {
  "stock": {
    "symbol": "RELIANCE",
    "company_name": "Reliance Industries Ltd",
    "exchange": "NSE"
  },
  "market_behavior": {
    "gap_direction": "UP",
    "gap_strength": "MODERATE",
    "price_behavior": "HOLDING_STRENGTH",
    "position_in_range": "NEAR_HIGH",
    "volume_confirmation": "STRONG"
  },
  "technical_validation": {
    "support_respected": True,
    "resistance_respected": True,
    "near_resistance_risk": "LOW",
    "near_support_risk": "LOW",
    "level_comment": "Price is holding above support and not pressing into strong resistance."
  },
  "thesis_check": {
    "agent_1_bias": "BULLISH",
    "expected_behavior": [
      "Price should gap up after open",
      "Price should hold above previous close",
      "Volume should support the move"
    ],
    "actual_behavior_summary": "Price opened higher, stayed near day high, and volume participation is strong.",
    "alignment": "ALIGNED"
  },
  "validation": {
    "status": "CONFIRMED",
    "confidence_in_validation": "HIGH",
    "reason": "Agent 1 bullish thesis is respected by opening behavior, price strength, and volume.",
    "what_failed": [],
    "what_worked": [
      "Gap direction matched thesis",
      "Price held near day high",
      "Volume confirmation was strong",
      "Support remained intact"
    ],
    "early_signal_quality": "STRONG"
  },
  "trade_suitability": {
    "mode": "INTRADAY",
    "reason": "Strong early move with volume support is more suitable for intraday execution.",
    "holding_logic": "SHORT_INTRADAY_MOVE"
  },
  "timeframe_plan": {
    "primary_timeframe": "1m",
    "secondary_timeframe": None,
    "data_window_minutes": 5,
    "use_previous_data_for_secondary": False,
    "reason": "At 9:20 only current-day 1m candles have enough usable data."
  },
  "indicators_to_check": {
    "trend": ["EMA", "MACD", "PARABOLIC_SAR"],
    "momentum": ["RSI", "STOCHASTIC", "MFI"],
    "volatility": ["ATR", "BOLLINGER_BANDS"],
    "volume": ["VWAP", "OBV", "CMF"],
    "pattern_recognition": ["CANDLESTICK_PATTERNS"],
    "support_resistance": ["PIVOT_POINTS", "DYNAMIC_SUPPORT_RESISTANCE"]
  },
  "decision": {
    "should_pass_to_agent_3": True,
    "pass_reason": "Confirmed thesis with aligned price action, strong early signal quality, and intraday suitability.",
    "agent_3_instruction": "PROCEED"
  }
}

def inject():
    db = SessionLocal()
    try:
        # Find the most recent signal for RELIANCE
        signal = db.query(DBTradeSignal).filter(DBTradeSignal.symbol == "RELIANCE").order_by(DBTradeSignal.generated_at.desc()).first()
        
        if not signal:
            print("No signal found for RELIANCE. Creating a new mock signal...")
            import uuid
            import time
            from datetime import datetime
            
            signal = DBTradeSignal(
                id=f"sig-RELIANCE-mock-{uuid.uuid4().hex[:8]}",
                symbol="RELIANCE",
                signal_type="WATCH",
                confidence=80,
                trade_mode="INTRADAY",
                market_date=datetime.now().strftime("%Y-%m-%d"),
                generated_at=int(time.time() * 1000),
                confirmation_status="pending",
                execution_status="pending",
                risk_monitor_status="pending",
                status="pending",
                reasoning={"combined_view": {"final_bias": "BULLISH", "final_confidence": "HIGH"}},
                stock_snapshot={"last_close": 2900}
            )
            db.add(signal)
            db.commit()
            print(f"Created mock signal {signal.id}")
        print(f"Found signal {signal.id} for RELIANCE generated at {signal.generated_at}")
        
        # Update it
        signal.confirmation_status = "confirmed"
        signal.confirmation_data = data
        signal.status = "confirmed"
        signal.execution_status = "pending"
        signal.execution_data = None
        
        db.commit()
        print("\n--- Triggering Agent 2.5 (Technical Analysis) ---")
        
        # We will mock analyze_technicals directly to guarantee a "GO" result 
        # so you can see Agent 3 trigger in action.
        import agent.technical_analysis_agent
        
        # Keep candles and indicators mocked so it doesn't fail before analysis
        original_build = agent.technical_analysis_agent._build_candle_data
        original_fetch = agent.technical_analysis_agent.fetch_indicator_data
        original_analyze = agent.technical_analysis_agent.analyze_technicals
        
        def mock_build_candle_data(symbol, plan):
            import time
            return [{"timestamp": int(time.time()*1000) - i*60000, "close": 2900} for i in range(5)]
            
        def mock_fetch_indicator_data(*args, **kwargs):
            return []
            
        def mock_analyze_technicals(*args, **kwargs):
            return {
                "_source": "mocked_for_test",
                "technical_analysis": {
                    "overall": {
                        "technical_bias": "BULLISH",
                        "confidence": "HIGH",
                        "technical_grade": "A",
                        "trade_readiness": "READY",
                        "reasoning": {
                            "why_this_bias": "Strong volume breakout above VWAP and EMA crossovers.",
                            "why_this_grade": "A grade because momentum is aligned with Agent 2 thesis.",
                            "key_evidence": [
                                "RSI indicates strong momentum at 68",
                                "Price broke through 2900 resistance level",
                                "OBV confirms the upward price action"
                            ]
                        }
                    },
                    "trend_analysis": {
                        "short_term": "UP",
                        "momentum": "BULLISH",
                        "strength": "STRONG"
                    },
                    "support_resistance_context": {
                        "nearest_support": "2880",
                        "nearest_resistance": "2950",
                        "risk_of_rejection": "LOW"
                    },
                    "agent_3_handoff": {
                        "technical_go_no_go": "GO",
                        "go_no_go_reason": "Perfect mocked breakout for testing Agent 3 trigger.",
                        "must_confirm_before_entry": [
                            "Ensure spread is within 0.1%",
                            "Check for sudden volatility spikes"
                        ]
                    }
                }
            }
            
        agent.technical_analysis_agent._build_candle_data = mock_build_candle_data
        agent.technical_analysis_agent.fetch_indicator_data = mock_fetch_indicator_data
        agent.technical_analysis_agent.analyze_technicals = mock_analyze_technicals
        
        # --- MOCK AGENT 3 (Execution) ---
        # Mock Agent 3 so it ignores the closed market and generates a paper trade
        import agent.execution_agent
        original_plan_execution = agent.execution_agent.plan_execution
        
        def mock_plan_execution(*args, **kwargs):
            return {
                "action": "ENTER_NOW",
                "execution_decision": "ENTER NOW",
                "confidence": 95,
                "trade_mode": "INTRADAY",
                "why_now_or_why_wait": "Perfect mocked breakout for testing Agent 3 trigger.",
                "final_summary": "Execution accepted.",
                "entry_plan": {
                    "entry_price": 2905,
                    "entry_type": "MKT",
                    "condition": "Price is holding strong"
                },
                "stop_loss": {
                    "price": 2880,
                    "reason": "Below support"
                },
                "target": {
                    "price": 2955,
                    "reason": "Previous high"
                },
                "risk_reward": 2.0,
                "position_sizing": {
                    "position_size_shares": 100,
                    "position_size_inr": 290500,
                    "max_loss_at_sl": 2500,
                    "capital_used_pct": 10.0,
                    "sizing_note": "Mocked trade"
                },
                "_source": "mocked_for_test",
                "_v2_execution_decision": {
                    "action": "ENTER_NOW",
                    "direction": "LONG",
                    "trade_mode": "INTRADAY",
                    "confidence": "HIGH",
                    "reason": "Mocked execution for end-to-end testing."
                },
                "trade_plan": {
                    "entry_price": 2905,
                    "stop_loss": 2880,
                    "target_price": 2955,
                    "risk_reward": 2.0
                },
                "order_payload": {
                    "transaction_type": "BUY"
                }
            }
            
        agent.execution_agent.plan_execution = mock_plan_execution
        
        try:
            from agent.technical_analysis.technical_analysis_agent import run_technical_analysis
            run_technical_analysis(db=db, signal_ids=[signal.id])
        finally:
            agent.technical_analysis_agent._build_candle_data = original_build
            agent.technical_analysis_agent.fetch_indicator_data = original_fetch
            agent.technical_analysis_agent.analyze_technicals = original_analyze
            agent.execution_agent.plan_execution = original_plan_execution
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    inject()
