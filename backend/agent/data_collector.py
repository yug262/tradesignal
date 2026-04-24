"""Data collector — fetches news articles and stock prices for the agent."""

import time
import json
import traceback
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
import numpy as np
try:
    import talib
except ImportError:
    talib = None

import db_models
from routers.stocks import get_accurate_stock_data
from agent.market_calendar import get_news_fetch_window, get_hours_back_for_news, IST


def fetch_recent_news(db: Session, hours_back: float = None) -> dict[str, list[dict]]:
    """
    Fetch news articles from DB published since last market close.
    
    Uses the NSE market calendar to dynamically calculate the correct window:
      - Weekday: previous day 15:30 IST → today (e.g., ~17 hours)
      - Monday:  Friday 15:30 IST → Monday (e.g., ~65 hours)
      - After holiday: last trading day 15:30 IST → today
    
    If hours_back is explicitly provided, it overrides the smart calculation.
    
    Groups articles by affected_symbols.
    Returns: dict mapping symbol -> list of article dicts.
    """
    if hours_back is None:
        # Smart calculation based on market calendar
        hours_back = get_hours_back_for_news()
    else:
        print(f"[DATA] Using manual hours_back override: {hours_back}h")
    
    cutoff_ms = int((time.time() - hours_back * 3600) * 1000)

    articles = (
        db.query(db_models.NewsArticle)
        .filter(db_models.NewsArticle.published_at >= cutoff_ms)
        .filter(db_models.NewsArticle.impact_score >= 5.0)
        .order_by(db_models.NewsArticle.published_at.desc())
        .all()
    )

    grouped: dict[str, list[dict]] = {}
    
    # Common NSE Symbol mapping for fallback extraction
    SYMBOL_MAP = {
        "RELIANCE": ["RELIANCE"],
        "HDFC": ["HDFCBANK", "HDFCLIFE"],
        "ICICI": ["ICICIBANK"],
        "INFOSYS": ["INFY"],
        "TCS": ["TCS"],
        "WIPRO": ["WIPRO"],
        "TATA MOTORS": ["TATAMOTORS"],
        "TATA STEEL": ["TATASTEEL"],
        "SBI ": ["SBIN"],
        "ADANI": ["ADANIENT", "ADANIPORTS"],
        "BHARTI AIRTEL": ["BHARTIARTL"],
        "ITC": ["ITC"],
        "MARUTI": ["MARUTI"],
        "ULTRATECH": ["ULTRACEMCO"],
        "UNITED BREWERIES": ["UBL"],
        "AXIS BANK": ["AXISBANK"],
        "KOTAK": ["KOTAKBANK"],
        "ASIAN PAINTS": ["ASIANPAINT"],
        "LARSEN": ["LT"],
        "BAJAJ": ["BAJFINANCE", "BAJAJFINSV"],
        "TITAN": ["TITAN"],
        "SUN PHARMA": ["SUNPHARMA"],
        "MAHINDRA": ["M&M"],
        "JSW STEEL": ["JSWSTEEL"],
        "POWER GRID": ["POWERGRID"],
        "NTPC": ["NTPC"],
        "COAL INDIA": ["COALINDIA"],
    }

    for a in articles:
        data = {
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "source": a.source,
            "published_at": a.published_at,
            "analyzed_at": a.analyzed_at,
            "impact_score": a.impact_score,
            "impact_summary": a.impact_summary,
            "executive_summary": a.executive_summary,
            "news_category": a.news_category,
            "news_relevance": a.news_relevance,
            "affected_symbols": a.affected_symbols,
            "raw_analysis_data": a.raw_analysis_data,
            "processing_status": a.processing_status,
        }

        symbols = a.affected_symbols if a.affected_symbols else []
        
        # Fallback: Extract from title if empty
        if not symbols:
            title_upper = a.title.upper()
            for keyword, sym_list in SYMBOL_MAP.items():
                if keyword in title_upper:
                    symbols.extend(sym_list)
            
            if not symbols:
                # Still no symbols? Maybe it's a general market event.
                symbols = ["GENERAL"]

        for sym in set(symbols): # Use set to avoid duplicates
            if sym and sym != "GENERAL":
                grouped.setdefault(sym, []).append(data)

    return grouped


