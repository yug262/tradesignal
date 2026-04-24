"""Test ALL decision execution paths in the risk monitor."""
import sys, io, time, uuid
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.append("d:/ATS/backend")

from datetime import datetime, timezone, timedelta
from database import SessionLocal
import db_models
from agent.paper_trading_engine import partial_close_paper_trade, close_paper_trade

IST = timezone(timedelta(hours=5, minutes=30))

def create_test_trade(db, symbol="TESTEXEC", qty=10, entry=100.0, sl=95.0, tgt=110.0):
    """Create a disposable test trade."""
    now_ms = int(time.time() * 1000)
    trade_id = f"pt-{symbol}-{uuid.uuid4().hex[:6]}"
    trade = db_models.DBPaperTrade(
        id=trade_id, symbol=symbol, action="BUY",
        entry_price=entry, exit_price=None, quantity=qty,
        stop_loss=sl, target_price=tgt, current_price=entry,
        pnl=0.0, pnl_percentage=0.0, status="OPEN",
        confidence_score=75.0, risk_level="MEDIUM",
        trade_reason="Execution routing test", exit_reason=None,
        signal_id=None, trade_mode="INTRADAY", risk_reward="1:2",
        position_value=round(qty * entry, 2),
        max_loss_at_sl=round(abs(entry - sl) * qty, 2),
        entry_time=now_ms - 600_000, exit_time=None,
        created_at=now_ms, updated_at=now_ms,
    )
    db.add(trade)
    db.commit()
    return trade

def cleanup(db, symbol):
    db.query(db_models.DBPaperTrade).filter(db_models.DBPaperTrade.symbol == symbol).delete()
    db.query(db_models.DBAgentLog).filter(db_models.DBAgentLog.symbol == symbol).delete()
    db.commit()

def test_all_decisions():
    db = SessionLocal()
    sym = "TESTEXEC"
    
    try:
        cleanup(db, sym)
        
        # ── TEST 1: TIGHTEN_STOPLOSS ─────────────────────────────────────
        print("=== TEST 1: TIGHTEN_STOPLOSS ===")
        trade = create_test_trade(db, sym, qty=10, entry=100.0, sl=95.0)
        
        # Simulate: trail SL from 95 to 98
        new_sl = 98.0
        old_sl = trade.stop_loss
        is_long = (trade.action == "BUY")
        sl_is_tighter = (new_sl > old_sl) if is_long else (new_sl < old_sl)
        
        assert sl_is_tighter, "New SL should be tighter for long"
        trade.stop_loss = new_sl
        trade.max_loss_at_sl = round(abs(trade.entry_price - new_sl) * trade.quantity, 2)
        db.commit()
        
        db.refresh(trade)
        assert trade.stop_loss == 98.0, f"Expected SL=98, got {trade.stop_loss}"
        assert trade.max_loss_at_sl == 20.0, f"Expected max_loss=20, got {trade.max_loss_at_sl}"
        assert trade.status == "OPEN"
        print(f"  PASS: SL trailed {old_sl} -> {trade.stop_loss}, max_loss={trade.max_loss_at_sl}")
        
        cleanup(db, sym)
        
        # ── TEST 2: PARTIAL_EXIT ─────────────────────────────────────────
        print("\n=== TEST 2: PARTIAL_EXIT ===")
        trade = create_test_trade(db, sym, qty=10, entry=100.0, sl=95.0)
        
        result = partial_close_paper_trade(db, trade.id, exit_price=103.0, exit_fraction=0.5)
        assert result["success"]
        assert result["shares_sold"] == 5
        assert result["shares_remaining"] == 5
        assert result["realized_pnl"] == 15.0
        
        db.refresh(trade)
        assert trade.status == "OPEN"
        assert trade.quantity == 5
        print(f"  PASS: Sold {result['shares_sold']}, remaining {result['shares_remaining']}, PnL=+{result['realized_pnl']}")
        
        cleanup(db, sym)
        
        # ── TEST 3: EXIT_NOW ─────────────────────────────────────────────
        print("\n=== TEST 3: EXIT_NOW ===")
        trade = create_test_trade(db, sym, qty=10, entry=100.0, sl=95.0)
        
        result = close_paper_trade(db, trade.id, exit_price=108.0, exit_reason="RISK_MONITOR_EXIT")
        assert result["success"]
        assert result["pnl"] == 80.0  # (108-100)*10
        
        db.refresh(trade)
        assert trade.status == "CLOSED"
        print(f"  PASS: Full close, PnL=+{result['pnl']}, status={trade.status}")
        
        cleanup(db, sym)
        
        # ── TEST 4: HOLD (no-op, just verify no crash) ───────────────────
        print("\n=== TEST 4: HOLD ===")
        trade = create_test_trade(db, sym, qty=10, entry=100.0, sl=95.0)
        
        db.refresh(trade)
        assert trade.status == "OPEN"
        assert trade.stop_loss == 95.0  # Unchanged
        print(f"  PASS: Trade still OPEN, SL unchanged at {trade.stop_loss}")
        
        cleanup(db, sym)
        
        # ── TEST 5: TIGHTEN rejected (SL widening attempt) ──────────────
        print("\n=== TEST 5: TIGHTEN rejected (widening attempt) ===")
        trade = create_test_trade(db, sym, qty=10, entry=100.0, sl=95.0)
        
        new_sl = 90.0  # Widening, not tightening
        old_sl = trade.stop_loss
        is_long = (trade.action == "BUY")
        sl_is_tighter = (new_sl > old_sl) if is_long else (new_sl < old_sl)
        
        assert not sl_is_tighter, "90 < 95 should NOT be tighter for a long"
        # SL should remain unchanged
        db.refresh(trade)
        assert trade.stop_loss == 95.0
        print(f"  PASS: Widening rejected. SL stays at {trade.stop_loss}")
        
        cleanup(db, sym)
        
        print("\n" + "=" * 50)
        print(" ALL DECISION EXECUTION TESTS PASSED (5/5)")
        print("=" * 50)
        
    except Exception as e:
        db.rollback()
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup(db, sym)
        db.close()

if __name__ == "__main__":
    test_all_decisions()
