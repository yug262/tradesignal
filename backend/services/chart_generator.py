"""Chart Generator — Creates technical analysis chart images for Agent 3.

Generates candlestick charts with overlaid technical indicators (EMA, SMA, RSI,
MACD, ATR, Bollinger Bands, etc.) using matplotlib + mplfinance.

The output is a PNG image (as bytes) that can be passed directly to Gemini's
multimodal API, enabling Agent 3 to visually analyze price action and
indicator patterns for more accurate execution decisions.

Key design decisions:
  - Charts are rendered headless (Agg backend) — no GUI needed on the server.
  - Output is in-memory bytes (io.BytesIO), never written to disk.
  - Chart includes: candlestick body, volume bars, and up to 4 indicator subplots.
  - Colors and styling optimized for AI readability (high contrast, clear labels).
"""

import io
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd

# Force non-interactive backend BEFORE importing pyplot
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch

try:
    import talib
except ImportError:
    talib = None

IST = timezone(timedelta(hours=5, minutes=30))


# ═══════════════════════════════════════════════════════════════════════════════
# CHART STYLE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

CHART_STYLE = {
    "bg_color": "#12151c",
    "text_color": "#d1d4dc",
    "grid_color": "#2a2e39",
    "candle_up": "#08d18d",      # Vibrant Groww Green
    "candle_down": "#ff5252",    # Vibrant Groww Red
    "candle_up_edge": "#08d18d",
    "candle_down_edge": "#ff5252",
    "volume_up": "#08d18d40",
    "volume_down": "#ff525240",
    "ema_color": "#ffab00",
    "sma_color": "#2979ff",
    "vwap_color": "#e040fb",
    "bb_upper": "#ff6f00",
    "bb_lower": "#ff6f00",
    "bb_fill": "#ff6f0015",
    "rsi_line": "#00e5ff",
    "rsi_ob": "#ff5252",
    "rsi_os": "#08d18d",
    "rsi_fill_ob": "#ff525220",
    "rsi_fill_os": "#08d18d20",
    "macd_line": "#00e5ff",
    "macd_signal": "#ff6f00",
    "macd_hist_pos": "#08d18d60",
    "macd_hist_neg": "#ff525260",
    "atr_line": "#b388ff",
    "ltp_line": "#ffffff",
    "entry_line": "#00e5ff",
    "stop_line": "#ff1744",
    "target_line": "#00e676",
}

CHART_WIDTH = 14
CHART_DPI = 150  # High enough for AI to read, low enough for fast generation


# ═══════════════════════════════════════════════════════════════════════════════
# CANDLE DATA FETCHER (reuses existing infrastructure)
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_candles_for_chart(symbol: str, interval: int, count: int = 60) -> list:
    """Fetch raw OHLCV candles from Groww for chart rendering.
    
    Reuses the same data source as the indicator pipeline but fetches
    more candles (60) for a richer visual context.
    """
    import httpx

    clean = symbol.replace(".NS", "").strip().upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    now_ms = int(time.time() * 1000)
    if interval == 1440:
        start_ms = now_ms - int(86400 * count * 1.5 * 1000)
    else:
        # Look back 5 days to ensure we hit the last trading session even over long weekends
        start_ms = now_ms - int(86400 * 5 * 1000)

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
                raw_candles = res.json().get("candles", [])
                # Validate candles
                valid = []
                for c in raw_candles:
                    if not isinstance(c, (list, tuple)) or len(c) < 5:
                        continue
                    try:
                        o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
                        if o <= 0 or h <= 0 or l <= 0 or cl <= 0:
                            continue
                        if h < l or h < o or h < cl or l > o or l > cl:
                            continue
                        valid.append(c)
                    except (ValueError, TypeError):
                        continue
                return valid[-count:] if len(valid) > count else valid
    except Exception as e:
        print(f"  [CHART] Candle fetch failed for {symbol}: {e}")
    return []


def _candles_to_dataframe(candles: list, interval: int = 1) -> pd.DataFrame:
    """Convert raw candle list to a pandas DataFrame with DatetimeIndex.
    
    Candle format: [timestamp_ms, open, high, low, close, volume]
    """
    records = []
    for c in candles:
        ts = c[0]
        # Groww timestamps are in milliseconds
        dt = datetime.fromtimestamp(ts / 1000, tz=IST) if ts > 1e12 else datetime.fromtimestamp(ts, tz=IST)
        vol = int(c[5]) if len(c) > 5 and c[5] else 0
        records.append({
            "Date": dt,
            "Open": float(c[1]),
            "High": float(c[2]),
            "Low": float(c[3]),
            "Close": float(c[4]),
            "Volume": vol,
        })

    df = pd.DataFrame(records)
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    
    if interval == 1 and len(df) > 1:
        # Groww 1-minute intraday charts return cumulative daily volume in c[5].
        # We must differentiate it to get actual per-minute volume.
        diff_vol = df["Volume"].diff()
        # If difference is negative, it means a new day started, so keep the raw volume
        df["Volume"] = np.where(diff_vol < 0, df["Volume"], diff_vol)
        df["Volume"] = df["Volume"].fillna(df["Volume"].iloc[0])
        # Prevent any negative volume just in case
        df["Volume"] = df["Volume"].clip(lower=0)
        
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# PURE NUMPY/PANDAS INDICATOR FALLBACKS (when TA-Lib is not installed)
# ═══════════════════════════════════════════════════════════════════════════════

