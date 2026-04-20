"""Data collector — fetches news articles and stock prices for the agent."""

import time
import json
import traceback
import httpx
from datetime import datetime
from sqlalchemy.orm import Session

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
                affected_symbols=item.get("affected_symbols", []),
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
    Fetch live stock price data for a list of symbols via Groww API.
    Returns dict mapping symbol -> stock data dict.
    """
    results = {}
    for sym in symbols:
        try:
            data = get_accurate_stock_data(sym)
            if data and not data.get("error"):
                results[sym] = data
            else:
                print(f"  [WARN] No data for {sym}: {data.get('error', 'unknown error')}")
        except Exception as e:
            print(f"  [WARN] Failed to fetch {sym}: {e}")
    return results
