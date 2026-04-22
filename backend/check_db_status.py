import sys
sys.path.insert(0, ".")
from database import SessionLocal
import db_models
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
today = datetime.now(IST).strftime("%Y-%m-%d")

db = SessionLocal()

signals = db.query(db_models.DBTradeSignal).filter(
    db_models.DBTradeSignal.market_date == today
).all()

print(f"--- TODAY'S SIGNALS ({today}) ---")
if not signals:
    print("No signals found for today.")
else:
    for s in signals:
        print(f"Symbol: {s.symbol:12} | Type: {s.signal_type:8} | Status: {s.status:20} | Conf Status: {s.confirmation_status:12} | Exec Status: {s.execution_status:12}")

db.close()