def _np_ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average using numpy — matches TA-Lib output."""
    result = np.full_like(data, np.nan)
    if len(data) < period:
        return result
    # Seed with SMA for the first 'period' values
    result[period - 1] = np.mean(data[:period])
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(data)):
        result[i] = data[i] * multiplier + result[i - 1] * (1 - multiplier)
    return result


def _np_sma(data: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average using numpy."""
    result = np.full_like(data, np.nan)
    if len(data) < period:
        return result
    cumsum = np.cumsum(data)
    cumsum[period:] = cumsum[period:] - cumsum[:-period]
    result[period - 1:] = cumsum[period - 1:] / period
    return result


def _np_rsi(data: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index using numpy — Wilder's smoothing method."""
    result = np.full_like(data, np.nan)
    if len(data) < period + 1:
        return result
    deltas = np.diff(data)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    # First average
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))
    # Wilder's smoothing
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - (100.0 / (1.0 + rs))
    return result


def _np_macd(data: np.ndarray, fast: int = 12, slow: int = 26, signal_period: int = 9):
    """MACD using numpy — returns (macd_line, signal_line, histogram)."""
    ema_fast = _np_ema(data, fast)
    ema_slow = _np_ema(data, slow)
    macd_line = ema_fast - ema_slow
    # Signal line is EMA of MACD line
    valid_macd = macd_line.copy()
    signal_line = _np_ema(valid_macd, signal_period)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _np_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range using numpy — Wilder's smoothing."""
    result = np.full_like(closes, np.nan)
    if len(closes) < period + 1:
        return result
    # True Range
    tr = np.zeros(len(closes))
    tr[0] = highs[0] - lows[0]
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    # First ATR is simple average of first 'period' TRs
    result[period] = np.mean(tr[1:period + 1])
    # Wilder's smoothing
    for i in range(period + 1, len(closes)):
        result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def _np_bbands(data: np.ndarray, period: int = 20, nbdev: float = 2.0):
    """Bollinger Bands using numpy — returns (upper, middle, lower)."""
    middle = _np_sma(data, period)
    # Rolling standard deviation
    std = np.full_like(data, np.nan)
    for i in range(period - 1, len(data)):
        std[i] = np.std(data[i - period + 1:i + 1], ddof=0)
    upper = middle + nbdev * std
    lower = middle - nbdev * std
    return upper, middle, lower


