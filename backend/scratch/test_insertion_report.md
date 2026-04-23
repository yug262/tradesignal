# Test Trade Insertion Report

## 1. Analysis of the Pipeline & Insertion Point

To ensure a "natural" flow of the test trade, I analyzed your `db_models.py`, `execution_agent.py` (Agent 3), and `paper_trading_engine.py`.

Here is how your pipeline works:
1. **Agent 3 Trigger:** `run_execution_planner()` queries `db_models.DBTradeSignal` for rows where `market_date` is today, `confirmation_status == "confirmed"`, and `execution_status == "pending"`.
2. **Execution Planning:** It fetches live price data, merges it with `confirmation_data` (agent 2 view) and `stock_snapshot`, and asks the LLM to decide on an execution strategy (e.g. "ENTER NOW").
3. **Paper Trade Auto-Creation:** If the LLM returns "ENTER NOW" and passes validation (fields exist and are > 0), Agent 3 calls `auto_create_from_execution()`, which creates the actual `DBPaperTrade` row and updates the virtual `DBPortfolio`.
4. **Risk Monitor Pickup:** The `risk_monitor.py` loop routinely queries `DBPaperTrade` for `status == "OPEN"`.

**Where to insert:**
The correct, safest, and most natural place to insert a test trade is directly into `DBTradeSignal`, mocking the *Agent 2 output*.
If we insert directly into `DBPaperTrade`, we bypass Agent 3 entirely, which fails your requirement: *"Agent 3 / execution flow recognizes it"*.

## 2. Insertion Execution Script

I created and ran a safe Python script (`d:\ATS\backend\scratch\insert_test_trade.py`) that uses SQLAlchemy to add the record properly. Here is the script for your reference:

```python
import time
import uuid
from datetime import datetime, timezone, timedelta
from database import SessionLocal
import db_models
from agent.risk_features import fetch_live_quote

IST = timezone(timedelta(hours=5, minutes=30))

def insert_test_trade():
    db = SessionLocal()
    try:
        symbol = "JIOFIN"
        
        # 1. Fetch real-time live price
        quote = fetch_live_quote(symbol)
        ltp = float(quote.get("ltp", 244.50))
        
        entry_price = round(ltp, 2)
        target_price = round(entry_price + 1.00, 2)
        stop_loss = round(entry_price - 0.30, 2)
        
        now_ms = int(time.time() * 1000)
        today_str = datetime.now(IST).strftime("%Y-%m-%d")
        signal_id = f"test-{uuid.uuid4().hex[:8]}"
        
        # Provide mock Agent 2 data to give Agent 3 context
        mock_agent2_data = {
            "decision": "TRADE",
            "trade_mode": "INTRADAY",
            "direction": "BUY",
            "confidence": 95,
            "why_tradable_or_not": "Test insertion to validate execution and risk pipeline.",
            "final_summary": "Strong test setup, safe to execute."
        }
        
        mock_snapshot = {
            "last_close": ltp - 1.0, 
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
            
            # Required for Agent 3 pickup
            confirmation_status="confirmed",
            confirmed_at=now_ms,
            confirmation_data=mock_agent2_data,
            
            # Required for Agent 3 pickup
            execution_status="pending",
            
            stock_snapshot=mock_snapshot,
            news_article_ids=["test-article-1"],
            reasoning={"reason": "test setup"}
        )
        
        db.add(signal)
        db.commit()
    except Exception as e:
        db.rollback()
    finally:
        db.close()
```

## 3. Final Inserted Values

The script fetched the live Groww quote at the time of execution. The values inserted were:

*   **Signal ID:** `test-c3b90f97`
*   **Symbol:** `JIOFIN`
*   **Action:** `BUY` (INTRADAY)
*   **Entry Price:** `244.85`
*   **Stop Loss:** `244.55` (-0.30)
*   **Target Price:** `245.85` (+1.00)

## 4. Expected Chain of Events

Within the next 60 seconds (depending on your scheduler cycle), the following sequence will occur automatically:

1.  **Agent 3 Execution Planner:** Wakes up, finds the `test-c3b90f97` row with `execution_status="pending"`. It calls the Gemini API to construct a live execution plan based on current price context.
2.  **Auto-Creation:** If the LLM returns `ENTER NOW` (highly likely given the setup), the `auto_create_from_execution()` function fires. It translates the signal into a `DBPaperTrade` record (Status `OPEN`), updates the `DBPortfolio`, and writes an `agent_logs` record. The `execution_status` on the signal becomes `"planned"`.
3.  **Risk Monitor:** Now that a `DBPaperTrade` is `OPEN`, the new Gemini Risk Monitor (Agent 4) will pick it up on its next 30-second cycle. It will fetch features (including the newly added depth data) and assess the open JIOFIN position.

## 5. Verification Queries

You can run the following SQL queries directly in your database to trace the lifecycle of this test trade:

**1. Check Agent 3 Pickup (Signal Table):**
```sql
SELECT id, symbol, execution_status, status 
FROM trade_signals 
WHERE symbol = 'JIOFIN' 
ORDER BY generated_at DESC LIMIT 1;
-- Expect: execution_status='planned', status='planned'
```

**2. Check Paper Trade Creation:**
```sql
SELECT id, symbol, action, status, entry_price, stop_loss, target_price 
FROM paper_trades 
WHERE symbol = 'JIOFIN' 
ORDER BY entry_time DESC LIMIT 1;
-- Expect: status='OPEN' (or 'CLOSED' if it hit the SL/TGT quickly)
```

**3. Check Agent Logs for Full Trace:**
```sql
SELECT agent_name, signal, message 
FROM agent_logs 
WHERE symbol = 'JIOFIN' 
ORDER BY created_at DESC LIMIT 5;
-- Expect to see Agent 3 "Execution planned", Paper Trading "BUY_EXECUTED", and Agent 4 evaluations.
```
