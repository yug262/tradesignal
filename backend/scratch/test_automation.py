import os
import sys
import json
import time
import traceback
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import SessionLocal
import db_models

import agent.paper_trading_engine as pte
import agent.risk_monitor as rm

IST = timezone(timedelta(hours=5, minutes=30))


# =============================================================================
# Helpers
# =============================================================================

def now_ms() -> int:
    return int(time.time() * 1000)


def market_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def sep(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def sub(title: str) -> None:
    print("\n" + "-" * 90)
    print(title)
    print("-" * 90)


def jprint(label: str, data) -> None:
    print(f"{label}:")
    try:
        print(json.dumps(data, indent=2, default=str))
    except Exception:
        print(data)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"✅ ASSERT OK: {message}")


def refresh_trade(db, trade_id: str):
    return db.query(db_models.DBPaperTrade).filter_by(id=trade_id).first()


def refresh_signal(db, signal_id: str):
    return db.query(db_models.DBTradeSignal).filter_by(id=signal_id).first()


def get_open_trade_by_signal(db, signal_id: str):
    return (
        db.query(db_models.DBPaperTrade)
        .filter(
            db_models.DBPaperTrade.signal_id == signal_id,
            db_models.DBPaperTrade.status == "OPEN",
        )
        .first()
    )


def cleanup_test_data(db, symbol_prefix: str = "TSTAUTO_") -> None:
    sub("CLEANUP OLD TEST DATA")
    deleted_open = (
        db.query(db_models.DBPaperTrade)
        .filter(db_models.DBPaperTrade.symbol.like(f"{symbol_prefix}%"))
        .delete(synchronize_session=False)
    )
    deleted_signals = (
        db.query(db_models.DBTradeSignal)
        .filter(db_models.DBTradeSignal.symbol.like(f"{symbol_prefix}%"))
        .delete(synchronize_session=False)
    )
    db.commit()
    print(f"Deleted paper trades: {deleted_open}")
    print(f"Deleted signals: {deleted_signals}")


def make_signal(
    db,
    symbol: str,
    action: str = "BUY",
    entry_price: float = 1000.0,
    stop_loss: float = 980.0,
    target_price: float = 1040.0,
    qty: int = 10,
    confidence: int = 80,
    final_summary: str = "Test execution signal",
):
    """
    Create a DBTradeSignal in the same general shape Agent 3 would leave behind
    after producing a valid ENTER NOW execution plan.
    """
    signal_id = f"sig-{symbol}-{now_ms()}"
    rr_numeric = round((target_price - entry_price) / max(entry_price - stop_loss, 0.0001), 2) if action == "BUY" else round((entry_price - target_price) / max(stop_loss - entry_price, 0.0001), 2)

    execution_data = {
        "action": action,
        "execution_decision": "ENTER NOW",
        "trade_mode": "DELIVERY",
        "confidence": confidence,
        "entry_plan": {
            "entry_type": "MARKET",
            "entry_price": entry_price,
            "condition": "Integration test immediate entry",
        },
        "stop_loss": {
            "price": stop_loss,
            "reason": "Integration test stop loss",
        },
        "target": {
            "price": target_price,
            "reason": "Integration test target",
        },
        "position_sizing": {
            "position_size_shares": qty,
            "position_size_inr": round(entry_price * qty, 2),
            "risk_per_share": round(abs(entry_price - stop_loss), 2),
            "max_loss_at_sl": round(abs(entry_price - stop_loss) * qty, 2),
            "capital_used_pct": 0.0,
            "sizing_note": "Integration test sizing",
        },
        "risk_reward": rr_numeric,
        "why_now_or_why_wait": "Integration test execution path",
        "final_summary": final_summary,
    }

    signal = db_models.DBTradeSignal(
        id=signal_id,
        symbol=symbol,
        signal_type=action,
        trade_mode="DELIVERY",
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_price=target_price,
        risk_reward=rr_numeric,
        confidence=confidence,
        reasoning={"source": "post_agent3_integration_test"},
        stock_snapshot={"company_name": symbol},
        generated_at=now_ms(),
        market_date=market_date_str(),
        status="planned",
        confirmation_status="confirmed",
        confirmed_at=now_ms(),
        confirmation_data={"decision": "TRADE"},
        execution_status="planned",
        executed_at=now_ms(),
        execution_data=execution_data,
        risk_monitor_status=None,
        risk_last_checked_at=None,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)

    print(f"Created signal: {signal.id}")
    jprint("Signal execution_data", signal.execution_data)
    return signal