def _parse_ms(val) -> int:
    """Safely parse a value into an integer representing milliseconds."""
    fallback = int(time.time() * 1000)
    if not val:
        return fallback
    if isinstance(val, (int, float)):
        return int(val) if val > 0 else fallback
    if isinstance(val, str):
        try:
            if val.isdigit():
                parsed = int(val)
                return parsed if parsed > 0 else fallback
            from datetime import datetime
            # Attempt to parse ISO string
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except Exception:
            return fallback
    return fallback


def trigger_news_fetch(news_endpoint_url: str, db: Session) -> int:
    """
    Pull fresh news from the external endpoint and save new articles to DB.
    
    Stores ALL articles regardless of impact score — filtering happens later
    during the agent analysis pipeline. This ensures we never miss news that
    might become relevant.
    
    Returns count of new articles saved.
    """
    # Headers for ngrok endpoints
    headers = {
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "ATS-NewsCollector/2.0",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=60.0, headers=headers, follow_redirects=True) as client:
            print(f"  [FETCH] Requesting: {news_endpoint_url[:80]}...")
            response = client.get(news_endpoint_url)
            response.raise_for_status()
            json_res = response.json()

        # Handle various API response formats
        articles_list = (
            json_res if isinstance(json_res, list)
            else json_res.get("data", json_res.get("items", json_res.get("articles", [])))
        )

        if not isinstance(articles_list, list):
            print(f"  [WARN] Unexpected response format: {type(articles_list)}")
            return 0

        print(f"  [FETCH] Received {len(articles_list)} articles from endpoint")

        saved = 0
        skipped_existing = 0
        skipped_invalid = 0

        for item in articles_list:
            if not isinstance(item, dict):
                skipped_invalid += 1
                continue

            item_id = str(item.get("id", ""))
            if not item_id or item_id == "None":
                skipped_invalid += 1
                continue

            # Check if already exists
            existing = (
                db.query(db_models.NewsArticle)
                .filter(db_models.NewsArticle.id == item_id)
                .first()
            )
            if existing:
                skipped_existing += 1
                continue

            # Parse impact score and strictly filter out low-impact news
            raw_impact = item.get("impact_score")
            impact = float(raw_impact) if raw_impact is not None else 0.0
            
            if impact < 5.0:
                skipped_invalid += 1
                continue

            raw_stocks = item.get("affected_stocks", [])
            symbols_list = []
            if isinstance(raw_stocks, dict):
                symbols_list.extend(raw_stocks.get("direct", []))
                symbols_list.extend(raw_stocks.get("indirect", []))
            elif isinstance(raw_stocks, list):
                symbols_list.extend(raw_stocks)

            final_symbols = item.get("affected_symbols", symbols_list)
            if not isinstance(final_symbols, list):
                final_symbols = []

            new_art = db_models.NewsArticle(
                id=item_id,
                title=item.get("title", "No Title"),
                description=item.get("description", ""),
                source=item.get("source", "Unknown"),
                published_at=_parse_ms(item.get("published_at")),
                analyzed_at=_parse_ms(item.get("analyzed_at")),
                impact_score=impact,
                impact_summary=item.get("impact_summary", ""),
                executive_summary=item.get("executive_summary", ""),
                news_category=item.get("news_category", ""),
                news_relevance=item.get("news_relevance", ""),
                affected_symbols=final_symbols,
                raw_analysis_data=item.get("raw_analysis_data", {}),
                processing_status=item.get("processing_status", "analyzed"),
            )
            db.add(new_art)
            saved += 1

        db.commit()
        print(f"  [FETCH] Result: {saved} new | {skipped_existing} already exist | {skipped_invalid} invalid")
        return saved

    except httpx.ConnectError as e:
        print(f"  [WARN] News endpoint unreachable (connection error): {e}")
        return 0
    except httpx.TimeoutException as e:
        print(f"  [WARN] News endpoint timed out: {e}")
        return 0
    except httpx.HTTPStatusError as e:
        print(f"  [WARN] News endpoint returned error {e.response.status_code}: {e}")
        return 0
    except Exception as e:
        print(f"  [WARN] News fetch failed: {e}")
        traceback.print_exc()
        return 0


