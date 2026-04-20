"""NSE Market Calendar — handles weekends, holidays, and trading session windows.

Computes the correct news-fetch window:
  FROM: last market close day's 15:30 IST
  TO:   today's 08:30 IST

This correctly handles:
  - Weekdays (previous day 15:30 → today 08:30)
  - Mondays  (Friday 15:30 → Monday 08:30)
  - Holidays (last trading day 15:30 → next trading day 08:30)
  - Long weekends with holidays on Friday or Monday
"""

from datetime import datetime, date, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

# ── NSE Market Hours ─────────────────────────────────────────────────────────
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# Pre-market agent run time
AGENT_RUN_HOUR = 8
AGENT_RUN_MINUTE = 30

# ── NSE Holidays 2026 (update annually) ──────────────────────────────────────
# Source: NSE India official holiday list
# Format: (month, day) tuples for the current year
# These are the days when NSE is CLOSED (excluding weekends)
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 10),   # Maha Shivaratri
    date(2026, 3, 17),   # Holi
    date(2026, 3, 30),   # Id-ul-Fitr (Eid)
    date(2026, 4, 2),    # Ram Navami
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # May Day / Maharashtra Day
    date(2026, 5, 25),   # Buddha Purnima
    date(2026, 6, 5),    # Eid-ul-Adha (Bakri Id)
    date(2026, 7, 6),    # Muharram
    date(2026, 8, 15),   # Independence Day
    date(2026, 8, 16),   # Parsi New Year
    date(2026, 9, 4),    # Milad-un-Nabi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 10, 21),  # Dussehra (additional)
    date(2026, 11, 9),   # Diwali (Laxmi Puja)
    date(2026, 11, 10),  # Diwali Balipratipada
    date(2026, 11, 27),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}

# Support multiple years — add more as needed
NSE_HOLIDAYS_2025 = {
    date(2025, 1, 26),   # Republic Day
    date(2025, 2, 26),   # Maha Shivaratri
    date(2025, 3, 14),   # Holi
    date(2025, 3, 31),   # Id-ul-Fitr
    date(2025, 4, 6),    # Ram Navami
    date(2025, 4, 10),   # Mahavir Jayanti
    date(2025, 4, 14),   # Dr. Ambedkar Jayanti
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # May Day
    date(2025, 5, 12),   # Buddha Purnima
    date(2025, 6, 7),    # Eid-ul-Adha
    date(2025, 7, 6),    # Muharram
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 16),   # Parsi New Year
    date(2025, 9, 5),    # Milad-un-Nabi
    date(2025, 10, 2),   # Gandhi Jayanti
    date(2025, 10, 21),  # Dussehra
    date(2025, 10, 22),  # Diwali (Laxmi Puja)
    date(2025, 11, 5),   # Guru Nanak Jayanti
    date(2025, 12, 25),  # Christmas
}

# Combined set for all supported years
ALL_NSE_HOLIDAYS: set[date] = NSE_HOLIDAYS_2025 | NSE_HOLIDAYS_2026


def is_nse_holiday(d: date) -> bool:
    """Check if a given date is an NSE holiday."""
    return d in ALL_NSE_HOLIDAYS


def is_weekend(d: date) -> bool:
    """Check if a date is a weekend (Saturday=5, Sunday=6)."""
    return d.weekday() >= 5


def is_trading_day(d: date) -> bool:
    """Check if a given date is a valid NSE trading day (not weekend, not holiday)."""
    return not is_weekend(d) and not is_nse_holiday(d)


def get_last_trading_day(from_date: date) -> date:
    """
    Find the most recent trading day BEFORE `from_date`.
    
    Walks backwards from from_date to find the last day
    when the NSE market was open.
    
    Examples:
      - If from_date is Monday  → returns Friday (if Friday wasn't a holiday)
      - If from_date is Tuesday → returns Monday (if Monday wasn't a holiday)  
      - If from_date is Monday and Friday was a holiday → returns Thursday
    """
    d = from_date - timedelta(days=1)
    # Safety: don't go back more than 15 days (handles extreme edge cases)
    for _ in range(15):
        if is_trading_day(d):
            return d
        d -= timedelta(days=1)
    
    # Fallback: shouldn't happen, but return from_date - 1
    return from_date - timedelta(days=1)