def create_trade_from_signal(db, signal):
    sub(f"AUTO-CREATE PAPER TRADE FROM SIGNAL [{signal.symbol}]")
    result = pte.auto_create_from_execution(db, signal)
    jprint("auto_create_from_execution() result", result)
    assert_true(result is not None, "auto_create_from_execution returned a result")
    assert_true(result.get("success") is True, "paper trade auto-created successfully")
    trade = refresh_trade(db, result["trade_id"])
    assert_true(trade is not None, "paper trade row exists")
    assert_true(trade.signal_id == signal.id, "paper trade linked to signal_id")
    assert_true(trade.status == "OPEN", "paper trade starts OPEN")
    print(f"Trade created: {trade.id}")
    return trade


def force_risk_monitor_eligibility(db, trade, signal=None):
    sub(f"FORCE RISK MONITOR ELIGIBILITY [{trade.symbol}]")
    trade.updated_at = (trade.updated_at or now_ms()) - 30000
    if signal:
        signal.risk_last_checked_at = (signal.risk_last_checked_at or now_ms()) - 30000
    db.commit()
    print("Set timestamps 30s in the past to bypass MIN_CHECK_INTERVAL_SECONDS.")


# =============================================================================
# Monkeypatch contexts
# =============================================================================

class RiskMonitorPatchContext:
    def __init__(self, quote, candles, depth):
        self.quote = quote
        self.candles = candles
        self.depth = depth
        self.orig_quote = None
        self.orig_candles = None
        self.orig_depth = None

    def __enter__(self):
        self.orig_quote = rm.fetch_live_quote
        self.orig_candles = rm.fetch_intraday_candles
        self.orig_depth = rm.fetch_market_depth

        rm.fetch_live_quote = lambda symbol: self.quote
        rm.fetch_intraday_candles = lambda symbol, interval_minutes=5: self.candles
        rm.fetch_market_depth = lambda symbol: self.depth
        return self

    def __exit__(self, exc_type, exc, tb):
        rm.fetch_live_quote = self.orig_quote
        rm.fetch_intraday_candles = self.orig_candles
        rm.fetch_market_depth = self.orig_depth


class PaperPricePatchContext:
    def __init__(self, price_map):
        self.price_map = price_map
        self.orig = None

    def __enter__(self):
        self.orig = pte._fetch_live_price
        pte._fetch_live_price = lambda symbol: self.price_map.get(symbol, self.orig(symbol))
        return self

    def __exit__(self, exc_type, exc, tb):
        pte._fetch_live_price = self.orig


# =============================================================================
# Test Cases
# =============================================================================

def test_case_1_auto_create(db):
    sep("TEST CASE 1 — AGENT 3 STYLE SIGNAL -> AUTO PAPER TRADE CREATION")

    signal = make_signal(
        db=db,
        symbol="TSTAUTO_CREATE",
        entry_price=1000.0,
        stop_loss=980.0,
        target_price=1040.0,
        qty=10,
        final_summary="Auto create integration test",
    )
    trade = create_trade_from_signal(db, signal)

    print("\nFinal state after auto-create:")
    print(f"Signal status: {signal.status}")
    print(f"Signal execution_status: {signal.execution_status}")
    print(f"Trade status: {trade.status}")
    print(f"Trade entry/sl/target: {trade.entry_price} / {trade.stop_loss} / {trade.target_price}")