def fetch_stock_data_for_symbols(symbols: list[str]) -> dict[str, dict]:
    """
    Fetch rich market context for a list of symbols via Groww API.
    
    For each symbol, returns:
      - Basic price data (close, open, high, low, volume, 52-week range)
      - Historical averages (5d/20d volume)
      - Multi-period returns (1d, 5d, 20d)
      - Trend classification (up/down/sideways/mixed)
      - Distance from 20-day high/low
    """
    results = {}
    for sym in symbols:
        try:
            data = _fetch_rich_stock_data(sym)
            if data and not data.get("error"):
                results[sym] = data
            else:
                print(f"  [WARN] No data for {sym}: {data.get('error', 'unknown error')}")
        except Exception as e:
            print(f"  [WARN] Failed to fetch {sym}: {e}")
    return results


def _fetch_rich_stock_data(symbol: str) -> dict:
    """
    Fetch comprehensive market context for a single symbol.
    Uses Groww's live price API + charting API for historical candles.
    """
    import httpx

    clean = symbol.replace(".NS", "")
    data = {
        "symbol": clean,
        "company_name": clean,
        # Basic price data
        "previous_close": None,
        "last_close": None,
        "today_open": None,
        "today_high": None,
        "today_low": None,
        "gap_percentage": None,
        "52_week_high": None,
        "52_week_low": None,
        "current_volume": None,
        "current_change_pct": None,
        "current_change_amount": None,
        # Previous day candle
        "prev_day_open": None,
        "prev_day_high": None,
        "prev_day_low": None,
        "prev_day_volume": None,
        # Historical averages
        "avg_volume_5d": None,
        "avg_volume_20d": None,
        # Multi-period returns
        "change_1d_percent": None,
        "change_5d_percent": None,
        "change_20d_percent": None,
        # Trend & relative position
        "recent_trend": None,
        "distance_from_20d_high_percent": None,
        "distance_from_20d_low_percent": None,
        # Error
        "error": None,
    }

    if clean == "GENERAL":
        return data

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    with httpx.Client(timeout=10.0) as client:
        try:
            # ── 1. Live price data ──────────────────────────────────────
            live_url = (
                f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/"
                f"exchange/NSE/segment/CASH/{clean}/latest"
            )
            live_res = client.get(live_url, headers=headers)

            if live_res.status_code != 200:
                data["error"] = f"Live API HTTP {live_res.status_code}"
                return data

            live = live_res.json()
            pc = live.get("close")
            o = live.get("open")

            data["previous_close"] = pc
            data["last_close"] = pc
            data["today_open"] = o
            data["today_high"] = live.get("high")
            data["today_low"] = live.get("low")
            data["52_week_high"] = live.get("yearHighPrice")
            data["52_week_low"] = live.get("yearLowPrice")
            data["current_volume"] = live.get("volume")
            data["current_change_pct"] = live.get("dayChangePerc")
            data["current_change_amount"] = live.get("dayChange")
            data["change_1d_percent"] = live.get("dayChangePerc")

            if o is not None and pc is not None and pc != 0:
                data["gap_percentage"] = round(((o - pc) / pc) * 100, 2)

            # ── 2. Historical candles (daily, 30 days back) ─────────────
            end_ms = int(time.time() * 1000)
            start_ms = end_ms - (86400 * 35 * 1000)  # 35 days to ensure 20+ trading days

            chart_url = (
                f"https://groww.in/v1/api/charting_service/v2/chart/"
                f"exchange/NSE/segment/CASH/{clean}"
                f"?intervalInMinutes=1440&minimal=false"
                f"&startTimeInMillis={start_ms}&endTimeInMillis={end_ms}"
            )
            chart_res = client.get(chart_url, headers=headers)

            if chart_res.status_code == 200:
                candles = chart_res.json().get("candles", [])
                # Candle format: [timestamp, open, high, low, close, volume]

                if len(candles) >= 2:
                    # Previous day candle (second-to-last is yesterday)
                    prev = candles[-2]
                    data["prev_day_open"] = prev[1]
                    data["prev_day_high"] = prev[2]
                    data["prev_day_low"] = prev[3]
                    data["prev_day_volume"] = prev[5] if len(prev) > 5 else None

                    # ── Volume averages ──────────────────────────────
                    volumes = [c[5] for c in candles if len(c) > 5 and c[5]]
                    if len(volumes) >= 5:
                        data["avg_volume_5d"] = int(sum(volumes[-5:]) / 5)
                    if len(volumes) >= 20:
                        data["avg_volume_20d"] = int(sum(volumes[-20:]) / 20)
                    elif len(volumes) >= 5:
                        data["avg_volume_20d"] = int(sum(volumes) / len(volumes))

                    # ── Multi-period returns ─────────────────────────
                    closes = [c[4] for c in candles if len(c) > 4 and c[4]]
                    if closes and pc:
                        if len(closes) >= 5:
                            close_5d_ago = closes[-5]
                            data["change_5d_percent"] = round(
                                ((pc - close_5d_ago) / close_5d_ago) * 100, 2
                            )
                        if len(closes) >= 20:
                            close_20d_ago = closes[-20]
                            data["change_20d_percent"] = round(
                                ((pc - close_20d_ago) / close_20d_ago) * 100, 2
                            )

                    # ── 20-day high/low distance ─────────────────────
                    recent_20 = candles[-20:] if len(candles) >= 20 else candles
                    highs_20d = [c[2] for c in recent_20 if len(c) > 2 and c[2]]
                    lows_20d = [c[3] for c in recent_20 if len(c) > 3 and c[3]]

                    if highs_20d and pc:
                        high_20d = max(highs_20d)
                        data["distance_from_20d_high_percent"] = round(
                            ((pc - high_20d) / high_20d) * 100, 2
                        )
                    if lows_20d and pc:
                        low_20d = min(lows_20d)
                        data["distance_from_20d_low_percent"] = round(
                            ((pc - low_20d) / low_20d) * 100, 2
                        )

                    # ── Trend classification ─────────────────────────
                    if closes and len(closes) >= 5:
                        c5 = data.get("change_5d_percent") or 0
                        c20 = data.get("change_20d_percent") or 0

                        if c5 > 2 and c20 > 3:
                            data["recent_trend"] = "up"
                        elif c5 < -2 and c20 < -3:
                            data["recent_trend"] = "down"
                        elif abs(c5) <= 2 and abs(c20) <= 3:
                            data["recent_trend"] = "sideways"
                        else:
                            data["recent_trend"] = "mixed"

        except Exception as e:
            data["error"] = str(e)

    return data