# ═══════════════════════════════════════════════════════════════════════════════
# INDICATOR COMPUTATION FOR CHART OVERLAY
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_indicators_for_chart(
    df: pd.DataFrame,
    requested_indicators: list,
) -> dict:
    """Compute indicators and return them as named Series/arrays.
    
    Uses TA-Lib when available, falls back to pure numpy implementations.
    
    Returns a dict keyed by indicator type:
      {
        "overlays": [(name, series, color), ...],  # plotted on price axis
        "rsi": series or None,                      # separate subplot
        "macd": (macd, signal, hist) or None,       # separate subplot
        "atr": series or None,                      # separate subplot
      }
    """
    result = {
        "overlays": [],
        "rsi": None,
        "macd": None,
        "atr": None,
    }

    use_talib = talib is not None
    engine = "TA-Lib" if use_talib else "numpy"
    print(f"  [CHART] Computing indicators using {engine}...")

    closes = df["Close"].values
    highs = df["High"].values
    lows = df["Low"].values

    for req in requested_indicators[:4]:  # Cap at 4
        if isinstance(req, str):
            name = req.upper().strip()
            req_dict = {"name": name} # Dummy dict for get() calls below
        else:
            name = str(req.get("name", "")).upper().strip()
            req_dict = req

        try:
            if name in ("EMA",):
                period = int(req_dict.get("period", 20))
                vals = talib.EMA(closes, timeperiod=period) if use_talib else _np_ema(closes, period)
                series = pd.Series(vals, index=df.index, name=f"EMA({period})")
                result["overlays"].append((f"EMA({period})", series, CHART_STYLE["ema_color"]))

            elif name in ("SMA",):
                period = int(req_dict.get("period", 20))
                vals = talib.SMA(closes, timeperiod=period) if use_talib else _np_sma(closes, period)
                series = pd.Series(vals, index=df.index, name=f"SMA({period})")
                result["overlays"].append((f"SMA({period})", series, CHART_STYLE["sma_color"]))

            elif name == "RSI":
                period = int(req_dict.get("period", 14))
                vals = talib.RSI(closes, timeperiod=period) if use_talib else _np_rsi(closes, period)
                result["rsi"] = pd.Series(vals, index=df.index, name=f"RSI({period})")

            elif name == "MACD":
                if use_talib:
                    macd_v, signal_v, hist_v = talib.MACD(closes)
                else:
                    macd_v, signal_v, hist_v = _np_macd(closes)
                result["macd"] = (
                    pd.Series(macd_v, index=df.index, name="MACD"),
                    pd.Series(signal_v, index=df.index, name="Signal"),
                    pd.Series(hist_v, index=df.index, name="Histogram"),
                )

            elif name in ("ATR", "NATR"):
                period = int(req_dict.get("period", 14))
                vals = talib.ATR(highs, lows, closes, timeperiod=period) if use_talib else _np_atr(highs, lows, closes, period)
                result["atr"] = pd.Series(vals, index=df.index, name=f"ATR({period})")

            elif name == "BBANDS":
                period = int(req_dict.get("period", 20))
                if use_talib:
                    upper, middle, lower = talib.BBANDS(closes, timeperiod=period)
                else:
                    upper, middle, lower = _np_bbands(closes, period)
                result["overlays"].append(("BB Upper", pd.Series(upper, index=df.index), CHART_STYLE["bb_upper"]))
                result["overlays"].append(("BB Lower", pd.Series(lower, index=df.index), CHART_STYLE["bb_lower"]))
                result["overlays"].append(("BB Mid", pd.Series(middle, index=df.index), CHART_STYLE["sma_color"]))

            elif name in ("WMA",):
                period = int(req_dict.get("period", 20))
                if use_talib:
                    vals = talib.WMA(closes, timeperiod=period)
                else:
                    # WMA fallback: use weighted numpy calculation
                    vals = np.full_like(closes, np.nan)
                    weights = np.arange(1, period + 1, dtype=float)
                    for i in range(period - 1, len(closes)):
                        vals[i] = np.dot(closes[i - period + 1:i + 1], weights) / weights.sum()
                series = pd.Series(vals, index=df.index, name=f"WMA({period})")
                result["overlays"].append((f"WMA({period})", series, "#e040fb"))

            elif name in ("DEMA",):
                period = int(req.get("period", 20))
                if use_talib:
                    vals = talib.DEMA(closes, timeperiod=period)
                else:
                    vals = _np_ema(closes, period) # fallback to ema
                series = pd.Series(vals, index=df.index, name=f"DEMA({period})")
                result["overlays"].append((f"DEMA({period})", series, "#FF9800"))

            elif name in ("TEMA",):
                period = int(req.get("period", 20))
                if use_talib:
                    vals = talib.TEMA(closes, timeperiod=period)
                else:
                    vals = _np_ema(closes, period) # fallback to ema
                series = pd.Series(vals, index=df.index, name=f"TEMA({period})")
                result["overlays"].append((f"TEMA({period})", series, "#E91E63"))

            elif name in ("VWAP",):
                # Native VWAP Calculation
                volumes = df["Volume"].values
                typical_price = (highs + lows + closes) / 3
                vwap_vals = np.cumsum(typical_price * volumes) / (np.cumsum(volumes) + 1e-9)
                series = pd.Series(vwap_vals, index=df.index, name="VWAP")
                result["overlays"].append(("VWAP", series, "#FFD700"))

            elif name in ("SAR",):
                if use_talib:
                    vals = talib.SAR(highs, lows, acceleration=0.02, maximum=0.2)
                    series = pd.Series(vals, index=df.index, name="SAR")
                    result["overlays"].append(("SAR", series, "#00BCD4"))

            print(f"  [CHART]   {name}: computed OK")

        except Exception as e:
            print(f"  [CHART] Failed to compute {name}: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CHART RENDERER
# ═══════════════════════════════════════════════════════════════════════════════

def generate_technical_chart(
    symbol: str,
    trade_mode: str,
    requested_indicators: list,
    ltp: float = None,
    direction: str = None,
    entry_suggestion: float = None,
    stop_suggestion: float = None,
    target_suggestion: float = None,
) -> Optional[bytes]:
    """Generate a technical analysis chart image as PNG bytes.
    
    This is the main entry point. It:
    1. Fetches 60 candles from Groww
    2. Computes requested indicators via TA-Lib
    3. Renders a professional candlestick chart with indicator overlays
    4. Returns PNG bytes (or None if generation fails)
    
    The chart is designed for AI consumption — high contrast, clear labels,
    annotated levels, and clean indicator subplots.
    
    Args:
        symbol: NSE stock symbol
        trade_mode: INTRADAY or DELIVERY
        requested_indicators: List of {name, timeframe, reason, period}
        ltp: Current LTP for annotation
        direction: BULLISH or BEARISH (for color coding)
        entry_suggestion: Optional entry price line
        stop_suggestion: Optional stop loss line  
        target_suggestion: Optional target price line
    
    Returns:
        PNG image bytes, or None if chart generation fails
    """
    print(f"\n  [CHART] Generating technical chart for {symbol}...")
    start_time = time.time()

    # 1. Determine interval from trade mode
    interval = 1440 if trade_mode.upper() == "DELIVERY" else 1
    tf_label = "Daily" if interval == 1440 else "1-Min"

    # 2. Fetch candle data with extra 50 candles warmup for TA-Lib
    warmup = 50
    display_count = 60
    candles = _fetch_candles_for_chart(symbol, interval, count=display_count + warmup)
    if not candles or len(candles) < 10:
        print(f"  [CHART] Not enough candle data for {symbol} (got {len(candles)})")
        return None

    full_df = _candles_to_dataframe(candles, interval)

    # If LTP is not provided, use the last candle's close for visual consistency
    if ltp is None and not full_df.empty:
        ltp = float(full_df["Close"].iloc[-1])
        
    # 3. Compute on the FULL dataframe to warm up indicators (DEMA, EMA, etc.)
    indicators = _compute_indicators_for_chart(full_df, requested_indicators)

    # Now strictly slice down to the final display_count (60) for rendering
    df = full_df.iloc[-display_count:].copy()
    
    # Slice all indicator Series down to the display frame
    for i in range(len(indicators["overlays"])):
        name, series, color = indicators["overlays"][i]
        indicators["overlays"][i] = (name, series.loc[df.index], color)
        
    if indicators["rsi"] is not None:
        indicators["rsi"] = indicators["rsi"].loc[df.index]
        
    if indicators["macd"] is not None:
        macd, sig, hist = indicators["macd"]
        indicators["macd"] = (macd.loc[df.index], sig.loc[df.index], hist.loc[df.index])
        
    if indicators["atr"] is not None:
        indicators["atr"] = indicators["atr"].loc[df.index]

    # 4. Determine subplot layout: We ALWAYS want 4 subplots as requested.
    # Panel 0: Price & Trend
    # Panel 1: Momentum (RSI or MACD)
    # Panel 2: Volatility (ATR)
    # Panel 3: Volume
    
    # Ensure we have something for Momentum and Volatility
    if indicators["rsi"] is None and indicators["macd"] is None:
        # Fallback calculate RSI
        indicators["rsi"] = pd.Series(
            talib.RSI(df["Close"].values, timeperiod=14) if talib else _np_rsi(df["Close"].values, 14),
            index=df.index, name="RSI(14)"
        )
    if indicators["atr"] is None:
        # Fallback calculate ATR
        indicators["atr"] = pd.Series(
            talib.ATR(df["High"].values, df["Low"].values, df["Close"].values, timeperiod=14) 
            if talib else _np_atr(df["High"].values, df["Low"].values, df["Close"].values, 14),
            index=df.index, name="ATR(14)"
        )

    n_subplots = 4
    height_ratios = [3.5, 1.2, 1.2, 1.0]  # Price, Momentum, Volatility, Volume

    total_height = sum(height_ratios) * 1.8 + 1  # Scale factor

    # 5. Create figure with dark theme
    fig, axes = plt.subplots(
        n_subplots, 1,
        figsize=(CHART_WIDTH, total_height),
        gridspec_kw={"height_ratios": height_ratios, "hspace": 0.5}, # further hspace for labels
        squeeze=False,
    )
    axes = axes.flatten()
    
    # Pre-calculate x-axis coordinates (0, 1, 2...) to avoid gaps in time
    x_coords = np.arange(len(df))
    
    # Accurate Date Labels: Show Date only when day changes, else Time
    date_labels = []
    prev_date = None
    day_breaks = []
    for i, dt in enumerate(df.index):
        curr_date = dt.date()
        if prev_date is None or curr_date != prev_date:
            date_labels.append(dt.strftime("%d %b"))
            day_breaks.append(i)
        else:
            date_labels.append(dt.strftime("%H:%M"))
        prev_date = curr_date

    fig.patch.set_facecolor(CHART_STYLE["bg_color"])

    # Set overall title/description
    fig.suptitle(
        f"Technical Analysis Chart: {symbol} ({tf_label})\n"
        "Price & Trend  |  Momentum  |  Volatility  |  Volume",
        color=CHART_STYLE["text_color"], fontsize=16, fontweight="bold", y=0.96
    )

    # ── PRICE PANEL (axes[0]) ──────────────────────────────────────────
    ax_price = axes[0]
    overlay_names = [name for name, _, _ in indicators["overlays"]]
    # Combine BB bands into a single label for cleaner title if present
    if "BB Upper" in overlay_names:
        overlay_names = [n for n in overlay_names if not n.startswith("BB ")] + ["BBANDS"]
    
    overlay_title = f" ({', '.join(overlay_names)})" if overlay_names else ""
    desc_1 = " - Identifies trend direction and support/resistance levels"
    ax_price.set_title(f"Chart 1: Price Action & Trend Indicators{overlay_title}{desc_1}", color=CHART_STYLE["text_color"], fontsize=10, loc="left", pad=5)
    ax_price.set_ylabel("Price (INR)", fontsize=9, color=CHART_STYLE["text_color"])
    _render_candlestick(ax_price, x_coords, df)
    # Add Day Break Lines
    for brk in day_breaks:
        if brk > 0:
            ax_price.axvline(x=brk - 0.5, color=CHART_STYLE["grid_color"], linestyle="--", alpha=0.5, linewidth=1)

    _render_overlays(ax_price, x_coords, indicators["overlays"])
    _render_suggested_levels(ax_price, x_coords, df, entry_suggestion, stop_suggestion, target_suggestion)

    # Annotate LTP (only if within visible range of candle data)
    if ltp and ltp > 0:
        price_min, price_max = df["Low"].min(), df["High"].max()
        price_range = price_max - price_min
        if price_min - price_range * 0.3 <= ltp <= price_max + price_range * 0.3:
            ax_price.axhline(
                y=ltp, color=CHART_STYLE["ltp_line"], linewidth=0.8,
                linestyle="--", alpha=0.7
            )
            ax_price.text(
                x_coords[-1], ltp, f"  LTP Rs.{ltp:.2f}",
                color=CHART_STYLE["ltp_line"], fontsize=9, fontweight="bold",
                va="center",
            )
    # Add headroom for the summary box (top right)
    # Get current limits which already include the suggested level lines
    ymin, ymax = ax_price.get_ylim()
    yrange = ymax - ymin
    # Add extra 20% at the top specifically for the summary box
    ax_price.set_ylim(ymin - yrange * 0.05, ymax + yrange * 0.25)

    # Style price axis
    ax_price.set_facecolor(CHART_STYLE["bg_color"])
    ax_price.tick_params(colors=CHART_STYLE["text_color"], labelsize=8)
    ax_price.grid(True, color=CHART_STYLE["grid_color"], alpha=0.3, linewidth=0.5)
    ax_price.spines["top"].set_visible(False)
    ax_price.spines["right"].set_color(CHART_STYLE["grid_color"])
    ax_price.spines["left"].set_color(CHART_STYLE["grid_color"])
    ax_price.spines["bottom"].set_color(CHART_STYLE["grid_color"])

    # Title
    dir_label = f" | Bias: {direction}" if direction else ""
    ax_price.text(
        0.01, 0.95, f" {symbol} • {tf_label} {dir_label}",
        transform=ax_price.transAxes,
        fontsize=12, fontweight="bold", color=CHART_STYLE["text_color"],
        va="top", ha="left",
        bbox=dict(facecolor=CHART_STYLE["bg_color"], alpha=0.7, edgecolor='none')
    )

    # Add Summary Stats Header (Top Left - Single Line to avoid overlap)
    _render_summary_header(ax_price, df, indicators, ltp)

    # Legend for overlays - move to lower left
    if indicators["overlays"]:
        ax_price.legend(
            loc="lower left", fontsize=8,
            facecolor=CHART_STYLE["bg_color"],
            edgecolor=CHART_STYLE["grid_color"],
            labelcolor=CHART_STYLE["text_color"],
            framealpha=0.6,
        )

    # ── INDICATOR SUBPLOTS ─────────────────────────────────────────────
    
    # Chart 2: Momentum
    ax_mom = axes[1]
    desc_2 = " - Shows overbought/oversold extremes and momentum strength"
    if indicators["macd"] is not None:
        ax_mom.set_title(f"Chart 2: Momentum Indicator (MACD){desc_2}", color=CHART_STYLE["text_color"], fontsize=10, loc="left", pad=5)
        macd_line, signal_line, hist = indicators["macd"]
        _render_macd(ax_mom, x_coords, macd_line, signal_line, hist)
    else:
        rsi_name = indicators["rsi"].name if indicators["rsi"] is not None else "RSI"
        ax_mom.set_title(f"Chart 2: Momentum Indicator ({rsi_name}){desc_2}", color=CHART_STYLE["text_color"], fontsize=10, loc="left", pad=5)
        _render_rsi(ax_mom, x_coords, indicators["rsi"])

    # Chart 3: Volatility
    ax_volatility = axes[2]
    atr_name = indicators["atr"].name if indicators["atr"] is not None else "ATR"
    desc_3 = " - Measures price fluctuation to help size stop-losses properly"
    ax_volatility.set_title(f"Chart 3: Volatility Indicator ({atr_name}){desc_3}", color=CHART_STYLE["text_color"], fontsize=10, loc="left", pad=5)
    _render_atr(ax_volatility, x_coords, indicators["atr"])

    # Chart 4: Volume
    ax_vol = axes[3]
    desc_4 = " - Confirms the strength of price movements and breakouts"
    ax_vol.set_title(f"Chart 4: Volume Indicator{desc_4}", color=CHART_STYLE["text_color"], fontsize=10, loc="left", pad=5)
    _render_standalone_volume(ax_vol, x_coords, df)

    # Format x-axis: Show labels on ALL panels, use integer coordinates mapped to dates
    for i, ax in enumerate(axes):
        # Day break lines for all subplots
        for brk in day_breaks:
            if brk > 0:
                ax.axvline(x=brk - 0.5, color=CHART_STYLE["grid_color"], linestyle="--", alpha=0.3, linewidth=0.8)
                
        # Smart Ticks: ensures we show the date at the start of each day
        tick_indices = list(day_breaks)
        if len(x_coords) > 10:
            step = len(x_coords) // 6
            tick_indices.extend(range(0, len(x_coords), step))
        tick_indices = sorted(list(set(tick_indices)))
        tick_indices = [idx for idx in tick_indices if idx < len(x_coords)]

        ax.set_xticks(tick_indices)
        ax.set_xticklabels([date_labels[idx] for idx in tick_indices], 
                          rotation=0, ha="center", fontsize=8, color=CHART_STYLE["text_color"])
        ax.tick_params(axis="x", colors=CHART_STYLE["text_color"], length=5)
        ax.set_xlabel("Time (IST)", fontsize=9, color=CHART_STYLE["text_color"], fontweight="bold")


    # 6. Render to bytes
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=CHART_DPI,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)
    buf.seek(0)
    image_bytes = buf.getvalue()

    elapsed = round((time.time() - start_time) * 1000)
    size_kb = len(image_bytes) / 1024
    print(f"  [CHART] Generated {symbol} chart: {size_kb:.0f} KB in {elapsed}ms")

    return image_bytes