def test_case_2_risk_monitor_tightens_sl(db):
    sep("TEST CASE 2 — RISK MONITOR TIGHTENS STOP LOSS")

    signal = make_signal(
        db=db,
        symbol="TSTAUTO_TIGHTEN",
        entry_price=1000.0,
        stop_loss=980.0,
        target_price=1040.0,
        qty=10,
        final_summary="Risk tighten SL test",
    )
    trade = create_trade_from_signal(db, signal)
    old_sl = trade.stop_loss

    force_risk_monitor_eligibility(db, trade, signal)

    mock_quote = {
        "ltp": 1022.0,
        "open": 1002.0,
        "high": 1025.0,
        "low": 998.0,
        "close": 1000.0,
        "volume": 500000,
        "vwap": 1012.0,
    }
    mock_candles = [
        [1, 1001, 1005, 999, 1004, 12000],
        [2, 1004, 1008, 1003, 1007, 14000],
        [3, 1007, 1015, 1006, 1013, 18000],
        [4, 1013, 1020, 1011, 1019, 22000],
        [5, 1019, 1024, 1018, 1022, 24000],
    ]
    mock_depth = {
        "buy_quantity": 200000,
        "sell_quantity": 120000,
    }

    with RiskMonitorPatchContext(mock_quote, mock_candles, mock_depth):
        result = rm.run_risk_monitor(db=db, force=True)

    jprint("Risk monitor result", result)

    trade = refresh_trade(db, trade.id)
    signal = refresh_signal(db, signal.id)

    print("\nPost-risk-monitor DB state:")
    print(f"Old SL: {old_sl}")
    print(f"New Trade SL: {trade.stop_loss}")
    print(f"Signal SL: {signal.stop_loss}")
    print(f"Signal risk_monitor_status: {signal.risk_monitor_status}")
    jprint("Signal risk_monitor_data", signal.risk_monitor_data)

    assert_true(trade.status == "OPEN", "trade remains OPEN after tighten flow")
    assert_true(trade.stop_loss >= old_sl, "trade stop loss did not move backward")
    assert_true(signal.stop_loss == trade.stop_loss, "signal stop loss synced with trade")
    assert_true(signal.risk_monitor_status == "TIGHTEN_STOPLOSS", "signal RM status is TIGHTEN_STOPLOSS")


def test_case_3_risk_monitor_exit_now(db):
    sep("TEST CASE 3 — RISK MONITOR FORCES EARLY EXIT")

    signal = make_signal(
        db=db,
        symbol="TSTAUTO_EXIT",
        entry_price=1000.0,
        stop_loss=980.0,
        target_price=1040.0,
        qty=10,
        final_summary="Risk EXIT_NOW test",
    )
    trade = create_trade_from_signal(db, signal)

    force_risk_monitor_eligibility(db, trade, signal)

    # Crafted to look like a bad reversal / loss condition.
    mock_quote = {
        "ltp": 984.0,
        "open": 1001.0,
        "high": 1003.0,
        "low": 982.0,
        "close": 1000.0,
        "volume": 900000,
        "vwap": 995.0,
    }
    mock_candles = [
        [1, 1001, 1002, 998, 999, 10000],
        [2, 999, 1000, 994, 995, 18000],
        [3, 995, 996, 990, 991, 25000],
        [4, 991, 992, 986, 987, 32000],
        [5, 987, 988, 983, 984, 45000],
    ]
    mock_depth = {
        "buy_quantity": 50000,
        "sell_quantity": 250000,
    }

    with RiskMonitorPatchContext(mock_quote, mock_candles, mock_depth):
        result = rm.run_risk_monitor(db=db, force=True)

    jprint("Risk monitor result", result)

    trade = refresh_trade(db, trade.id)
    signal = refresh_signal(db, signal.id)

    print("\nPost-risk-monitor DB state:")
    print(f"Trade status: {trade.status}")
    print(f"Trade exit_reason: {trade.exit_reason}")
    print(f"Trade pnl: {trade.pnl}")
    print(f"Signal status: {signal.status}")
    print(f"Signal risk_monitor_status: {signal.risk_monitor_status}")
    jprint("Signal risk_monitor_data", signal.risk_monitor_data)

    assert_true(trade.status == "CLOSED", "trade closed by risk monitor")
    assert_true(trade.exit_reason == "RISK_MONITOR_EXIT", "exit reason is RISK_MONITOR_EXIT")
    assert_true(signal.status == "closed", "signal closed after RM exit")
    assert_true(signal.risk_monitor_status == "RISK_MONITOR_EXIT", "signal RM status synced to RISK_MONITOR_EXIT")


def test_case_4_paper_monitor_target_hit(db):
    sep("TEST CASE 4 — PAPER ENGINE TARGET HIT AUTO-CLOSE")

    signal = make_signal(
        db=db,
        symbol="TSTAUTO_TARGET",
        entry_price=1000.0,
        stop_loss=980.0,
        target_price=1040.0,
        qty=10,
        final_summary="Paper target hit test",
    )
    trade = create_trade_from_signal(db, signal)

    with PaperPricePatchContext({"TSTAUTO_TARGET": 1045.0}):
        result = pte.monitor_open_positions(db=db)

    jprint("Paper monitor result", result)

    trade = refresh_trade(db, trade.id)
    signal = refresh_signal(db, signal.id)

    print("\nPost-paper-monitor DB state:")
    print(f"Trade status: {trade.status}")
    print(f"Trade exit_reason: {trade.exit_reason}")
    print(f"Trade pnl: {trade.pnl}")
    print(f"Signal status: {signal.status}")
    print(f"Signal risk_monitor_status: {signal.risk_monitor_status}")

    assert_true(trade.status == "CLOSED", "trade closed at target")
    assert_true(trade.exit_reason == "TARGET_HIT", "exit reason is TARGET_HIT")
    assert_true(signal.status == "closed", "signal closed after target hit")
    assert_true(signal.risk_monitor_status == "TARGET_HIT", "signal RM status synced to TARGET_HIT")


