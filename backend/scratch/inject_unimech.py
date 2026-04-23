import sys
import uuid
import time
from datetime import datetime, timezone, timedelta

sys.path.append("d:/ATS/backend")
from database import SessionLocal
import db_models
from agent.paper_trading_engine import create_paper_trade

IST = timezone(timedelta(hours=5, minutes=30))

def inject_unimech_test():
    db = SessionLocal()
    try:
        symbol = "UNIMECH"
        entry_price = 1017.4
        target_price = 1010.5
        stop_loss = 1020.0
        quantity = 15
        
        now_ms = int(time.time() * 1000)
        today_str = datetime.now(IST).strftime("%Y-%m-%d")
        signal_id = f"test-{uuid.uuid4().hex[:8]}"

        # This is the exact data structure that the UI reads to display the Agent 3 card
        mock_execution_data = {
            "action": "SELL",
            "execution_decision": "WAIT FOR PULLBACK", # Changed from WAIT FOR PULLBACK so it trades immediately
            "confidence": 65,
            "trade_mode": "INTRADAY",
            "entry_plan": {
                "entry_price": entry_price,
                "type": "MARKET",
                "condition": "Entering at current price as requested to trigger paper trading."
            },
            "target": {
                "price": target_price,
                "reasoning": "Targeting the recent intraday high of 1051.95, with a conservative exit at 1030 to ensure RR compliance."
            },
            "stop_loss": {
                "price": stop_loss,
                "reasoning": "Placed just below the previous close and the 1000 psychological support level to invalidate the gap-up thesis."
            },
            "position_sizing": {
                "position_size_shares": quantity,
                "position_size_inr": 15231,
                "capital_used_pct": 19.83,
                "max_loss_at_sl": 261
            },
            "why_now_or_why_wait": "The stock is currently trading at 1015.4. Entering now as requested to bypass wait and trigger paper trading directly.",
            "invalid_if": "Price drops below 998, filling the gap and negating the bullish momentum."
        }

        # 1. Insert the DBTradeSignal so the UI shows the full card
        signal = db_models.DBTradeSignal(
            id=signal_id,
            symbol=symbol,
            signal_type="SELL",
            trade_mode="INTRADAY",
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            confidence=65.0,
            generated_at=now_ms,
            market_date=today_str,
            status="planned", # Already planned, bypasses Agent 3
            confirmation_status="confirmed",
            execution_status="planned", # Already planned
            execution_data=mock_execution_data,
            news_article_ids=[],
            reasoning={"reason": "Direct injection test"}
        )
        db.add(signal)
        
        # 2. Directly create the paper trade but set it to PENDING so it waits for the price
        print(f"Creating PENDING paper trade for {symbol} (Waiting for price to hit {entry_price})...")
        pt_result = create_paper_trade(
            db=db,
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            quantity=quantity,
            action="SELL",
            trade_mode="INTRADAY",
            confidence_score=65.0,
            risk_level="MEDIUM",
            trade_reason="Direct test injection from UI data",
            signal_id=signal_id,
            risk_reward="1:3.57",
            max_loss_at_sl=261.0,
            status="PENDING"
        )
        
        if pt_result.get("success"):
            print(f"SUCCESS: PENDING Paper trade created! ID: {pt_result['trade_id']}")
        else:
            print(f"FAILED to create paper trade: {pt_result.get('error')}")

        db.commit()
        print(f"SUCCESS: Inserted Trade Signal {signal_id} and PENDING Paper Trade.")
        
    except Exception as e:
        db.rollback()
        print(f"FAILED: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    inject_unimech_test()