# ═══════════════════════════════════════════════════════════════════════════════
# RENDERING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _render_candlestick(ax, x_coords: np.ndarray, df: pd.DataFrame):
    """Draw candlestick bodies and wicks on the given axes."""
    candle_width = 0.6

    for i, (x, row) in enumerate(zip(x_coords, df.itertuples())):
        o, h, l, c = row.Open, row.High, row.Low, row.Close

        if c >= o:
            color = CHART_STYLE["candle_up"]
            edge = CHART_STYLE["candle_up_edge"]
        else:
            color = CHART_STYLE["candle_down"]
            edge = CHART_STYLE["candle_down_edge"]

        # Wick (high-low line)
        ax.plot([x, x], [l, h], color=edge, linewidth=0.5, zorder=2) # thinner wick

        # Body
        body_bottom = min(o, c)
        body_height = abs(c - o)
        if body_height == 0:
            body_height = h * 0.0005 # tiny visible body for doji

        ax.bar(
            x, body_height, bottom=body_bottom, width=candle_width,
            color=color, edgecolor=edge, linewidth=0.4, zorder=3,
            alpha=1.0, # solid vibrant colors
        )


def _render_standalone_volume(ax, x_coords: np.ndarray, df: pd.DataFrame):
    """Render volume bars on a standalone subplot."""
    if "Volume" not in df.columns or df["Volume"].sum() == 0:
        return

    bar_width = 0.5
    ax.set_facecolor(CHART_STYLE["bg_color"])

    colors = [
        CHART_STYLE["volume_up"] if row.Close >= row.Open else CHART_STYLE["volume_down"]
        for row in df.itertuples()
    ]

    ax.bar(x_coords, df["Volume"].values, width=bar_width, color=colors, alpha=0.8, zorder=3)
    
    # Add a Volume Moving Average overlay
    if len(df) >= 20:
        vol_sma = df["Volume"].rolling(window=20).mean()
        ax.plot(x_coords, vol_sma.values, color="#FF9800", linewidth=1.2, alpha=0.9, zorder=4, label="Vol SMA(20)")
        # Small legend for the Volume SMA
        ax.legend(loc="upper left", frameon=True, fontsize=7, 
                  facecolor=CHART_STYLE["bg_color"], edgecolor=CHART_STYLE["grid_color"], labelcolor="white")