def test_case_5_double_close_safety(db):
    sep("TEST CASE 5 — DOUBLE-CLOSE SAFETY")

    signal = make_signal(
        db=db,
        symbol="TSTAUTO_RACE",
        entry_price=1000.0,
        stop_loss=980.0,
        target_price=1040.0,
        qty=10,
        final_summary="Double-close safety test",
    )
    trade = create_trade_from_signal(db, signal)

    # First close via paper engine
    with PaperPricePatchContext({"TSTAUTO_RACE": 1045.0}):
        result_1 = pte.monitor_open_positions(db=db)

    jprint("First close result", result_1)

    trade = refresh_trade(db, trade.id)
    signal = refresh_signal(db, signal.id)

    assert_true(trade.status == "CLOSED", "trade closed in first pass")

    # Now force Risk Monitor to look at the same trade after it's already closed.
    # It should not crash, should not reopen, and should not double-close.
    force_risk_monitor_eligibility(db, trade, signal)

    mock_quote = {
        "ltp": 970.0,
        "open": 1001.0,
        "high": 1002.0,
        "low": 969.0,
        "close": 1000.0,
        "volume": 1000000,
        "vwap": 990.0,
    }
    mock_candles = [
        [1, 1000, 1001, 998, 999, 10000],
        [2, 999, 1000, 995, 996, 12000],
        [3, 996, 997, 990, 991, 14000],
        [4, 991, 992, 980, 982, 30000],
        [5, 982, 983, 968, 970, 50000],
    ]
    mock_depth = {
        "buy_quantity": 30000,
        "sell_quantity": 300000,
    }

    with RiskMonitorPatchContext(mock_quote, mock_candles, mock_depth):
        result_2 = rm.run_risk_monitor(db=db, force=True)

    jprint("Risk monitor result after already-closed trade", result_2)

    trade = refresh_trade(db, trade.id)
    signal = refresh_signal(db, signal.id)

    print("\nPost-double-close-safety DB state:")
    print(f"Trade status: {trade.status}")
    print(f"Trade exit_reason: {trade.exit_reason}")
    print(f"Trade pnl: {trade.pnl}")
    print(f"Signal status: {signal.status}")
    print(f"Signal risk_monitor_status: {signal.risk_monitor_status}")

    assert_true(trade.status == "CLOSED", "trade remains CLOSED after second close attempt")
    assert_true(signal.status == "closed", "signal remains closed after second close attempt")


# =============================================================================
# Main
# =============================================================================

def run_all_tests():
    db = SessionLocal()
    start = now_ms()

    try:
        sep("POST-AGENT-3 AUTOMATION INTEGRATION TEST SUITE")
        cleanup_test_data(db)

        portfolio_before = pte.get_or_create_portfolio(db)
        sub("PORTFOLIO BEFORE")
        print(f"Total capital: {portfolio_before.total_capital}")
        print(f"Available cash: {portfolio_before.available_cash}")
        print(f"Total pnl: {portfolio_before.total_pnl}")

        test_case_1_auto_create(db)
        test_case_2_risk_monitor_tightens_sl(db)
        test_case_3_risk_monitor_exit_now(db)
        test_case_4_paper_monitor_target_hit(db)
        test_case_5_double_close_safety(db)

        portfolio_after = pte.get_or_create_portfolio(db)
        sub("PORTFOLIO AFTER")
        print(f"Total capital: {portfolio_after.total_capital}")
        print(f"Available cash: {portfolio_after.available_cash}")
        print(f"Total pnl: {portfolio_after.total_pnl}")
        print(f"Open trades: {portfolio_after.open_trades}")
        print(f"Closed trades: {portfolio_after.closed_trades}")

        duration = now_ms() - start
        sep("✅ ALL POST-AGENT-3 AUTOMATION TESTS PASSED")
        print(f"Total duration: {duration} ms")

    except Exception as e:
        sep("❌ TEST SUITE FAILED")
        print(f"Error: {e}")
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_all_tests()
