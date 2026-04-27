"""
Manually trigger Agent 2 (Market Reality Validator) for testing.

Usage:
    python .\scratch\run_agent2.py           # live market data mode
    python .\scratch\run_agent2.py --debug   # use DB snapshots (no live API call)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

parser = argparse.ArgumentParser(description="Trigger Agent 2 manually")
parser.add_argument("--debug", action="store_true", help="Use DB snapshots instead of live market data")
args = parser.parse_args()

debug_mode = args.debug

print(f"\nTriggering Agent 2 (Market Reality Validator) {'DEBUG' if debug_mode else 'LIVE'} manually...")

from database import SessionLocal
from agent.confirmation.confirmation_agent import run_market_open_confirmation

db = SessionLocal()
try:
    result = run_market_open_confirmation(db, debug_mode=debug_mode)

    print("\nAgent 2 execution completed! Check the logs above.")
    print(f"  Total checked : {result.get('total_checked', 0)}")
    s = result.get("summary", {})
    print(f"  Confirmed     : {s.get('confirmed', 0)}")
    print(f"  Weakened      : {s.get('weakened', 0)}")
    print(f"  Invalidated   : {s.get('invalidated', 0)}")
    print(f"  Skipped       : {s.get('skipped', 0)}")
    print(f"  Duration      : {result.get('duration_ms', 0)}ms")
finally:
    db.close()
