"""Risk Feature Extractor — computes normalized live features for each open trade.

Extracts all measurable dimensions of trade health from:
  - Live price data (OHLC, LTP, VWAP)
  - Original trade plan (entry, stop, target from Agent 3)
  - Time in trade
  - Trade mode (INTRADAY / DELIVERY)
  - Technical indicators derived from intraday candles

Each feature is a normalized, named value that the risk scoring engine
and Gemini risk monitor can consume directly.
"""

import time
import math
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
    # Fetch today's candles (from midnight IST)
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

    Returns dict with buy_orders, sell_orders, total_buy_qty, total_sell_qty.
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
# Technical Indicator Derivation from Candles
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Compute RSI from a list of close prices."""
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(0, delta))
        losses.append(max(0, -delta))

    if len(gains) < period:
        return None

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _compute_macd(closes: list[float]) -> dict:
    """Compute MACD (12, 26, 9) from close prices."""
    if len(closes) < 26:
        return {"macd_line": None, "signal_line": None, "histogram": None, "cross_state": "unknown"}

    def ema(data, period):
        k = 2 / (period + 1)
        ema_val = data[0]
        for price in data[1:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val

    # Full EMA series for signal line
    ema12_series = []
    ema26_series = []
    k12 = 2 / 13
    k26 = 2 / 27

    ema12_val = closes[0]
    ema26_val = closes[0]
    for c in closes:
        ema12_val = c * k12 + ema12_val * (1 - k12)
        ema26_val = c * k26 + ema26_val * (1 - k26)
        ema12_series.append(ema12_val)
        ema26_series.append(ema26_val)

    macd_series = [e12 - e26 for e12, e26 in zip(ema12_series, ema26_series)]

    if len(macd_series) < 9:
        return {"macd_line": None, "signal_line": None, "histogram": None, "cross_state": "unknown"}

    # Signal line = 9-period EMA of MACD line
    k9 = 2 / 10
    signal_val = macd_series[0]
    for m in macd_series:
        signal_val = m * k9 + signal_val * (1 - k9)

    macd_now = macd_series[-1]
    histogram = macd_now - signal_val

    # Cross state
    if len(macd_series) >= 2:
        prev_macd = macd_series[-2]
        # Recalculate prev signal roughly
        prev_signal = signal_val  # approximation
        if prev_macd < prev_signal and macd_now >= signal_val:
            cross_state = "bullish_cross"
        elif prev_macd > prev_signal and macd_now <= signal_val:
            cross_state = "bearish_cross"
        elif macd_now > signal_val:
            cross_state = "bullish"
        else:
            cross_state = "bearish"
    else:
        cross_state = "unknown"

    return {
        "macd_line": round(macd_now, 4),
        "signal_line": round(signal_val, 4),
        "histogram": round(histogram, 4),
        "cross_state": cross_state,
    }


def _compute_supertrend(candles: list, period: int = 10, multiplier: float = 3.0) -> str:
    """Compute Supertrend state from OHLC candles. Returns 'green', 'red', or 'unknown'."""
    if len(candles) < period + 1:
        return "unknown"

    # Extract OHLC
    highs = [c[2] for c in candles if len(c) > 4]
    lows = [c[3] for c in candles if len(c) > 4]
    closes = [c[4] for c in candles if len(c) > 4]

    if len(closes) < period + 1:
        return "unknown"

    # Compute ATR
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)

    if len(trs) < period:
        return "unknown"

    atr = sum(trs[-period:]) / period

    # Basic Supertrend
    hl2 = (highs[-1] + lows[-1]) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    if closes[-1] > upper_band:
        return "green"
    elif closes[-1] < lower_band:
        return "red"

    # Check trend from last few candles
    if closes[-1] > hl2:
        return "green"
    else:
        return "red"


def _compute_atr(candles: list, period: int = 14) -> Optional[float]:
    """Compute Average True Range from OHLC candles."""
    if len(candles) < period + 1:
        return None

    trs = []
    for i in range(1, len(candles)):
        if len(candles[i]) < 5 or len(candles[i - 1]) < 5:
            continue
        high = candles[i][2]
        low = candles[i][3]
        prev_close = candles[i - 1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    if len(trs) < period:
        return None

    return round(sum(trs[-period:]) / period, 4)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Feature Extraction
# ═══════════════════════════════════════════════════════════════════════════════

def extract_risk_features(
    signal: dict,
    live_quote: dict,
    candles: list,
    depth: dict,
) -> dict:
    """Extract comprehensive risk features for a single trade.

    Args:
        signal: The trade signal record (from DB, with execution_data, reasoning, etc.)
        live_quote: Latest live quote from Groww API
        candles: Intraday candle list [ts, O, H, L, C, V]
        depth: Market depth data {total_buy_qty, total_sell_qty, imbalance_ratio}

    Returns:
        Dict of normalized risk features
    """
    # ── Extract trade plan from execution_data ────────────────────────────
    exec_data = signal.get("execution_data") or {}
    entry_plan = exec_data.get("entry_plan") or {}
    sl_plan = exec_data.get("stop_loss") or {}
    target_plan = exec_data.get("target") or {}

    entry_price = _sf(entry_plan.get("entry_price"), 0)
    stop_loss = _sf(sl_plan.get("price"), 0)
    target_price = _sf(target_plan.get("price"), 0)
    trade_mode = signal.get("trade_mode", "INTRADAY").upper()
    direction = exec_data.get("action", "BUY").upper()
    is_long = direction in ("BUY",)

    # ── Live price data ──────────────────────────────────────────────────
    ltp = _sf(live_quote.get("ltp") or live_quote.get("close"), 0)
    day_open = _sf(live_quote.get("open"), 0)
    day_high = _sf(live_quote.get("high"), 0)
    day_low = _sf(live_quote.get("low"), 0)
    prev_close = _sf(live_quote.get("close"), 0)
    volume = int(live_quote.get("volume") or 0)
    change_pct = _sf(live_quote.get("dayChangePerc"), 0)
    vwap = _sf(live_quote.get("vwap") or live_quote.get("averagePrice") or live_quote.get("avgPrice"), 0)

    # ── Distance metrics ─────────────────────────────────────────────────
    dist_to_sl_pct = _pct_diff(ltp, stop_loss) if stop_loss > 0 else 999
    dist_from_entry_pct = _pct_diff(ltp, entry_price) if entry_price > 0 else 0
    dist_from_vwap_pct = _pct_diff(ltp, vwap) if vwap > 0 else 0
    dist_from_high_pct = _pct_diff(day_high, ltp) if day_high > 0 else 0
    dist_from_low_pct = _pct_diff(ltp, day_low) if day_low > 0 else 0
    dist_from_target_pct = _pct_diff(target_price, ltp) if target_price > 0 else 0

    # For long trades, SL is below. For short, SL is above.
    if is_long:
        sl_proximity = "safe" if dist_to_sl_pct > 2.0 else (
            "close" if dist_to_sl_pct > 0.8 else (
                "danger" if dist_to_sl_pct > 0 else "breached"
            )
        )
    else:
        # For short, dist_to_sl is negative when approaching SL (which is above entry)
        abs_dist = abs(_pct_diff(stop_loss, ltp)) if stop_loss > 0 else 999
        sl_proximity = "safe" if abs_dist > 2.0 else (
            "close" if abs_dist > 0.8 else (
                "danger" if abs_dist > 0 else "breached"
            )
        )

    # ── Time in trade ────────────────────────────────────────────────────
    executed_at = signal.get("executed_at") or 0
    now_ms = int(time.time() * 1000)
    time_in_trade_seconds = max(0, (now_ms - executed_at) / 1000) if executed_at > 0 else 0

    # Time decay state — varies by trade mode
    if trade_mode == "INTRADAY":
        if time_in_trade_seconds < 900:        # < 15 min
            time_decay_state = "fresh"
        elif time_in_trade_seconds < 3600:     # < 1 hour
            time_decay_state = "acceptable"
        elif time_in_trade_seconds < 7200:     # < 2 hours
            time_decay_state = "aging"
        elif time_in_trade_seconds < 14400:    # < 4 hours
            time_decay_state = "decaying"
        else:
            time_decay_state = "stale"
    else:  # DELIVERY
        if time_in_trade_seconds < 7200:       # < 2 hours
            time_decay_state = "fresh"
        elif time_in_trade_seconds < 14400:    # < 4 hours
            time_decay_state = "acceptable"
        elif time_in_trade_seconds < 28800:    # < 8 hours
            time_decay_state = "aging"
        else:
            time_decay_state = "acceptable"    # Delivery trades have long horizon

    # ── Follow-through check ─────────────────────────────────────────────
    if is_long:
        follow_through_seen = ltp > entry_price * 1.005 if entry_price > 0 else False
        entry_zone_held = ltp >= entry_price * 0.995 if entry_price > 0 else False
    else:
        follow_through_seen = ltp < entry_price * 0.995 if entry_price > 0 else False
        entry_zone_held = ltp <= entry_price * 1.005 if entry_price > 0 else False

    # ── Candle structure analysis ────────────────────────────────────────
    pullback_behavior = "unknown"
    recent_structure = "unknown"
    strong_bearish_reversal = False
    close_near_low = False
    lower_high_detected = False
    relative_volume = 0

    closes = [c[4] for c in candles if len(c) > 4 and c[4]]

    if len(candles) >= 3:
        last_3 = candles[-3:]

        # Pullback analysis (for longs)
        if is_long:
            red_count = sum(1 for c in last_3 if len(c) > 4 and c[4] < c[1])
            if red_count == 0:
                pullback_behavior = "no_pullback"
            elif red_count == 1:
                # Check wick ratio of the red candle
                red_candle = [c for c in last_3 if len(c) > 4 and c[4] < c[1]]
                if red_candle:
                    rc = red_candle[0]
                    body = abs(rc[4] - rc[1])
                    full_range = rc[2] - rc[3] if rc[2] > rc[3] else 0.01
                    if body / full_range < 0.4:
                        pullback_behavior = "healthy_small"
                    else:
                        pullback_behavior = "moderate"
            elif red_count >= 2:
                pullback_behavior = "aggressive"
        else:
            # For shorts, green candles are the pullback
            green_count = sum(1 for c in last_3 if len(c) > 4 and c[4] > c[1])
            if green_count == 0:
                pullback_behavior = "no_pullback"
            elif green_count == 1:
                pullback_behavior = "healthy_small"
            elif green_count >= 2:
                pullback_behavior = "aggressive"

        # Strong bearish reversal candle (last candle)
        lc = candles[-1]
        if len(lc) > 4:
            lc_body = lc[4] - lc[1]
            lc_range = lc[2] - lc[3] if lc[2] > lc[3] else 0.01
            if lc_body < 0 and abs(lc_body) / lc_range > 0.6:
                strong_bearish_reversal = True

            # Close near low
            if lc_range > 0:
                close_position = (lc[4] - lc[3]) / lc_range
                close_near_low = close_position < 0.2

    # Lower high detection (for longs)
    if len(candles) >= 5 and is_long:
        recent_highs = [c[2] for c in candles[-5:] if len(c) > 2]
        if len(recent_highs) >= 3:
            if recent_highs[-1] < recent_highs[-2] and recent_highs[-2] < recent_highs[-3]:
                lower_high_detected = True

    # Recent structure
    if len(closes) >= 5:
        if closes[-1] > closes[-3] and closes[-2] > closes[-4]:
            recent_structure = "higher_highs"
        elif closes[-1] < closes[-3] and closes[-2] < closes[-4]:
            recent_structure = "lower_lows"
        else:
            recent_structure = "mixed"

    # ── Technical indicators from candles ─────────────────────────────────
    rsi_value = _compute_rsi(closes) if len(closes) >= 15 else None
    macd_data = _compute_macd(closes) if len(closes) >= 26 else {
        "macd_line": None, "signal_line": None, "histogram": None, "cross_state": "unknown"
    }
    supertrend_state = _compute_supertrend(candles) if len(candles) >= 11 else "unknown"
    atr_value = _compute_atr(candles) if len(candles) >= 15 else None

    # RSI state classification
    if rsi_value is not None:
        if rsi_value > 80:
            rsi_state = "overbought_extreme"
        elif rsi_value > 70:
            rsi_state = "overbought"
        elif rsi_value > 55:
            rsi_state = "supportive" if is_long else "neutral"
        elif rsi_value > 40:
            rsi_state = "neutral"
        elif rsi_value > 30:
            rsi_state = "supportive" if not is_long else "weakening"
        elif rsi_value > 20:
            rsi_state = "oversold"
        else:
            rsi_state = "oversold_extreme"
    else:
        rsi_state = "unavailable"

    # ATR context
    atr_context = "normal"
    if atr_value is not None and ltp > 0:
        atr_pct = (atr_value / ltp) * 100
        if atr_pct > 3.0:
            atr_context = "high_volatility"
        elif atr_pct > 1.5:
            atr_context = "elevated"
        elif atr_pct < 0.5:
            atr_context = "low_volatility"

    # Volatility state
    if day_high > 0 and day_low > 0 and prev_close > 0:
        day_range_pct = ((day_high - day_low) / prev_close) * 100
        if day_range_pct > 4.0:
            volatility_state = "extreme"
        elif day_range_pct > 2.5:
            volatility_state = "high"
        elif day_range_pct > 1.0:
            volatility_state = "normal"
        else:
            volatility_state = "low"
    else:
        volatility_state = "unknown"

    # Volume context
    volumes = [c[5] for c in candles if len(c) > 5 and c[5]]
    if volumes and len(volumes) >= 5:
        avg_vol = sum(volumes[-5:]) / 5
        recent_vol = volumes[-1] if volumes else 0
        relative_volume = round(recent_vol / avg_vol, 2) if avg_vol > 0 else 0
    else:
        relative_volume = 0

    # Volume pressure
    if relative_volume > 2.0:
        volume_pressure = "surge"
    elif relative_volume > 1.3:
        volume_pressure = "above_average"
    elif relative_volume > 0.7:
        volume_pressure = "normal"
    elif relative_volume > 0:
        volume_pressure = "below_average"
    else:
        volume_pressure = "unknown"

    # Overbought/oversold with volume context
    if rsi_value is not None:
        if rsi_value > 75 and relative_volume > 1.5 and strong_bearish_reversal:
            overbought_oversold_state = "overbought_with_rejection"
        elif rsi_value > 70 and relative_volume > 1.3:
            overbought_oversold_state = "overbought_with_volume"
        elif rsi_value > 70:
            overbought_oversold_state = "overbought_mild"
        elif rsi_value < 25 and relative_volume > 1.5:
            overbought_oversold_state = "oversold_with_volume"
        elif rsi_value < 30:
            overbought_oversold_state = "oversold_mild"
        else:
            overbought_oversold_state = "neutral"
    else:
        overbought_oversold_state = "unknown"

    # Market depth analysis
    depth_imbalance = depth.get("imbalance_ratio", 1.0)
    if depth_imbalance > 2.0:
        market_depth_state = "buyer_heavy"
    elif depth_imbalance > 1.3:
        market_depth_state = "buyer_supportive"
    elif depth_imbalance > 0.7:
        market_depth_state = "balanced"
    elif depth_imbalance > 0.5:
        market_depth_state = "seller_leaning"
    else:
        market_depth_state = "seller_heavy"

    aggressive_selling = (
        depth_imbalance < 0.5
        and relative_volume > 1.5
        and (strong_bearish_reversal or close_near_low)
    )

    # ── Build final feature dict ─────────────────────────────────────────
    return {
        # Identity
        "symbol": signal.get("symbol", "UNKNOWN"),
        "trade_mode": trade_mode,
        "direction": direction,
        "is_long": is_long,

        # Price levels
        "ltp": ltp,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "day_open": day_open,
        "day_high": day_high,
        "day_low": day_low,
        "prev_close": prev_close,
        "vwap": vwap,

        # Distance metrics (%)
        "distance_to_stoploss_percent": round(dist_to_sl_pct, 2),
        "distance_from_entry_percent": round(dist_from_entry_pct, 2),
        "distance_from_vwap_percent": round(dist_from_vwap_pct, 2),
        "distance_from_day_high_percent": round(dist_from_high_pct, 2),
        "distance_from_day_low_percent": round(dist_from_low_pct, 2),
        "distance_from_target_percent": round(dist_from_target_pct, 2),
        "sl_proximity": sl_proximity,

        # Time
        "time_in_trade_seconds": round(time_in_trade_seconds),
        "time_decay_state": time_decay_state,

        # Trade progress
        "follow_through_seen": follow_through_seen,
        "entry_zone_held": entry_zone_held,

        # Candle structure
        "pullback_behavior": pullback_behavior,
        "recent_structure": recent_structure,
        "strong_bearish_reversal_candle": strong_bearish_reversal,
        "close_near_low": close_near_low,
        "lower_high_detected": lower_high_detected,

        # Technical indicators
        "rsi_value": rsi_value,
        "rsi_state": rsi_state,
        "supertrend_state": supertrend_state,
        "macd_cross_state": macd_data.get("cross_state", "unknown"),
        "macd_histogram": macd_data.get("histogram"),

        # Volatility
        "atr_value": atr_value,
        "atr_context": atr_context,
        "volatility_state": volatility_state,

        # Volume
        "relative_volume": relative_volume,
        "volume_pressure": volume_pressure,
        "overbought_oversold_state": overbought_oversold_state,

        # Market depth
        "market_depth_imbalance": round(depth_imbalance, 3),
        "market_depth_state": market_depth_state,
        "aggressive_selling_detected": aggressive_selling,
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
