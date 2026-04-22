"""
Full end-to-end automation test — runs full pipeline in one call.
Uses longer timeout since Gemini calls can take 2-3 mins total.
"""
import httpx
import json
import time
import sys

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8000"

print("=" * 70)
print("  FULL AUTOMATION TEST - End-to-End Paper Trading Pipeline")
print("=" * 70)

# Step 0: Clear today's signals for a fresh run
print("\n[0] Clearing today's signals for fresh pipeline run...")
from database import SessionLocal
from datetime import datetime, timezone, timedelta
import db_models

IST = timezone(timedelta(hours=5, minutes=30))
today = datetime.now(IST).strftime("%Y-%m-%d")
db = SessionLocal()
deleted = db.query(db_models.DBTradeSignal).filter(
    db_models.DBTradeSignal.market_date == today
).delete(synchronize_session=False)
db.commit()
print(f"    Cleared {deleted} signals for {today}")
db.close()

# Step 1: Run full pipeline (Agent 1 + 2 + 3) in one call
print("\n" + "-" * 70)
print("[1] Running FULL PIPELINE (Agent 1 -> 2 -> 3)")
print("    This calls Gemini AI for each symbol. Please wait 2-4 mins...")
print("-" * 70)

try:
    r = httpx.post(f"{BASE}/api/agent/run-full-pipeline", timeout=300.0)
    data = r.json()

    # Agent 1
    a1 = data.get("agent1_discovery", {})
    total_analyzed = a1.get("total_analyzed", 0)
    summ1 = a1.get("signals_summary", {})
    print(f"\n  AGENT 1 (Discovery):")
    print(f"    Analyzed: {total_analyzed} symbols")
    print(f"    WATCH: {summ1.get('watch', 0)} | Ignore: {summ1.get('ignore', 0)} | Stale: {summ1.get('stale', 0)}")

    # Agent 2
    a2 = data.get("agent2_confirmation", {})
    summ2 = a2.get("summary", {})
    print(f"\n  AGENT 2 (Confirmation):")
    print(f"    Checked: {a2.get('total_checked', 0)}")
    print(f"    Confirmed: {summ2.get('confirmed', 0)} | Invalidated: {summ2.get('invalidated', 0)}")
    for res in a2.get("results", []):
        print(f"    >> {res['symbol']}: {res['decision']} (confidence={res.get('confidence', 0)})")

    # Agent 3
    a3 = data.get("agent3_execution", {})
    summ3 = a3.get("summary", {})
    print(f"\n  AGENT 3 (Execution):")
    print(f"    Checked: {a3.get('total_checked', 0)}")
    print(f"    PLANNED (ENTER NOW): {summ3.get('planned', 0)}")
    print(f"    Avoided: {summ3.get('avoided', 0)}")
    for res in a3.get("results", []):
        print(f"    >> {res['symbol']}: {res['action']} | {res['execution_decision']} (conf={res.get('confidence', 0)})")

except httpx.ReadTimeout:
    print("    [TIMEOUT] Pipeline took too long. Checking what completed...")
except Exception as e:
    print(f"    [ERROR] {e}")

# Step 2: Check paper trades dashboard
print("\n" + "-" * 70)
print("[2] PAPER TRADING DASHBOARD")
print("-" * 70)

time.sleep(2)
try:
    r = httpx.get(f"{BASE}/api/paper-trading/dashboard", timeout=30)
    dash = r.json()
    port = dash["portfolio"]

    print(f"\n  PORTFOLIO:")
    print(f"    Total Capital:  Rs.{port['total_capital']:>12,.2f}")
    print(f"    Available Cash: Rs.{port['available_cash']:>12,.2f}")
    print(f"    Used Cash:      Rs.{port['used_cash']:>12,.2f}")
    print(f"    Total P&L:      Rs.{port['total_pnl']:>12,.2f}")
    print(f"    Today P&L:      Rs.{port['todays_pnl']:>12,.2f}")
    print(f"    Win Rate:       {port['win_rate']:>11.1f}%")
    print(f"    Open Trades:    {port['open_trades']:>12}")
    print(f"    Closed Trades:  {port['closed_trades']:>12}")

    op = dash["open_positions"]
    print(f"\n  OPEN POSITIONS ({len(op)}):")
    if len(op) == 0:
        print("    (none - Agent 3 did not issue ENTER NOW for any signal)")
    for t in op:
        sign = "+" if t["pnl"] >= 0 else ""
        print(f"    {t['symbol']:>12} | {t['action']} {t['quantity']:>3}x @ Rs.{t['entry_price']:>10,.2f} "
              f"| SL: Rs.{t['stop_loss']:>10,.2f} | Tgt: Rs.{t['target_price']:>10,.2f} "
              f"| Now: Rs.{(t.get('current_price') or 0):>10,.2f} | P&L: {sign}Rs.{abs(t['pnl']):,.2f}")

    cl = dash["recent_closed"]
    print(f"\n  CLOSED TRADES ({len(cl)}):")
    if len(cl) == 0:
        print("    (none)")
    for t in cl:
        sign = "+" if t["pnl"] >= 0 else "-"
        print(f"    {t['symbol']:>12} | Entry: Rs.{t['entry_price']:>10,.2f} -> Exit: Rs.{(t.get('exit_price') or 0):>10,.2f} "
              f"| P&L: {sign}Rs.{abs(t['pnl']):,.2f} ({t['pnl_percentage']:+.2f}%) | {t.get('exit_reason')}")

    logs = dash["recent_activity"]
    print(f"\n  ACTIVITY LOG ({len(logs)}):")
    for l in logs[:8]:
        print(f"    [{l['agent_name']:>14}] {(l.get('symbol') or ''):>12} | {(l.get('signal') or ''):>20} | {(l.get('message') or '')[:55]}")

except Exception as e:
    print(f"    [ERROR] {e}")

# Step 3: Run monitor if open trades exist
print("\n" + "-" * 70)
print("[3] POSITION MONITOR (checking SL/Target auto-close)")
print("-" * 70)
try:
    r = httpx.post(f"{BASE}/api/paper-trading/monitor", timeout=30)
    mon = r.json()
    print(f"    Status: {mon.get('status')}")
    print(f"    Monitored: {mon.get('total_monitored', 0)}")
    print(f"    Auto-closed: {mon.get('actions_taken', 0)}")
    for a in mon.get("actions", []):
        print(f"    >> {a['symbol']}: {a['action']} @ Rs.{a['exit_price']:.2f} | P&L: Rs.{a['pnl']:.2f}")
except Exception as e:
    print(f"    [ERROR] {e}")

print("\n" + "=" * 70)
print("  AUTOMATION TEST COMPLETE")
print("=" * 70)
print(f"  Pipeline: A1 -> A2 -> A3 -> Auto-PaperTrade -> Monitor")
print(f"  The system automatically creates trades when Agent 3 says ENTER NOW")
print(f"  and auto-closes them when stop-loss or target is hit.")
print(f"  Open http://localhost:5173/paper-trading to see the dashboard!")
