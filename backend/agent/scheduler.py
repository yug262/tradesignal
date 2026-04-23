"""Scheduler — orchestrates all automated jobs for the trading system.

Four-layer pipeline (scheduled):
  Layer 1 — Discovery Agent (Agent 1)        : 08:30 AM IST (Mon-Fri trading days)
  Layer 2 — Market Open Confirmation (Agent 2): 09:20 AM IST (Mon-Fri trading days)
  Layer 3 — Execution Planner (Agent 3)      : triggered manually or via API
  Layer 4 — Risk Monitor (Agent 4)           : every 30s during market hours (09:16-15:30)

Support jobs (every day):
  DB Cleanup        : 05:00 AM IST — delete news >5 days old, signals >30 days old
  Pre-market Fetch  : 08:28 AM IST — pull fresh news before Agent 1 runs

Uses APScheduler with CronTriggers + IntervalTriggers. Started/stopped with FastAPI lifecycle.
"""

import time
import traceback
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from database import SessionLocal
from agent.market_calendar import is_trading_day, IST

IST_TZ = pytz.timezone("Asia/Kolkata")

scheduler = BackgroundScheduler(timezone=IST_TZ)
_is_started = False


# ═══════════════════════════════════════════════════════════════════════════════
# JOB 1: DB Cleanup -- delete news older than 5 days (every day 05:00 AM IST)
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
# JOB 2: Pre-Market News Fetch (every day 08:28 AM IST)
# ═══════════════════════════════════════════════════════════════════════════════

def _pre_market_news_fetch_job():
    """
    Fetch the freshest news right before Agent 1 runs.
    Runs EVERY DAY at 8:28 AM IST (2 minutes before the pre-market agent)
    so Agent 1 always has the most up-to-date news to analyze.
    """
    from store import _get_store
    from agent.data_collector import trigger_news_fetch

    now = datetime.now(IST)
    print(f"\n{'='*60}")
    print(f"[SCHEDULER] PRE-MARKET NEWS FETCH -- {now.strftime('%Y-%m-%d %H:%M IST (%A)')}")
    print(f"{'='*60}")

    db = SessionLocal()
    try:
        config = _get_store().config

        endpoint_url = config.news_endpoint_url
        if not endpoint_url:
            print("[SCHEDULER] No news endpoint URL configured -- skipping")
            return

        print(f"[SCHEDULER] Fetching from: {endpoint_url[:80]}...")
        new_count = trigger_news_fetch(endpoint_url, db)
        print(f"[SCHEDULER] Done! Saved {new_count} new articles to DB")

    except Exception as e:
        print(f"[SCHEDULER] Pre-market news fetch FAILED: {e}")
        traceback.print_exc()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# JOB 3: Pre-Market Agent (trading days at 08:30 AM IST)
# ═══════════════════════════════════════════════════════════════════════════════

