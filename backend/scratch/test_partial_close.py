"""Test partial_close_paper_trade in isolation with a real DB transaction."""
import sys
import io
import time
import uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.append("d:/ATS/backend")

from datetime import datetime, timezone, timedelta
from database import SessionLocal
import db_models
from agent.paper_trading_engine import partial_close_paper_trade, close_paper_trade

IST = timezone(timedelta(hours=5, minutes=30))

def test_partial_close():
    db = SessionLocal()
    try:
        now_ms = int(time.time() * 1000)
        trade_id = f"pt-TEST-PARTIAL-{uuid.uuid4().hex[:6]}"
        
        # Create a test trade directly
        trade = db_models.DBPaperTrade(
            id=trade_id,
            symbol="TESTPARTIAL",
            action="BUY",
            entry_price=100.00,
            exit_price=None,
            quantity=10,
            stop_loss=95.00,
            target_price=110.00,
            current_price=102.00,
            pnl=20.0,
            pnl_percentage=2.0,
            status="OPEN",
            confidence_score=75.0,
            risk_level="MEDIUM",
            trade_reason="Test partial close",
            exit_reason=None,
            signal_id=None,
            trade_mode="INTRADAY",
            risk_reward="1:2",
            position_value=1000.00,
            max_loss_at_sl=50.00,
            entry_time=now_ms - 600_000,  # 10 mins ago
            exit_time=None,
            created_at=now_ms,
            updated_at=now_ms,
        )
        db.add(trade)
        db.commit()
        print(f"Created test trade: {trade_id} (10 shares @ Rs.100)")
        
        # TEST 1: Partial exit 50% at Rs.103
        print("\n--- TEST 1: 50% partial exit at Rs.103 ---")
        result = partial_close_paper_trade(
            db, trade_id, exit_price=103.00, exit_fraction=0.5,
            exit_reason="RISK_MONITOR_PARTIAL_EXIT"
        )
        
        assert result["success"], f"Partial close failed: {result}"
        assert result["shares_sold"] == 5, f"Expected 5 sold, got {result['shares_sold']}"
        assert result["shares_remaining"] == 5, f"Expected 5 remaining, got {result['shares_remaining']}"
        assert result["realized_pnl"] == 15.0, f"Expected PnL 15.0, got {result['realized_pnl']}"
        print(f"  PASS: Sold {result['shares_sold']} shares, realized Rs.{result['realized_pnl']}")
        print(f"  PASS: {result['shares_remaining']} shares still OPEN")
        
        # Verify the trade was updated in DB
        db.refresh(trade)
        assert trade.quantity == 5
        assert trade.status == "OPEN"
        assert trade.position_value == 500.00
        print(f"  PASS: DB shows qty={trade.quantity}, status={trade.status}, pos_val={trade.position_value}")
        
        # TEST 2: Another 50% partial exit (of remaining 5 = sell 2)
        print("\n--- TEST 2: Another 50% partial exit at Rs.105 ---")
        result2 = partial_close_paper_trade(
            db, trade_id, exit_price=105.00, exit_fraction=0.5,
            exit_reason="RISK_MONITOR_PARTIAL_EXIT"
        )
        assert result2["success"]
        assert result2["shares_sold"] == 2  # floor(5 * 0.5) = 2
        assert result2["shares_remaining"] == 3
        print(f"  PASS: Sold {result2['shares_sold']} shares, realized Rs.{result2['realized_pnl']}")
        print(f"  PASS: {result2['shares_remaining']} shares still OPEN")
        
        # TEST 3: Full close the remaining position
        print("\n--- TEST 3: Full close remaining 3 shares at Rs.108 ---")
        result3 = close_paper_trade(db, trade_id, exit_price=108.00, exit_reason="TARGET_HIT")
        assert result3["success"]
        assert result3["pnl"] == 24.0  # (108 - 100) * 3 = 24
        print(f"  PASS: Closed remaining, PnL Rs.{result3['pnl']}")
        
        # Verify final state
        db.refresh(trade)
        assert trade.status == "CLOSED"
        print(f"  PASS: Final status = {trade.status}")
        
        # Cleanup
        db.delete(trade)
        # Clean up the log entries too
        db.query(db_models.DBAgentLog).filter(
            db_models.DBAgentLog.symbol == "TESTPARTIAL"
        ).delete()
        db.commit()
        
        print("\n" + "=" * 50)
        print(" ALL PARTIAL CLOSE TESTS PASSED")
        print("=" * 50)
        
    except Exception as e:
        db.rollback()
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_partial_close()
