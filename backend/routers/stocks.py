import time
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import db_models
from database import get_db

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

def get_accurate_stock_data(symbol: str):
    # If the symbol has .NS, remove it for Groww API
    clean_symbol = symbol.replace(".NS", "")
    
    data = {
        "symbol": clean_symbol,
        "last_close": None,
        "today_open": None,
        "gap_percentage": None,
        "today_high": None,
        "today_low": None,
        "52_week_high": None,
        "52_week_low": None,
        "past_day_high": None,
        "past_day_low": None,
        "current_volume": None,
        "current_change_pct": None,
        "current_change_amount": None,
        "error": None
    }
    
    if clean_symbol == "GENERAL":
        return data

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    with httpx.Client(timeout=10.0) as client:
        try:
            # 1. Fetch live accurate data (Today's Data & 52-Week Data)
            live_url = f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/exchange/NSE/segment/CASH/{clean_symbol}/latest"
            live_res = client.get(live_url, headers=headers)
            
            if live_res.status_code == 200:
                live_json = live_res.json()
                
                pc = live_json.get("close")
                o = live_json.get("open")
                
                data["last_close"] = pc
                data["today_open"] = o
                data["today_high"] = live_json.get("high")
                data["today_low"] = live_json.get("low")
                data["52_week_high"] = live_json.get("yearHighPrice")
                data["52_week_low"] = live_json.get("yearLowPrice")
                data["current_volume"] = live_json.get("volume")
                data["current_change_pct"] = live_json.get("dayChangePerc")
                data["current_change_amount"] = live_json.get("dayChange")
                
                if o is not None and pc is not None and pc != 0:
                    data["gap_percentage"] = ((o - pc) / pc) * 100
            else:
                data["error"] = f"Failed to fetch live data (HTTP {live_res.status_code})"
                return data
                
            # 2. Fetch Historical Candles for Past Day High/Low
            end_time = int(time.time() * 1000)
            start_time = end_time - (86400 * 5 * 1000) # 5 days ago to ensure we catch previous day
            
            chart_url = f"https://groww.in/v1/api/charting_service/v2/chart/exchange/NSE/segment/CASH/{clean_symbol}?intervalInMinutes=1440&minimal=false&startTimeInMillis={start_time}&endTimeInMillis={end_time}"
            chart_res = client.get(chart_url, headers=headers)
            
            if chart_res.status_code == 200:
                chart_json = chart_res.json()
                candles = chart_json.get("candles", [])
                
                # Candles format: [timestamp, open, high, low, close, volume]
                # If we have at least 2 candles, the second to last is the "past day"
                if len(candles) >= 2:
                    past_day = candles[-2]
                    data["past_day_high"] = past_day[2]
                    data["past_day_low"] = past_day[3]
                    
        except Exception as e:
            data["error"] = str(e)
            
    return data

@router.get("/grouped-analysis")
def get_grouped_news_stock_analysis(db: Session = Depends(get_db)):
    """Fetch all stocks returned in grouped news and analyze via Accurate Broker API."""
    articles = db.query(db_models.NewsArticle).all()
    
    unique_symbols = set()
    for a in articles:
        if a.affected_symbols:
            for sym in a.affected_symbols:
                if sym != "GENERAL":
                    unique_symbols.add(sym)
                    
    results = []
    for sym in unique_symbols:
        res = get_accurate_stock_data(sym)
        results.append(res)
        
    return results
