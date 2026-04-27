import sys
import os
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.risk.risk_rules import evaluate_trade

print("="*60)
print(" AGENT 4 (RISK MONITOR) SCENARIO TESTS")
print("="*60)

# Helper to run a test
def run_scenario(name, features):
    base = {
        "symbol": "TEST", "quantity": 10, "trade_mode": "DELIVERY", # Use DELIVERY to bypass intraday time exits
        "is_long": True, "entry_price": 1000, "stop_loss": 900,
        "target_price": 1100, "ltp": 1000, "pnl_percent": 0.0,
        "pnl_rupees_total": 0.0, "time_in_trade_seconds": 0,
        "mfe_pct": 0.0, "mae_pct": 0.0, "distance_to_sl": 10.0,
        "distance_to_target": 10.0, "volume_spike_against": False,
        "relative_volume": 1.0, "strong_reversal_candle": False,
        "structure_state": "healthy", "recent_swing_low": 0,
        "recent_swing_high": 0
    }
    base.update(features)
    # We patch datetime inside risk_rules just for intraday time tests
    import agent.risk_rules as rr
    old_now = rr.datetime
    
    class MockDatetime:
        @classmethod
        def now(cls, tz=None):
            # Return a time of 11:00 AM IST to avoid EXIT_BEFORE_CLOSE
            return datetime.now(tz).replace(hour=11, minute=0, second=0)
    
    rr.datetime = MockDatetime
    try:
        res = evaluate_trade(base)
    finally:
        rr.datetime = old_now
        
    print(f"\n[{name}]")
    print(f"  Decision: {res['decision']}")
    print(f"  Reason Code: {res['reason_code']}")
    print(f"  Message: {res['primary_reason']}")
    if res['updated_stop_loss']:
        print(f"  New SL: {res['updated_stop_loss']}")

# --- SCENARIO 1: Max Loss ---
run_scenario("Max Loss Percent", {"pnl_percent": -3.5, "pnl_rupees_total": -350})
run_scenario("Max Loss Rupees", {"pnl_percent": -1.0, "pnl_rupees_total": -5500, "quantity": 550})

# --- SCENARIO 2: Profit Locking ---
run_scenario("Move to Breakeven", {"pnl_percent": 0.6, "ltp": 1006})
run_scenario("Profit Lock Tier 1", {"pnl_percent": 1.6, "ltp": 1016})
run_scenario("Profit Lock Tier 2", {"pnl_percent": 3.5, "ltp": 1035})

# --- SCENARIO 3: Trailing SL ---
run_scenario("Trail Percentage", {"pnl_percent": 2.0, "ltp": 1020, "stop_loss": 1005})

# --- SCENARIO 4: Time Exits ---
run_scenario("Trade Stale (Intraday)", {
    "trade_mode": "INTRADAY",
    "time_in_trade_seconds": 14500, # > 14400 (4 hrs)
    "pnl_percent": 0.1 # < 0.3%
})

run_scenario("No Progress (Intraday)", {
    "trade_mode": "INTRADAY",
    "time_in_trade_seconds": 7500, # > 7200 (2 hrs)
    "pnl_percent": 0.1
})

run_scenario("Delivery Stale", {
    "trade_mode": "DELIVERY",
    "time_in_trade_seconds": 5 * 86400, # 5 days
    "pnl_percent": 0.1 # < 1.0% (must be < 0.5 to avoid breakeven trigger!)
})

# --- SCENARIO 5: Volume Spikes ---
run_scenario("Exhaustion Spike", {
    "volume_spike_against": True,
    "relative_volume": 3.0,
    "distance_to_target": 0.5,
    "pnl_percent": 0.1 # Keep low to avoid profit locking taking priority
})

run_scenario("Panic Move", {
    "volume_spike_against": True,
    "relative_volume": 3.0,
    "strong_reversal_candle": True,
    "pnl_percent": -0.5
})

run_scenario("Volume Spike Against", {
    "volume_spike_against": True,
    "relative_volume": 3.0,
    "pnl_percent": -0.5
})

# --- SCENARIO 6: Trend Reversal ---
run_scenario("Profit Surrender", {
    "mfe_pct": 2.5,
    "structure_state": "reversing",
    "strong_reversal_candle": True,
    "pnl_percent": 0.1
})

run_scenario("Structure Reversal Critical", {
    "structure_state": "reversing",
    "strong_reversal_candle": True,
    "distance_to_sl": 0.5,
    "pnl_percent": -0.5
})

run_scenario("Structure Weakening", {
    "structure_state": "reversing",
    "ltp": 1010,
    "stop_loss": 900,
    "pnl_percent": 0.1
})

# --- SCENARIO 7: Hold ---
run_scenario("Healthy Hold", {
    "pnl_percent": 0.2,
    "ltp": 1002
})

print("\n" + "="*60)
print(" AUTOMATION (PAPER TRADING ENGINE) SCENARIO TESTS")
print("="*60)

from database import SessionLocal
import db_models
import agent.paper_trading_engine as pte

db = SessionLocal()

db.query(db_models.DBPaperTrade).filter_by(status="OPEN").delete()
db.commit()

print("\nCreating 4 mock trades...")

t1 = pte.create_paper_trade(db, "TEST_TGT_LONG", 100, 90, 110, 10, "BUY", "DELIVERY")
t2 = pte.create_paper_trade(db, "TEST_SL_LONG", 100, 90, 110, 10, "BUY", "DELIVERY")
t3 = pte.create_paper_trade(db, "TEST_TGT_SHORT", 100, 110, 90, 10, "SELL", "DELIVERY")
t4 = pte.create_paper_trade(db, "TEST_SL_SHORT", 100, 110, 90, 10, "SELL", "DELIVERY")

print("Created 4 open trades.")

mock_prices = {
    "TEST_TGT_LONG": 115, # > 110 Target
    "TEST_SL_LONG": 85,   # < 90 SL
    "TEST_TGT_SHORT": 85, # < 90 Target
    "TEST_SL_SHORT": 115  # > 110 SL
}

original_fetch = pte._fetch_live_price
pte._fetch_live_price = lambda sym: mock_prices.get(sym, original_fetch(sym))

print("\nRunning Paper Trade Monitor...")
res = pte.monitor_open_positions(db)
print(f"Total Monitored: {res.get('total_monitored')}")
print(f"Actions Taken: {res.get('actions_taken')}")

for action in res.get("actions", []):
    print(f"  {action['symbol']}: Action={action['action']}, Exit Price={action['exit_price']}, PnL={action['pnl']}")

db.close()