def get_news_fetch_window(now: datetime = None) -> tuple[datetime, datetime, dict]:
    """
    Calculate the exact time window for fetching news articles.
    
    Returns:
        (from_dt, to_dt, info_dict)
        
        from_dt: Last market close time (15:30 IST on last trading day)
        to_dt:   Today's pre-market time (08:30 IST)
        info_dict: Debug info about the calculation
        
    Logic:
        - Find the last trading day before today
        - FROM = that day at 15:30 IST (market close)
        - TO   = today at 08:30 IST (agent run time)
        
    Examples:
        Tuesday 08:30 AM:
            FROM = Monday 15:30 IST
            TO   = Tuesday 08:30 IST
            Window = ~17 hours
            
        Monday 08:30 AM:
            FROM = Friday 15:30 IST
            TO   = Monday 08:30 IST
            Window = ~65 hours
            
        Monday 08:30 AM (Friday was holiday):
            FROM = Thursday 15:30 IST
            TO   = Monday 08:30 IST
            Window = ~89 hours
    """
    if now is None:
        now = datetime.now(IST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    
    today = now.date()
    
    # Find the last trading day
    last_trade_day = get_last_trading_day(today)
    
    # FROM: last trading day at market close (15:30 IST)
    from_dt = datetime(
        last_trade_day.year, last_trade_day.month, last_trade_day.day,
        MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE, 0,
        tzinfo=IST,
    )
    
    # TO: today at agent run time (08:30 IST)
    to_dt = datetime(
        today.year, today.month, today.day,
        AGENT_RUN_HOUR, AGENT_RUN_MINUTE, 0,
        tzinfo=IST,
    )
    
    # Calculate the window in hours
    window_hours = (to_dt - from_dt).total_seconds() / 3600
    
    # Count how many non-trading days are in between
    gap_days = (today - last_trade_day).days
    non_trading_days = []
    for i in range(1, gap_days):
        d = last_trade_day + timedelta(days=i)
        if is_weekend(d):
            non_trading_days.append(f"{d} (weekend)")
        elif is_nse_holiday(d):
            non_trading_days.append(f"{d} (holiday)")
    
    info = {
        "today": str(today),
        "today_is_trading_day": is_trading_day(today),
        "today_weekday": today.strftime("%A"),
        "last_trading_day": str(last_trade_day),
        "last_trading_day_weekday": last_trade_day.strftime("%A"),
        "gap_calendar_days": gap_days,
        "non_trading_days_between": non_trading_days,
        "window_hours": round(window_hours, 1),
        "from_time": from_dt.strftime("%Y-%m-%d %H:%M IST"),
        "to_time": to_dt.strftime("%Y-%m-%d %H:%M IST"),
    }
    
    return from_dt, to_dt, info


def get_hours_back_for_news() -> float:
    """
    Convenience function: returns the number of hours to look back
    for news articles from right now.
    
    This replaces the hardcoded hours_back=18.0 or hours_back=48.0
    with a dynamically calculated value.
    """
    from_dt, to_dt, info = get_news_fetch_window()
    now = datetime.now(IST)
    
    # Calculate hours from `from_dt` to `now` (not to_dt, since we want
    # articles up to the current moment)
    hours_back = (now - from_dt).total_seconds() / 3600
    
    # Add a 1-hour buffer for safety (articles published slightly before close)
    hours_back += 1.0
    
    print(f"[CALENDAR] News window: {info['from_time']} -> now")
    print(f"   Last trading day: {info['last_trading_day']} ({info['last_trading_day_weekday']})")
    print(f"   Today: {info['today']} ({info['today_weekday']})")
    print(f"   Gap: {info['gap_calendar_days']} calendar days")
    if info['non_trading_days_between']:
        print(f"   Non-trading days in between: {', '.join(info['non_trading_days_between'])}")
    print(f"   Looking back: {round(hours_back, 1)} hours")
    
    return hours_back


# ── Quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Market Calendar Self-Test ===\n")
    
    # Test current
    hours = get_hours_back_for_news()
    print(f"\nResult: fetch news from {round(hours, 1)} hours ago\n")
    
    # Test specific scenarios
    test_cases = [
        ("Normal Tuesday", datetime(2026, 4, 21, 8, 30, tzinfo=IST)),   # Tue
        ("Normal Wednesday", datetime(2026, 4, 22, 8, 30, tzinfo=IST)), # Wed
        ("Monday (weekend gap)", datetime(2026, 4, 20, 8, 30, tzinfo=IST)),  # Mon
        ("After Eid holiday (Thu)", datetime(2026, 6, 6, 8, 30, tzinfo=IST)),  # Fri after Eid
    ]
    
    for label, test_dt in test_cases:
        from_dt, to_dt, info = get_news_fetch_window(test_dt)
        print(f"--- {label} ({test_dt.strftime('%A %Y-%m-%d')}) ---")
        print(f"  Window: {info['from_time']} -> {info['to_time']}")
        print(f"  Hours: {info['window_hours']}")
        print(f"  Last trading day: {info['last_trading_day']} ({info['last_trading_day_weekday']})")
        if info['non_trading_days_between']:
            print(f"  Non-trading days: {', '.join(info['non_trading_days_between'])}")
        print()