def _render_overlays(ax, x_coords: np.ndarray, overlays: list):
    """Render EMA, SMA, BBANDS etc. as line overlays on the price chart."""
    for name, series, color in overlays:
        valid = series.dropna()
        if len(valid) > 0:
            # Match coordinates
            ax.plot(
                x_coords[-len(series):], series.values,
                color=color, linewidth=1.2, alpha=0.85,
                label=name, zorder=4,
            )


def _render_suggested_levels(ax, x_coords: np.ndarray, df: pd.DataFrame, entry, stop, target):
    """Plot horizontal lines for Entry, Stop Loss, and Target levels."""
    if not (entry or stop or target):
        return

    # Extend slightly to the right for labels
    label_x = x_coords[-1] + len(x_coords) * 0.02
    
    levels = [
        (entry, "ENTRY", CHART_STYLE["entry_line"], "-"),
        (stop, "STOP LOSS", CHART_STYLE["stop_line"], "--"),
        (target, "TARGET", CHART_STYLE["target_line"], "-."),
    ]
    
    for val, label, color, ls in levels:
        if val and val > 0:
            ax.axhline(y=val, color=color, linestyle=ls, linewidth=2.0, alpha=0.9, zorder=5)
            # Add text label with a small background box for readability
            ax.text(
                label_x, val, f" {label}: {val:.2f}",
                color=color, fontsize=10, fontweight="bold",
                va="center", ha="left",
                bbox=dict(facecolor=CHART_STYLE["bg_color"], alpha=0.8, edgecolor=color, pad=2)
            )


