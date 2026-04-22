"""Risk Feature Extractor — minimal, essential features for live trade monitoring.

Extracts ONLY what the rule-based risk engine needs:
  - Live price (LTP)
  - PnL metrics (percent, rupees)
  - Distance to SL / target
  - Time in trade
  - Simple volume spike detection
  - Simple candle reversal flag
  - Simple structure state (higher-lows / lower-highs)

NO RSI, MACD, Supertrend, ATR scoring, or complex indicator logic.
"""

import time
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))


# ═══════════════════════════════════════════════════════════════════════════════
# Live Data Fetching
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_live_quote(symbol: str) -> dict:
    """Fetch latest live quote from Groww for a symbol."""
    clean = symbol.replace(".NS", "").strip().upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    live_url = (
        f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/"
        f"exchange/NSE/segment/CASH/{clean}/latest"
    )
    try:
        with httpx.Client(timeout=8.0, headers=headers) as client:
            res = client.get(live_url)
            if res.status_code != 200:
                return {"error": f"HTTP {res.status_code}", "symbol": clean}
            return res.json()
    except Exception as e:
        return {"error": str(e), "symbol": clean}


def fetch_intraday_candles(symbol: str, interval_minutes: int = 5) -> list:
    """Fetch intraday candles from Groww charting API.

    Returns list of candles: [timestamp, open, high, low, close, volume]
    """
    clean = symbol.replace(".NS", "").strip().upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    now_ms = int(time.time() * 1000)
    # Fetch today's candles (from market open)
    now_ist = datetime.now(IST)
    today_start = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    start_ms = int(today_start.timestamp() * 1000)

    chart_url = (
        f"https://groww.in/v1/api/charting_service/v2/chart/"
        f"exchange/NSE/segment/CASH/{clean}"
        f"?intervalInMinutes={interval_minutes}&minimal=false"
        f"&startTimeInMillis={start_ms}&endTimeInMillis={now_ms}"
    )
    try:
        with httpx.Client(timeout=8.0, headers=headers) as client:
            res = client.get(chart_url)
            if res.status_code == 200:
                return res.json().get("candles", [])
    except Exception:
        pass
    return []


def fetch_market_depth(symbol: str) -> dict:
    """Fetch market depth (buy/sell order book) from Groww.

    Returns dict with total_buy_qty, total_sell_qty, imbalance_ratio.
    """
    clean = symbol.replace(".NS", "").strip().upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    depth_url = (
        f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/"
        f"exchange/NSE/segment/CASH/{clean}/latest"
    )
    try:
        with httpx.Client(timeout=8.0, headers=headers) as client:
            res = client.get(depth_url)
            if res.status_code == 200:
                data = res.json()
                # Groww live data sometimes includes depth in the same payload
                total_buy = data.get("totalBuyQty", 0) or 0
                total_sell = data.get("totalSellQty", 0) or 0
                return {
                    "total_buy_qty": total_buy,
                    "total_sell_qty": total_sell,
                    "imbalance_ratio": (
                        round(total_buy / total_sell, 3)
                        if total_sell > 0 else 999.0
                    ),
                }
    except Exception:
        pass
    return {"total_buy_qty": 0, "total_sell_qty": 0, "imbalance_ratio": 1.0}


# ═══════════════════════════════════════════════════════════════════════════════
# Main Feature Extraction
# ═══════════════════════════════════════════════════════════════════════════════

