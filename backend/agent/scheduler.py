"""Scheduler -- orchestrates all automated jobs for the trading system.

Jobs:
  1. DAILY NEWS FETCH    - Every day at 06:00 AM IST: pull news from endpoint -> DB
  2. DAILY DB CLEANUP    - Every day at 05:00 AM IST: delete news older than 5 days
  3. PRE-MARKET AGENT    - Trading days at 08:30 AM IST: analyze news -> generate signals

Uses APScheduler with CronTriggers. Started/stopped with FastAPI lifecycle.
"""

import time
import traceback
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from database import SessionLocal
from agent.market_calendar import is_trading_day, IST

IST_TZ = pytz.timezone("Asia/Kolkata")

scheduler = BackgroundScheduler(timezone=IST_TZ)
_is_started = False


# ═══════════════════════════════════════════════════════════════════════════════
# JOB 1: Daily News Fetch (every day 06:00 AM IST)
# ═══════════════════════════════════════════════════════════════════════════════

def _daily_news_fetch_job():
    """
    Fetch news from the configured endpoint and save to DB.
    Runs EVERY DAY at 6:00 AM IST (including weekends/holidays)
    so we never miss news that builds up over non-trading days.
    """
    from store import _get_store
    from agent.data_collector import trigger_news_fetch

    now = datetime.now(IST)
    print(f"\n{'='*60}")
    print(f"[SCHEDULER] DAILY NEWS FETCH -- {now.strftime('%Y-%m-%d %H:%M IST (%A)')}")
    print(f"{'='*60}")

    db = SessionLocal()
    try:
        config = _get_store().config
        if config.use_mock_data:
            print("[SCHEDULER] Mock mode enabled -- skipping live news fetch")
            return

        endpoint_url = config.news_endpoint_url
        if not endpoint_url:
            print("[SCHEDULER] No news endpoint URL configured -- skipping")
            return

        print(f"[SCHEDULER] Fetching from: {endpoint_url[:80]}...")
        new_count = trigger_news_fetch(endpoint_url, db)
        print(f"[SCHEDULER] Done! Saved {new_count} new articles to DB")

    except Exception as e:
        print(f"[SCHEDULER] Daily news fetch FAILED: {e}")
        traceback.print_exc()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# JOB 2: DB Cleanup -- delete news older than 5 days (every day 05:00 AM IST)
# ═══════════════════════════════════════════════════════════════════════════════

def _daily_cleanup_job():
    """
    Delete news articles older than 5 days to keep DB lean.
    Also deletes trade signals older than 30 days.
    Runs every day at 5:00 AM IST.
    """
    import db_models

    now = datetime.now(IST)
    print(f"\n{'='*60}")
    print(f"[SCHEDULER] DB CLEANUP -- {now.strftime('%Y-%m-%d %H:%M IST (%A)')}")
    print(f"{'='*60}")

    db = SessionLocal()
    try:
        # --- Delete news older than 5 days ---
        five_days_ago_ms = int((time.time() - 5 * 24 * 3600) * 1000)
        old_news = (
            db.query(db_models.NewsArticle)
            .filter(db_models.NewsArticle.published_at < five_days_ago_ms)
        )
        news_count = old_news.count()
        if news_count > 0:
            old_news.delete(synchronize_session=False)
            print(f"[CLEANUP] Deleted {news_count} news articles older than 5 days")
        else:
            print(f"[CLEANUP] No old news articles to delete")

        # --- Delete trade signals older than 30 days ---
        thirty_days_ago_ms = int((time.time() - 30 * 24 * 3600) * 1000)
        old_signals = (
            db.query(db_models.DBTradeSignal)
            .filter(db_models.DBTradeSignal.generated_at < thirty_days_ago_ms)
        )
        sig_count = old_signals.count()
        if sig_count > 0:
            old_signals.delete(synchronize_session=False)
            print(f"[CLEANUP] Deleted {sig_count} trade signals older than 30 days")
        else:
            print(f"[CLEANUP] No old trade signals to delete")

        db.commit()
        print(f"[CLEANUP] Done!")

    except Exception as e:
        print(f"[SCHEDULER] DB cleanup FAILED: {e}")
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# JOB 3: Pre-Market Agent (trading days at 08:30 AM IST)
# ═══════════════════════════════════════════════════════════════════════════════