def _render_summary_header(ax, df, indicators, ltp):
    """Render a single-line summary of OHLCV and indicators at the top of the chart."""
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    
    change = last["Close"] - prev["Close"]
    pct_change = (change / prev["Close"]) * 100 if prev["Close"] != 0 else 0
    
    color = CHART_STYLE["candle_up"] if change >= 0 else CHART_STYLE["candle_down"]
    sign = "+" if change >= 0 else ""
    
    # 1. Price Header (Top Left)
    price_str = (
        f"O: {last['Open']:.2f}  H: {last['High']:.2f}  L: {last['Low']:.2f}  C: {last['Close']:.2f}  "
        f"({sign}{pct_change:.2f}%)  V: {int(last['Volume']):,}"
    )
    
    ax.text(
        0.01, 0.98, price_str,
        transform=ax.transAxes,
        fontsize=9, color=color,
        va="top", ha="left",
        fontweight="bold",
        zorder=10
    )
    
    # 2. Indicator Values (below price)
    ind_parts = []
    if indicators["rsi"] is not None:
        ind_parts.append(f"RSI: {indicators['rsi'].iloc[-1]:.1f}")
    if indicators["macd"] is not None:
        macd_val, sig_val, hist_val = indicators["macd"]
        ind_parts.append(f"MACD: {macd_val.iloc[-1]:.2f}")
    
    if ind_parts:
        ax.text(
            0.01, 0.93, " | ".join(ind_parts),
            transform=ax.transAxes,
            fontsize=8, color=CHART_STYLE["text_color"],
            va="top", ha="left",
            alpha=0.8,
            zorder=10
        )


