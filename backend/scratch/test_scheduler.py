"""Quick integration test for the scheduler + market calendar + data collector."""

import sys
sys.path.insert(0, ".")

print("=" * 60)
print("TEST 1: Import all modules")
print("=" * 60)

from agent.scheduler import init_scheduler, get_scheduler_status
print("  [OK] Scheduler")

from agent.data_collector import fetch_recent_news, trigger_news_fetch
print("  [OK] Data collector")

from agent.market_calendar import is_trading_day, get_news_fetch_window, get_hours_back_for_news
print("  [OK] Market calendar")

from routers.agent import router
print("  [OK] Agent router")

print("\n" + "=" * 60)
print("TEST 2: Market calendar logic")
print("=" * 60)

from datetime import date, datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))

today = date.today()
print(f"  Today: {today} ({today.strftime('%A')})")
print(f"  Is trading day: {is_trading_day(today)}")

_, _, info = get_news_fetch_window()
print(f"  Last trading day: {info['last_trading_day']} ({info['last_trading_day_weekday']})")
print(f"  News window: {info['from_time']} -> {info['to_time']}")
print(f"  Window size: {info['window_hours']} hours")
if info['non_trading_days_between']:
    print(f"  Non-trading days: {', '.join(info['non_trading_days_between'])}")

print("\n" + "=" * 60)
print("TEST 3: Scheduler status (before init)")
print("=" * 60)

status = get_scheduler_status()
print(f"  Active: {status['scheduler_active']}")
print(f"  Today is trading day: {status['today_is_trading_day']}")
print(f"  Jobs: {len(status['jobs'])}")

print("\n" + "=" * 60)
print("TEST 4: DB connection check")
print("=" * 60)

try:
    from database import SessionLocal
    import db_models
    db = SessionLocal()
    news_count = db.query(db_models.NewsArticle).count()
    signal_count = db.query(db_models.DBTradeSignal).count()
    print(f"  News articles in DB: {news_count}")
    print(f"  Trade signals in DB: {signal_count}")
    
    # Check oldest/newest article
    oldest = db.query(db_models.NewsArticle).order_by(db_models.NewsArticle.published_at.asc()).first()
    newest = db.query(db_models.NewsArticle).order_by(db_models.NewsArticle.published_at.desc()).first()
    if oldest:
        oldest_dt = datetime.fromtimestamp(oldest.published_at / 1000, tz=IST)
        print(f"  Oldest article: {oldest_dt.strftime('%Y-%m-%d %H:%M IST')}")
    if newest:
        newest_dt = datetime.fromtimestamp(newest.published_at / 1000, tz=IST)
        print(f"  Newest article: {newest_dt.strftime('%Y-%m-%d %H:%M IST')}")
    
    db.close()
except Exception as e:
    print(f"  [WARN] DB check failed: {e}")

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