def _fetch_raw_candles(symbol: str, interval: int, count: int = 50) -> list:
    """Internal helper to fetch raw candles from Groww."""
    clean = symbol.replace(".NS", "").strip().upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    now_ms = int(time.time() * 1000)
    # Provide enough buffer to ensure we get 'count' candles even across weekends/holidays
    # 1440m (Daily) -> 1 day per candle. 50 candles = 50 trading days. Need ~70 calendar days.
    # 1m (Intraday) -> 1 min per candle. 50 candles = 50 mins. Need a few hours if near open.
    if interval == 1440:
        start_ms = now_ms - (86400 * count * 1.5 * 1000) 
    else:
        start_ms = now_ms - (60 * count * 5 * 1000) # 5x buffer for intraday gaps

    chart_url = (
        f"https://groww.in/v1/api/charting_service/v2/chart/"
        f"exchange/NSE/segment/CASH/{clean}"
        f"?intervalInMinutes={interval}&minimal=false"
        f"&startTimeInMillis={int(start_ms)}&endTimeInMillis={now_ms}"
    )
    
    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            res = client.get(chart_url)
            if res.status_code == 200:
                candles = res.json().get("candles", [])
                return candles[-count:] if len(candles) > count else candles
    except Exception as e:
        print(f"  [ERROR] Candle fetch failed for {symbol}: {e}")
    return []