def _render_rsi(ax, x_coords: np.ndarray, rsi_series: pd.Series):
    """Render RSI indicator subplot."""
    valid = rsi_series.dropna()
    if len(valid) == 0:
        return

    # Match coordinates
    plot_x = x_coords[-len(rsi_series):]
    
    ax.set_facecolor(CHART_STYLE["bg_color"])
    ax.plot(plot_x, rsi_series.values, color=CHART_STYLE["rsi_line"], linewidth=1.2, zorder=3)

    # Overbought / Oversold zones
    ax.axhline(70, color=CHART_STYLE["rsi_ob"], linewidth=0.7, linestyle="--", alpha=0.6)
    ax.axhline(30, color=CHART_STYLE["rsi_os"], linewidth=0.7, linestyle="--", alpha=0.6)
    ax.axhline(50, color=CHART_STYLE["text_color"], linewidth=0.5, linestyle=":", alpha=0.3)

    # Fill overbought/oversold regions
    ax.fill_between(
        plot_x, rsi_series.values, 70,
        where=(rsi_series.values > 70),
        color=CHART_STYLE["rsi_fill_ob"], alpha=0.5, interpolate=True, zorder=2,
    )
    ax.fill_between(
        plot_x, rsi_series.values, 30,
        where=(rsi_series.values < 30),
        color=CHART_STYLE["rsi_fill_os"], alpha=0.5, interpolate=True, zorder=2,
    )

    ax.set_ylim(0, 100)
    ax.set_ylabel("RSI", fontsize=8, color=CHART_STYLE["text_color"])
    ax.tick_params(colors=CHART_STYLE["text_color"], labelsize=7)
    ax.grid(True, color=CHART_STYLE["grid_color"], alpha=0.3, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_color(CHART_STYLE["grid_color"])
    ax.spines["left"].set_color(CHART_STYLE["grid_color"])
    ax.spines["bottom"].set_color(CHART_STYLE["grid_color"])

    # Latest value annotation
    latest_val = rsi_series.values[-1]
    if not np.isnan(latest_val):
        label_color = CHART_STYLE["rsi_ob"] if latest_val > 70 else CHART_STYLE["rsi_os"] if latest_val < 30 else CHART_STYLE["rsi_line"]
        ax.text(
            plot_x[-1], latest_val, f"  {latest_val:.1f}",
            color=label_color, fontsize=8, fontweight="bold", va="center",
        )


def _render_macd(ax, x_coords: np.ndarray, macd: pd.Series, signal: pd.Series, hist: pd.Series):
    """Render MACD indicator subplot."""
    if len(macd) == 0:
        return

    # Match coordinates
    plot_x = x_coords[-len(macd):]
    
    ax.set_facecolor(CHART_STYLE["bg_color"])

    # Histogram bars
    bar_width = 0.6
    colors = [
        CHART_STYLE["macd_hist_pos"] if v >= 0 else CHART_STYLE["macd_hist_neg"]
        for v in hist.values
    ]
    ax.bar(plot_x, hist.values, width=bar_width, color=colors, zorder=1)

    # MACD and Signal lines
    ax.plot(plot_x, macd.values, color=CHART_STYLE["macd_line"], linewidth=1.2, label="MACD", zorder=3)
    ax.plot(plot_x, signal.values, color=CHART_STYLE["macd_signal"], linewidth=1.0, label="Signal", zorder=3)

    ax.axhline(0, color=CHART_STYLE["text_color"], linewidth=0.5, linestyle=":", alpha=0.3)
    ax.set_ylabel("MACD", fontsize=8, color=CHART_STYLE["text_color"])
    ax.tick_params(colors=CHART_STYLE["text_color"], labelsize=7)
    ax.grid(True, color=CHART_STYLE["grid_color"], alpha=0.3, linewidth=0.5)
    ax.legend(
        loc="upper left", fontsize=6,
        facecolor=CHART_STYLE["bg_color"],
        edgecolor=CHART_STYLE["grid_color"],
        labelcolor=CHART_STYLE["text_color"],
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_color(CHART_STYLE["grid_color"])
    ax.spines["left"].set_color(CHART_STYLE["grid_color"])
    ax.spines["bottom"].set_color(CHART_STYLE["grid_color"])


def _render_atr(ax, x_coords: np.ndarray, atr_series: pd.Series):
    """Render ATR indicator subplot."""
    if len(atr_series) == 0:
        return

    # Match coordinates
    plot_x = x_coords[-len(atr_series):]

    ax.set_facecolor(CHART_STYLE["bg_color"])
    ax.fill_between(plot_x, 0, atr_series.values, color=CHART_STYLE["atr_line"], alpha=0.2, zorder=1)
    ax.plot(plot_x, atr_series.values, color=CHART_STYLE["atr_line"], linewidth=1.2, zorder=3)

    ax.set_ylabel("ATR", fontsize=8, color=CHART_STYLE["text_color"])
    ax.tick_params(colors=CHART_STYLE["text_color"], labelsize=7)
    ax.grid(True, color=CHART_STYLE["grid_color"], alpha=0.3, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_color(CHART_STYLE["grid_color"])
    ax.spines["left"].set_color(CHART_STYLE["grid_color"])
    ax.spines["bottom"].set_color(CHART_STYLE["grid_color"])

    # Latest value
    latest_val = atr_series.values[-1]
    if not np.isnan(latest_val):
        ax.text(
            plot_x[-1], latest_val, f"  {latest_val:.2f}",
            color=CHART_STYLE["atr_line"], fontsize=8, fontweight="bold", va="center",
        )