def _pre_market_agent_job():
    """
    Discovery Agent pipeline (Agent 1).
    Only runs on TRADING DAYS (skips weekends and NSE holidays).

    Pipeline:
      1. Check if today is a trading day
      2. Fetch fresh news from endpoint (last market close -> now)
      3. Group news by affected symbols
      4. Fetch stock company context
      5. Run Gemini Discovery analysis on each symbol
      6. Save WATCH / NO_TRADE assessments (status: pending_confirmation)
    """
    from agent.signal_generator import run_full_analysis

    now = datetime.now(IST)
    today = now.date()

    print(f"\n{'='*60}")
    print(f"[SCHEDULER] PRE-MARKET AGENT (Agent 1) -- {now.strftime('%Y-%m-%d %H:%M IST (%A)')}")
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
            f"\n[SCHEDULER] Agent 1 (Discovery) COMPLETE! "
            f"Analyzed {total} symbols -> "
            f"WATCH: {s.get('watch', 0)}, IGNORE: {s.get('ignore', 0)}, "
            f"NOISE: {s.get('stale', 0)} "
            f"({duration}ms)"
        )
        print(f"[SCHEDULER] Assessments are PENDING CONFIRMATION — Agent 2 will run at 09:20 AM")
    except Exception as e:
        print(f"[SCHEDULER] Agent 1 FAILED: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════════════
# JOB 4: Market Open Confirmation Agent (trading days at 09:20 AM IST)
# ═══════════════════════════════════════════════════════════════════════════════

def _market_open_confirmation_job():
    """
    Market Open Confirmation Agent (Agent 2).
    Runs at 09:20 AM IST — 5 minutes after NSE market open.
    Only runs on TRADING DAYS.

    Pipeline:
      1. Check if today is a trading day
      2. Query all pending_confirmation (WATCH) signals from Agent 1 Discovery
      3. Fetch LIVE market-open data (price, volume, gap, move quality)
      4. Build Agent 2 input from Discovery output + live context
      5. Run Gemini confirmation analysis on each signal
      6. Update signals: CONFIRMED (TRADE) / INVALIDATED (NO TRADE)
    """
    from agent.confirmation_agent import run_market_open_confirmation

    now = datetime.now(IST)
    today = now.date()

    print(f"\n{'='*60}")
    print(f"[SCHEDULER] MARKET OPEN CONFIRMATION (Agent 2) -- {now.strftime('%Y-%m-%d %H:%M IST (%A)')}")
    print(f"{'='*60}")

    # Check if today is a trading day
    if not is_trading_day(today):
        reason = "weekend" if today.weekday() >= 5 else "NSE holiday"
        print(f"[SCHEDULER] Today is NOT a trading day ({reason}) -- skipping confirmation")
        return

    print(f"[SCHEDULER] Market opened at 09:15 — running confirmation with live data...")

    try:
        result = run_market_open_confirmation()
        total = result.get("total_checked", 0)
        s = result.get("summary", {})
        duration = result.get("duration_ms", 0)
        print(
            f"\n[SCHEDULER] Agent 2 COMPLETE! "
            f"Checked {total} signals -> "
            f"CONFIRMED: {s.get('confirmed', 0)}, "
            f"REVISED: {s.get('revised', 0)}, "
            f"INVALIDATED: {s.get('invalidated', 0)} "
            f"({duration}ms)"
        )
    except Exception as e:
        print(f"[SCHEDULER] Agent 2 FAILED: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════════════
# JOB 5: Risk Monitor Agent (every 30s during market hours)
# ═══════════════════════════════════════════════════════════════════════════════

def _risk_monitor_job():
    """
    Live Risk Monitor Agent (Agent 4).
    Runs every 30 seconds during market hours (09:16 - 15:30 IST).
    Only processes trades that exist and are in 'planned' status.

    The risk monitor itself handles:
      - Market hours check (skips if market closed)
      - Per-trade throttling (won't re-check a trade within 25s)
      - Error isolation (one trade failure doesn't crash others)
    """
    from agent.risk_monitor import run_risk_monitor

    now = datetime.now(IST)

    # Quick guard: skip weekends and non-market hours at scheduler level
    if now.weekday() >= 5:
        return
    hhmm = now.hour * 100 + now.minute
    if hhmm < 916 or hhmm > 1530:
        return

    try:
        result = run_risk_monitor()
        status = result.get("status", "unknown")
        total = result.get("total_monitored", 0)
        if status == "completed" and total > 0:
            summary = result.get("summary", {})
            print(
                f"[RISK MONITOR] {now.strftime('%H:%M:%S')} | "
                f"{total} trades | "
                f"HOLD:{summary.get('hold', 0)} "
                f"TIGHTEN:{summary.get('tighten_stoploss', 0)} "
                f"PARTIAL:{summary.get('partial_exit', 0)} "
                f"EXIT:{summary.get('exit_now', 0)} "
                f"({result.get('duration_ms', 0)}ms)"
            )
    except Exception as e:
        print(f"[RISK MONITOR] Error: {e}")


def _paper_trade_monitor_job():
    """Job 6: Monitor open paper trades — check SL/target and auto-close."""
    from agent.paper_trading_engine import monitor_open_positions
    try:
        result = monitor_open_positions()
        actions = result.get("actions_taken", 0)
        if actions > 0:
            print(f"[PAPER TRADE MONITOR] {actions} position(s) auto-closed")
    except Exception as e:
        print(f"[PAPER TRADE MONITOR] Error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Scheduler Init / Shutdown
# ═══════════════════════════════════════════════════════════════════════════════

def init_scheduler():
    """Initialize and start all scheduled jobs."""
    global _is_started

    if _is_started:
        return

    # ── JOB 1: DB cleanup at 05:00 AM IST (every day) ────────────────────
    scheduler.add_job(
        _daily_cleanup_job,
        trigger=CronTrigger(hour=5, minute=0, timezone=IST_TZ),
        id="daily_db_cleanup",
        name="Daily DB Cleanup (05:00 AM IST)",
        replace_existing=True,
    )

    # ── JOB 2: Pre-market news fetch at 08:28 AM IST (every day) ─────────
    scheduler.add_job(
        _pre_market_news_fetch_job,
        trigger=CronTrigger(hour=8, minute=28, timezone=IST_TZ),
        id="pre_market_news_fetch",
        name="Pre-Market News Fetch (08:28 AM IST)",
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

    # ── JOB 4: Market open confirmation at 09:20 AM IST (Mon-Fri) ────────
    # Runs 5 minutes after NSE opens (09:15). By 09:20, we have the
    # opening candle: open price, volume surge, gap direction, 5-min high/low.
    scheduler.add_job(
        _market_open_confirmation_job,
        trigger=CronTrigger(hour=9, minute=16, day_of_week="mon-fri", timezone=IST_TZ),
        id="market_open_confirmation",
        name="Market Open Confirmation Agent (09:16 AM IST)",
        replace_existing=True,
    )

    # ── JOB 5: Risk Monitor (every 30s during market hours) ────────────
    scheduler.add_job(
        _risk_monitor_job,
        trigger=IntervalTrigger(seconds=30, timezone=IST_TZ),
        id="risk_monitor",
        name="Risk Monitor Agent (every 30s, market hours)",
        replace_existing=True,
    )

    # ── JOB 6: Paper Trade Monitor (every 15s during market hours) ────
    scheduler.add_job(
        _paper_trade_monitor_job,
        trigger=IntervalTrigger(seconds=15, timezone=IST_TZ),
        id="paper_trade_monitor",
        name="Paper Trade Position Monitor (every 15s, market hours)",
        replace_existing=True,
    )

    scheduler.start()
    _is_started = True

    print(f"[SCHEDULER] ===== All jobs scheduled =====")
    print(f"  1. Daily DB Cleanup              : 05:00 AM IST (every day)")
    print(f"  2. Pre-Market News Fetch         : 08:28 AM IST (every day)")
    print(f"  3. Discovery Agent (Agent 1)     : 08:30 AM IST (Mon-Fri trading days)")
    print(f"  4. Market Open Confirm (Agent 2) : 09:16 AM IST (Mon-Fri trading days)")
    print(f"  5. Risk Monitor (Agent 4)        : every 30s (09:16-15:30 Mon-Fri)")
    print(f"  6. Paper Trade Monitor           : every 15s (09:16-15:30 Mon-Fri)")
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
