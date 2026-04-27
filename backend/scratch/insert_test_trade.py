"""Script to safely insert a test trade into the Agent 3 execution pipeline."""
import sys
import uuid
import time
from datetime import datetime, timezone, timedelta

# Import the database models and session manager
sys.path.append("d:/ATS/backend")
from database import SessionLocal
import db_models
from agent.risk.risk_features import fetch_live_quote

IST = timezone(timedelta(hours=5, minutes=30))

def insert_test_trade():
    """Insert a controlled test signal to trigger Agent 3 and the Risk Monitor."""
    db = SessionLocal()
    try:
        symbol = "JIOFIN"
        
        # 1. Fetch real-time live price
        print(f"Fetching live data for {symbol}...")
        quote = fetch_live_quote(symbol)
        ltp = float(quote.get("ltp", 244.50))
        
        entry_price = round(ltp, 2)
        target_price = round(entry_price + 1.00, 2)
        stop_loss = round(entry_price - 0.30, 2)
        
        print(f"Live Price: {ltp:.2f}")
        print(f"Targeting: Entry={entry_price:.2f}, SL={stop_loss:.2f}, TGT={target_price:.2f}")

        # 2. Setup the required DB conditions for Agent 3
        # Agent 3 query requires:
        # market_date == today
        # confirmation_status == "confirmed"
        # execution_status == "pending"
        
        now_ms = int(time.time() * 1000)
        today_str = datetime.now(IST).strftime("%Y-%m-%d")
        signal_id = f"test-{uuid.uuid4().hex[:8]}"
        
        # We must provide mock confirmation_data so Agent 3 has 'agent2_view' context
        mock_agent2_data = {
            "decision": "TRADE",
            "trade_mode": "INTRADAY",
            "direction": "BUY",
            "confidence": 95,
            "why_tradable_or_not": "Test insertion to validate execution and risk pipeline.",
            "final_summary": "Strong test setup, safe to execute."
        }
        
        # We provide a mock stock_snapshot so Agent 3 doesn't fail calculating metrics
        mock_snapshot = {
            "last_close": ltp - 1.0,  # simulate slightly up day
            "avg_volume_20d": 10_000_000
        }

        # 3. Create the DBTradeSignal row
        signal = db_models.DBTradeSignal(
            id=signal_id,
            symbol=symbol,
            signal_type="BUY",
            trade_mode="INTRADAY",
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            confidence=95.0,
            generated_at=now_ms,
            market_date=today_str,
            status="confirmed",
            
            # Phase 2 status (Required for Agent 3 pickup)
            confirmation_status="confirmed",
            confirmed_at=now_ms,
            confirmation_data=mock_agent2_data,
            
            # Phase 3 status
            execution_status="pending",
            
            stock_snapshot=mock_snapshot,
            news_article_ids=["test-article-1"],
            reasoning={"reason": "test setup"}
        )
        
        db.add(signal)
        db.commit()
        
        print(f"SUCCESS: Successfully inserted Trade Signal: {signal_id}")
        print("Agent 3 should pick this up automatically within the next 30-60 seconds.")
        
    except Exception as e:
        db.rollback()
        print(f"FAILED: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    insert_test_trade()