def fetch_indicator_data(db: Session, symbol: str, trade_mode: str, indicator_name: str, timeframe: str = None) -> list:
    """
    Fetch last 20 candle data and calculate the specified TA-Lib indicator.
    
    Args:
        db: SQLAlchemy session
        symbol: NSE stock symbol
        trade_mode: INTRADAY or DELIVERY (used as fallback if timeframe not specified)
        indicator_name: TA-Lib indicator name (RSI, EMA, ATR, etc.)
        timeframe: Explicit timeframe override: '1m', '5m', '15m', '1D'
                   If None, falls back to trade_mode (DELIVERY->1D, INTRADAY->1m)
    
    Saves the results to DBIndicatorData.
    Returns list of {timestamp, value} dicts (last 20 valid values).
    """
    if talib is None:
        print("  [WARN] TA-Lib is not installed. Returning empty indicator data safely.")
        return []

    # 1. Determine timeframe from explicit param or trade_mode fallback
    TIMEFRAME_MAP = {"1m": 1, "5m": 5, "15m": 15, "1D": 1440}
    if timeframe and timeframe in TIMEFRAME_MAP:
        interval = TIMEFRAME_MAP[timeframe]
        tf_str = timeframe
    else:
        interval = 1440 if trade_mode.upper() == "DELIVERY" else 1
        tf_str = "1D" if interval == 1440 else "1m"
    
    print(f"  [INDICATOR] Fetching {indicator_name} for {symbol} ({tf_str})...")

    # 2. Fetch candles
    # We need more than 20 candles to calculate indicators accurately for the target 20 bars.
    # For many indicators (like RSI 14), we need at least period+1 bars. 
    # Fetching 60 candles to be safe and return the last 20.
    candles = _fetch_raw_candles(symbol, interval, count=60)
    if not candles or len(candles) < 20:
        print(f"  [WARN] Not enough candle data for {symbol} to calculate indicator.")
        return []

    # 3. Prepare data for TA-Lib (numpy arrays)
    # Candle format: [timestamp, open, high, low, close, volume]
    try:
        highs = np.array([float(c[2]) for c in candles])
        lows = np.array([float(c[3]) for c in candles])
        closes = np.array([float(c[4]) for c in candles])
        timestamps = [c[0] for c in candles]
    except (IndexError, ValueError) as e:
        print(f"  [ERROR] Data parsing error for {symbol}: {e}")
        return []

    # 4. Execute TA-Lib indicator
    try:
        func = getattr(talib, indicator_name.upper())
        # Most common indicators take (close) or (high, low, close)
        # We attempt to call with appropriate parameters based on the indicator name
        if indicator_name.upper() in ["RSI", "SMA", "EMA", "WMA", "MOM", "ROC", "TRIX"]:
            result = func(closes)
        elif indicator_name.upper() in ["ATR", "NATR", "TRANGE", "CCI", "WILLR"]:
            result = func(highs, lows, closes)
        elif indicator_name.upper() in ["MACD"]:
            macd, signal, hist = func(closes)
            result = macd # Store the main MACD line; could be expanded to store all
        elif indicator_name.upper() in ["BBANDS"]:
            upper, middle, lower = func(closes)
            result = middle
        else:
            # Fallback: try with closes
            result = func(closes)
    except AttributeError:
        print(f"  [ERROR] Indicator '{indicator_name}' not found in TA-Lib.")
        return []
    except Exception as e:
        print(f"  [ERROR] TA-Lib execution failed for {indicator_name}: {e}")
        return []

    if result is None:
        return []

    # 5. Extract last 20 values and save to DB
    now_ms = int(time.time() * 1000)
    output = []

    if isinstance(result, tuple):
        result = result[0]

    # We iterate backwards from the end to get the last 20 valid points
    valid_points = []
    for i in range(len(result) - 1, -1, -1):
        val = result[i]
        if not np.isnan(val):
            valid_points.append((timestamps[i], float(val)))
        if len(valid_points) >= 20:
            break
    
    # Reverse to keep chronological order
    valid_points.reverse()
    
    if not valid_points:
        return []

    # Prepare arrays for DB storage
    ts_array = [p[0] for p in valid_points]
    val_array = [p[1] for p in valid_points]

    try:
        # Check if already exists to update, or create new
        existing = db.query(db_models.DBIndicatorData).filter(
            db_models.DBIndicatorData.symbol == symbol,
            db_models.DBIndicatorData.indicator_name == indicator_name.upper(),
            db_models.DBIndicatorData.timeframe == tf_str
        ).first()

        if existing:
            existing.timestamps = ts_array
            existing.values = val_array
            existing.updated_at = now_ms
        else:
            new_entry = db_models.DBIndicatorData(
                symbol=symbol,
                indicator_name=indicator_name.upper(),
                timeframe=tf_str,
                timestamps=ts_array,
                values=val_array,
                updated_at=now_ms
            )
            db.add(new_entry)
        
        db.commit()
        print(f"  [OK] Calculated {indicator_name} for {symbol}. Saved array of {len(val_array)} points.")
    except Exception as e:
        print(f"  [ERROR] Database error for {symbol} array storage: {e}")
        db.rollback()

    # Still return the same output format for the caller
    return [{"timestamp": ts, "value": val} for ts, val in valid_points]