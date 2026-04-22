import sys
sys.path.insert(0, ".")
from database import SessionLocal
import db_models
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
today = datetime.now(IST).strftime("%Y-%m-%d")

db = SessionLocal()

# Reset all of today's signals to "pending" so Agent 2 can run again
signals = db.query(db_models.DBTradeSignal).filter(
    db_models.DBTradeSignal.market_date == today
).all()

count = 0
for sig in signals:
    sig.confirmation_status = "pending"
    sig.status = "pending_confirmation"
    sig.execution_status = "pending"
    count += 1

db.commit()
print(f"Successfully reset {count} signals to 'pending' state.")
print("You can now click 'Run Agent 2' on your dashboard and it will work!")
db.close()