def _pre_market_agent_job():
    """
    Full pre-market analysis pipeline.
    Only runs on TRADING DAYS (skips weekends and NSE holidays).
    
    Pipeline:
      1. Check if today is a trading day
      2. Fetch fresh news from endpoint (last market close -> now)
      3. Group news by affected symbols
      4. Fetch live stock prices
      5. Run Gemini deep analysis on each symbol
      6. Generate and save trading signals
    """
    from agent.signal_generator import run_full_analysis

    now = datetime.now(IST)
    today = now.date()

    print(f"\n{'='*60}")
    print(f"[SCHEDULER] PRE-MARKET AGENT TRIGGER -- {now.strftime('%Y-%m-%d %H:%M IST (%A)')}")
    print(f"{'='*60}")

    # Check if today is a trading day
    if not is_trading_day(today):
        reason = "weekend" if today.weekday() >= 5 else "NSE holiday"
        print(f"[SCHEDULER] Today is NOT a trading day ({reason}) -- skipping agent run")
        return

    print(f"[SCHEDULER] Today IS a trading day -- starting full analysis pipeline...")

    try:
        result = run_full_analysis()
        total = result.get("total_analyzed", 0)
        s = result.get("signals_summary", {})
        duration = result.get("duration_ms", 0)
        print(
            f"\n[SCHEDULER] Agent run COMPLETE! "
            f"Analyzed {total} symbols -> "
            f"BUY: {s.get('buy', 0)}, SELL: {s.get('sell', 0)}, "
            f"HOLD: {s.get('hold', 0)}, NO_TRADE: {s.get('no_trade', 0)} "
            f"({duration}ms)"
        )
    except Exception as e:
        print(f"[SCHEDULER] Agent run FAILED: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════════════
# Scheduler Init / Shutdown
# ═══════════════════════════════════════════════════════════════════════════════

def init_scheduler():
    """Initialize and start all scheduled jobs."""
    global _is_started

    if _is_started:
        return

    # ── JOB 1: Daily news fetch at 06:00 AM IST (every day) ──────────────
    scheduler.add_job(
        _daily_news_fetch_job,
        trigger=CronTrigger(hour=6, minute=0, timezone=IST_TZ),
        id="daily_news_fetch",
        name="Daily News Fetch (06:00 AM IST)",
        replace_existing=True,
    )

    # ── JOB 2: DB cleanup at 05:00 AM IST (every day) ────────────────────
    scheduler.add_job(
        _daily_cleanup_job,
        trigger=CronTrigger(hour=5, minute=0, timezone=IST_TZ),
        id="daily_db_cleanup",
        name="Daily DB Cleanup (05:00 AM IST)",
        replace_existing=True,
    )

    # ── JOB 3: Pre-market agent at 08:30 AM IST (Mon-Fri) ────────────────
    # Note: Runs Mon-Fri by cron, but the job itself also checks
    # is_trading_day() to skip NSE holidays that fall on weekdays.
    scheduler.add_job(
        _pre_market_agent_job,
        trigger=CronTrigger(hour=8, minute=30, day_of_week="mon-fri", timezone=IST_TZ),
        id="pre_market_agent",
        name="Pre-Market Trading Agent (08:30 AM IST)",
        replace_existing=True,
    )

    scheduler.start()
    _is_started = True

    print(f"\n[SCHEDULER] ===== All jobs scheduled =====")
    print(f"  1. Daily News Fetch    : 06:00 AM IST (every day)")
    print(f"  2. Daily DB Cleanup    : 05:00 AM IST (every day, deletes >5 day old news)")
    print(f"  3. Pre-Market Agent    : 08:30 AM IST (Mon-Fri, skips NSE holidays)")
    print(f"[SCHEDULER] ==================================\n")


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    global _is_started
    if _is_started:
        scheduler.shutdown(wait=False)
        _is_started = False
        print("[SCHEDULER] Shut down.")


def get_scheduler_status() -> dict:
    """Get current status of all scheduled jobs (for API/dashboard)."""
    now = datetime.now(IST)
    today = now.date()

    jobs_info = []
    if _is_started:
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.strftime("%Y-%m-%d %H:%M IST") if next_run else "None",
                "next_run_ms": int(next_run.timestamp() * 1000) if next_run else None,
            })

    return {
        "scheduler_active": _is_started,
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S IST"),
        "today_is_trading_day": is_trading_day(today),
        "today_weekday": today.strftime("%A"),
        "jobs": jobs_info,
    }