def extract_risk_features(
    signal: dict,
    live_quote: dict,
    candles: list,
    depth: dict,
) -> dict:
    """Extract minimal, essential features for the rule-based risk engine.

    Args:
        signal: The trade signal record (from DB, with execution_data, reasoning, etc.)
        live_quote: Latest live quote from Groww API
        candles: Intraday candle list [ts, O, H, L, C, V]
        depth: Market depth data {total_buy_qty, total_sell_qty, imbalance_ratio}

    Returns:
        Dict of normalized risk features — ONLY what the rule engine needs.
    """
    # ── Extract trade plan from flattened trade dict ────────────────────────────
    entry_price = _sf(signal.get("entry_price"), 0)
    stop_loss = _sf(signal.get("stop_loss"), 0)
    target_price = _sf(signal.get("target_price"), 0)
    trade_mode = signal.get("trade_mode", "INTRADAY").upper()
    direction = signal.get("direction", "BUY").upper()
    quantity = int(signal.get("quantity", 1))
    is_long = direction in ("BUY",)

    # ── Live price data ──────────────────────────────────────────────────
    ltp = _sf(live_quote.get("ltp") or live_quote.get("close"), 0)
    day_open = _sf(live_quote.get("open"), 0)
    day_high = _sf(live_quote.get("high"), 0)
    day_low = _sf(live_quote.get("low"), 0)
    prev_close = _sf(live_quote.get("close"), 0)
    volume = int(live_quote.get("volume") or 0)
    vwap = _sf(live_quote.get("vwap") or live_quote.get("averagePrice") or live_quote.get("avgPrice"), 0)

    # ── PnL metrics ──────────────────────────────────────────────────────
    if entry_price > 0 and ltp > 0:
        if is_long:
            pnl_percent = round(((ltp - entry_price) / entry_price) * 100, 2)
        else:
            pnl_percent = round(((entry_price - ltp) / entry_price) * 100, 2)
    else:
        pnl_percent = 0.0

    # PnL in rupees (per share & total)
    if is_long:
        pnl_rupees_per_share = round(ltp - entry_price, 2) if entry_price > 0 else 0.0
    else:
        pnl_rupees_per_share = round(entry_price - ltp, 2) if entry_price > 0 else 0.0

    pnl_rupees_total = round(pnl_rupees_per_share * quantity, 2)

    # ── Distance metrics ─────────────────────────────────────────────────
    distance_from_entry = _pct_diff(ltp, entry_price) if entry_price > 0 else 0
    distance_to_sl = abs(_pct_diff(ltp, stop_loss)) if stop_loss > 0 else 999
    distance_to_target = abs(_pct_diff(target_price, ltp)) if target_price > 0 else 999

    # ── Time in trade ────────────────────────────────────────────────────
    executed_at = signal.get("executed_at") or 0
    now_ms = int(time.time() * 1000)
    time_in_trade_seconds = max(0, (now_ms - executed_at) / 1000) if executed_at > 0 else 0

    # ── MFE / MAE Tracking ───────────────────────────────────────────────
    # MFE = Maximum Favorable Excursion, MAE = Maximum Adverse Excursion
    mfe = entry_price
    mae = entry_price

    if entry_price > 0:
        for c in candles:
            if len(c) > 4:
                ts = c[0]
                if ts >= executed_at:
                    high_price = c[2]
                    low_price = c[3]
                    if is_long:
                        if high_price > mfe: mfe = high_price
                        if low_price < mae: mae = low_price
                    else:
                        if low_price < mfe: mfe = low_price
                        if high_price > mae: mae = high_price
        
        # Consider LTP as well
        if ltp > 0:
            if is_long:
                if ltp > mfe: mfe = ltp
                if ltp < mae: mae = ltp
            else:
                if ltp < mfe: mfe = ltp
                if ltp > mae: mae = ltp

    mfe_pct = _pct_diff(mfe, entry_price) if is_long else _pct_diff(entry_price, mfe)
    mae_pct = _pct_diff(mae, entry_price) if is_long else _pct_diff(entry_price, mae)
    
    # mae_pct is always negative or zero for adverse excursion
    if mae_pct > 0: mae_pct = 0.0

    # ── Volume spike detection ───────────────────────────────────────────
    volumes = [c[5] for c in candles if len(c) > 5 and c[5]]
    relative_volume = 0.0
    volume_spike_against = False

    if volumes and len(volumes) >= 5:
        avg_vol = sum(volumes[:-1]) / max(1, len(volumes) - 1)
        recent_vol = volumes[-1]
        relative_volume = round(recent_vol / avg_vol, 2) if avg_vol > 0 else 0

        # Volume spike against position = high volume + price moving against us
        if relative_volume > 2.0 and len(candles) >= 1:
            last_candle = candles[-1]
            if len(last_candle) > 4:
                candle_direction = last_candle[4] - last_candle[1]  # close - open
                if is_long and candle_direction < 0:
                    volume_spike_against = True
                elif not is_long and candle_direction > 0:
                    volume_spike_against = True

    # ── Simple candle reversal flag ──────────────────────────────────────
    strong_reversal_candle = False
    if len(candles) >= 1:
        lc = candles[-1]
        if len(lc) > 4:
            lc_body = lc[4] - lc[1]  # close - open
            lc_range = lc[2] - lc[3] if lc[2] > lc[3] else 0.01
            body_ratio = abs(lc_body) / lc_range
            # For longs: big red candle is reversal. For shorts: big green candle.
            if is_long and lc_body < 0 and body_ratio > 0.6:
                strong_reversal_candle = True
            elif not is_long and lc_body > 0 and body_ratio > 0.6:
                strong_reversal_candle = True

    # ── Simple structure state (last 5 candle highs/lows) ────────────────
    structure_state = "unknown"
    recent_swing_high = 0.0
    recent_swing_low = 0.0

    if len(candles) >= 5:
        recent_highs = [c[2] for c in candles[-5:] if len(c) > 4]
        recent_lows = [c[3] for c in candles[-5:] if len(c) > 4]

        if recent_highs:
            recent_swing_high = max(recent_highs)
        if recent_lows:
            recent_swing_low = min(recent_lows)

        if len(recent_highs) >= 3 and len(recent_lows) >= 3:
            # Lower highs = bearish structure
            lower_highs = (
                recent_highs[-1] < recent_highs[-2]
                and recent_highs[-2] < recent_highs[-3]
            )
            # Higher lows = bullish structure
            higher_lows = (
                recent_lows[-1] > recent_lows[-2]
                and recent_lows[-2] > recent_lows[-3]
            )

            if is_long:
                if lower_highs:
                    structure_state = "reversing"  # Bearish for long
                elif higher_lows:
                    structure_state = "healthy"    # Bullish for long
                else:
                    structure_state = "neutral"
            else:
                if higher_lows:
                    structure_state = "reversing"  # Bullish for short
                elif lower_highs:
                    structure_state = "healthy"    # Bearish for short
                else:
                    structure_state = "neutral"

    # ── Build final feature dict ─────────────────────────────────────────
    return {
        # Identity
        "symbol": signal.get("symbol", "UNKNOWN"),
        "trade_mode": trade_mode,
        "direction": direction,
        "is_long": is_long,
        "quantity": quantity,

        # Price levels
        "ltp": ltp,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "day_high": day_high,
        "day_low": day_low,
        "vwap": vwap,

        # PnL
        "pnl_percent": pnl_percent,
        "pnl_rupees_per_share": pnl_rupees_per_share,
        "pnl_rupees_total": pnl_rupees_total,

        # Distance metrics (%)
        "distance_from_entry": round(distance_from_entry, 2),
        "distance_to_sl": round(distance_to_sl, 2),
        "distance_to_target": round(distance_to_target, 2),

        # MFE / MAE
        "mfe": mfe,
        "mfe_pct": round(mfe_pct, 2),
        "mae": mae,
        "mae_pct": round(mae_pct, 2),

        # Time
        "time_in_trade_seconds": round(time_in_trade_seconds),

        # Volume
        "relative_volume": relative_volume,
        "volume_spike_against": volume_spike_against,

        # Candle / Structure
        "strong_reversal_candle": strong_reversal_candle,
        "structure_state": structure_state,
        "recent_swing_high": recent_swing_high,
        "recent_swing_low": recent_swing_low,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _sf(value, default: float = 0.0) -> float:
    """Safe float conversion."""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _pct_diff(a: float, b: float) -> float:
    """Percentage difference: ((a - b) / b) * 100."""
    if b == 0:
        return 0.0
    return round(((a - b) / b) * 100, 4)