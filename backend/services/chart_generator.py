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
    "bg_color": "#1a1a2e",
    "text_color": "#e0e0e0",
    "grid_color": "#2a2a4a",
    "candle_up": "#00e676",
    "candle_down": "#ff1744",
    "candle_up_edge": "#00c853",
    "candle_down_edge": "#d50000",
    "volume_up": "#00e67640",
    "volume_down": "#ff174440",
    "ema_color": "#ffab00",
    "sma_color": "#2979ff",
    "vwap_color": "#e040fb",
    "bb_upper": "#ff6f00",
    "bb_lower": "#ff6f00",
    "bb_fill": "#ff6f0015",
    "rsi_line": "#00e5ff",
    "rsi_ob": "#ff1744",
    "rsi_os": "#00e676",
    "rsi_fill_ob": "#ff174420",
    "rsi_fill_os": "#00e67620",
    "macd_line": "#00e5ff",
    "macd_signal": "#ff6f00",
    "macd_hist_pos": "#00e67660",
    "macd_hist_neg": "#ff174460",
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
        start_ms = now_ms - int(60 * count * 5 * 1000)

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


def _candles_to_dataframe(candles: list) -> pd.DataFrame:
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
        name = str(req.get("name", "")).upper().strip()

        try:
            if name in ("EMA",):
                period = int(req.get("period", 20))
                vals = talib.EMA(closes, timeperiod=period) if use_talib else _np_ema(closes, period)
                series = pd.Series(vals, index=df.index, name=f"EMA({period})")
                result["overlays"].append((f"EMA({period})", series, CHART_STYLE["ema_color"]))

            elif name in ("SMA",):
                period = int(req.get("period", 20))
                vals = talib.SMA(closes, timeperiod=period) if use_talib else _np_sma(closes, period)
                series = pd.Series(vals, index=df.index, name=f"SMA({period})")
                result["overlays"].append((f"SMA({period})", series, CHART_STYLE["sma_color"]))

            elif name == "RSI":
                period = int(req.get("period", 14))
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
                period = int(req.get("period", 14))
                vals = talib.ATR(highs, lows, closes, timeperiod=period) if use_talib else _np_atr(highs, lows, closes, period)
                result["atr"] = pd.Series(vals, index=df.index, name=f"ATR({period})")

            elif name == "BBANDS":
                period = int(req.get("period", 20))
                if use_talib:
                    upper, middle, lower = talib.BBANDS(closes, timeperiod=period)
                else:
                    upper, middle, lower = _np_bbands(closes, period)
                result["overlays"].append(("BB Upper", pd.Series(upper, index=df.index), CHART_STYLE["bb_upper"]))
                result["overlays"].append(("BB Lower", pd.Series(lower, index=df.index), CHART_STYLE["bb_lower"]))
                result["overlays"].append(("BB Mid", pd.Series(middle, index=df.index), CHART_STYLE["sma_color"]))

            elif name in ("WMA",):
                period = int(req.get("period", 20))
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

    # 2. Fetch candle data
    candles = _fetch_candles_for_chart(symbol, interval, count=60)
    if not candles or len(candles) < 10:
        print(f"  [CHART] Not enough candle data for {symbol} (got {len(candles)})")
        return None

    df = _candles_to_dataframe(candles)

    # 3. Compute indicators
    indicators = _compute_indicators_for_chart(df, requested_indicators)

    # 4. Determine subplot layout
    has_rsi = indicators["rsi"] is not None
    has_macd = indicators["macd"] is not None
    has_atr = indicators["atr"] is not None

    n_subplots = 1 + int(has_rsi) + int(has_macd) + int(has_atr)
    
    # Height ratios: price panel gets most space, indicator panels are smaller
    height_ratios = [4]  # Price panel
    if has_rsi:
        height_ratios.append(1.2)
    if has_macd:
        height_ratios.append(1.2)
    if has_atr:
        height_ratios.append(1.0)

    total_height = sum(height_ratios) * 1.8 + 1  # Scale factor

    # 5. Create figure with dark theme
    fig, axes = plt.subplots(
        n_subplots, 1,
        figsize=(CHART_WIDTH, total_height),
        gridspec_kw={"height_ratios": height_ratios, "hspace": 0.08},
        squeeze=False,
    )
    axes = axes.flatten()

    fig.patch.set_facecolor(CHART_STYLE["bg_color"])

    # ── PRICE PANEL (axes[0]) ──────────────────────────────────────────
    ax_price = axes[0]
    _render_candlestick(ax_price, df)
    _render_volume_bars(ax_price, df)
    _render_overlays(ax_price, indicators["overlays"])
    _render_suggested_levels(ax_price, df, entry_suggestion, stop_suggestion, target_suggestion)

    # Annotate LTP (only if within visible range of candle data)
    if ltp and ltp > 0:
        price_min = df["Low"].min()
        price_max = df["High"].max()
        price_range = price_max - price_min
        # Only show LTP line if it's within 30% of the visible price range
        if price_min - price_range * 0.3 <= ltp <= price_max + price_range * 0.3:
            ax_price.axhline(
                y=ltp, color=CHART_STYLE["ltp_line"], linewidth=0.8,
                linestyle="--", alpha=0.7
            )
            ax_price.text(
                df.index[-1], ltp, f"  LTP Rs.{ltp:.2f}",
                color=CHART_STYLE["ltp_line"], fontsize=8, fontweight="bold",
                va="center",
            )

    # Style price axis
    ax_price.set_facecolor(CHART_STYLE["bg_color"])
    ax_price.tick_params(colors=CHART_STYLE["text_color"], labelsize=7)
    ax_price.grid(True, color=CHART_STYLE["grid_color"], alpha=0.3, linewidth=0.5)
    ax_price.spines["top"].set_visible(False)
    ax_price.spines["right"].set_color(CHART_STYLE["grid_color"])
    ax_price.spines["left"].set_color(CHART_STYLE["grid_color"])
    ax_price.spines["bottom"].set_color(CHART_STYLE["grid_color"])

    # Title
    dir_label = f" | {direction}" if direction else ""
    ax_price.set_title(
        f"  {symbol}  •  {tf_label} Chart  •  {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}{dir_label}",
        fontsize=14, fontweight="bold", color=CHART_STYLE["text_color"],
        loc="left", pad=20,
    )

    # Add Summary Stats Box (Top Right)
    _render_summary_box(ax_price, df, indicators, ltp)

    # Legend for overlays
    if indicators["overlays"]:
        ax_price.legend(
            loc="upper left", fontsize=7,
            facecolor=CHART_STYLE["bg_color"],
            edgecolor=CHART_STYLE["grid_color"],
            labelcolor=CHART_STYLE["text_color"],
        )

    # ── INDICATOR SUBPLOTS ─────────────────────────────────────────────
    subplot_idx = 1

    if has_rsi:
        _render_rsi(axes[subplot_idx], indicators["rsi"])
        subplot_idx += 1

    if has_macd:
        macd_line, signal_line, hist = indicators["macd"]
        _render_macd(axes[subplot_idx], macd_line, signal_line, hist)
        subplot_idx += 1

    if has_atr:
        _render_atr(axes[subplot_idx], indicators["atr"])
        subplot_idx += 1

    # Format x-axis on the bottom-most panel
    bottom_ax = axes[n_subplots - 1]
    bottom_ax.tick_params(axis="x", colors=CHART_STYLE["text_color"], labelsize=8, rotation=30)
    
    # Force more x-axis ticks to ensure time is visible
    bottom_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=12))

    # Hide x-tick labels on all panels except the bottom
    for i in range(n_subplots - 1):
        axes[i].tick_params(axis="x", labelbottom=False)

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

def _render_candlestick(ax, df: pd.DataFrame):
    """Draw candlestick bodies and wicks on the given axes."""
    # Convert datetime index to numeric for plotting
    dates = mdates.date2num(df.index.to_pydatetime())
    
    # Auto-calculate candle width based on data density
    if len(dates) > 1:
        avg_gap = np.mean(np.diff(dates))
        candle_width = avg_gap * 0.6
    else:
        candle_width = 0.0005

    for i, (dt_num, row) in enumerate(zip(dates, df.itertuples())):
        o, h, l, c = row.Open, row.High, row.Low, row.Close

        if c >= o:
            color = CHART_STYLE["candle_up"]
            edge = CHART_STYLE["candle_up_edge"]
        else:
            color = CHART_STYLE["candle_down"]
            edge = CHART_STYLE["candle_down_edge"]

        # Wick (high-low line)
        ax.plot([dt_num, dt_num], [l, h], color=edge, linewidth=0.8, zorder=2)

        # Body
        body_bottom = min(o, c)
        body_height = abs(c - o) if abs(c - o) > 0 else h * 0.001

        ax.bar(
            dt_num, body_height, bottom=body_bottom, width=candle_width,
            color=color, edgecolor=edge, linewidth=0.5, zorder=3,
            alpha=0.9,
        )

    ax.xaxis_date()
    # Smart date formatting: detect daily vs intraday from actual data gaps
    if len(dates) > 1:
        avg_gap_hours = np.mean(np.diff(dates)) * 24  # gap in hours
        if avg_gap_hours > 12:  # Daily candles (gap > 12 hours)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        else:  # Intraday candles
            # Show date if chart covers more than one day
            if df.index[0].date() != df.index[-1].date():
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M"))
            else:
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M"))


def _render_volume_bars(ax, df: pd.DataFrame):
    """Render volume bars as a subtle overlay at the bottom of the price panel."""
    if "Volume" not in df.columns or df["Volume"].sum() == 0:
        return

    dates = mdates.date2num(df.index.to_pydatetime())
    
    if len(dates) > 1:
        avg_gap = np.mean(np.diff(dates))
        bar_width = avg_gap * 0.5
    else:
        bar_width = 0.0004

    # Create a twin axis for volume
    ax_vol = ax.twinx()

    max_vol = df["Volume"].max() if df["Volume"].max() > 0 else 1
    # Scale volume to occupy ~20% of the price panel height
    price_range = df["High"].max() - df["Low"].min()
    vol_scale = (price_range * 0.2) / max_vol

    for dt_num, row in zip(dates, df.itertuples()):
        color = CHART_STYLE["volume_up"] if row.Close >= row.Open else CHART_STYLE["volume_down"]
        ax_vol.bar(
            dt_num, row.Volume, width=bar_width,
            color=color, alpha=0.4, zorder=1,
        )

    ax_vol.set_ylim(0, max_vol * 5)  # Push volume bars to bottom
    ax_vol.set_yticks([])
    ax_vol.set_yticklabels([])
    for spine in ax_vol.spines.values():
        spine.set_visible(False)


def _render_overlays(ax, overlays: list):
    """Render EMA, SMA, BBANDS etc. as line overlays on the price chart."""
    for name, series, color in overlays:
        valid = series.dropna()
        if len(valid) > 0:
            dates = mdates.date2num(valid.index.to_pydatetime())
            ax.plot(
                dates, valid.values,
                color=color, linewidth=1.2, alpha=0.85,
                label=name, zorder=4,
            )


def _render_suggested_levels(ax, df, entry, stop, target):
    """Plot horizontal lines for Entry, Stop Loss, and Target levels."""
    if not (entry or stop or target):
        return

    x_min, x_max = ax.get_xlim()
    # Extend slightly to the right for labels
    label_x = df.index[-1] + (df.index[-1] - df.index[0]) * 0.05
    
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


def _render_summary_box(ax, df, indicators, ltp):
    """Add a semi-transparent summary box with latest data points."""
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    change = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
    change_color = CHART_STYLE["candle_up"] if change >= 0 else CHART_STYLE["candle_down"]
    
    # Build summary text
    lines = [
        f"LATEST CANDLE ({df.index[-1].strftime('%H:%M')})",
        f"  O: {latest['Open']:.2f}  H: {latest['High']:.2f}",
        f"  L: {latest['Low']:.2f}  C: {latest['Close']:.2f}",
        f"  Change: {change:+.2f}%",
        f"  Volume: {latest['Volume']:,}",
        "",
        "INDICATORS:",
    ]
    
    # Add indicator values
    for name, series, color in indicators["overlays"]:
        val = series.iloc[-1]
        if not np.isnan(val):
            lines.append(f"  {name}: {val:.2f}")
            
    if indicators["rsi"] is not None:
        rsi_val = indicators["rsi"].iloc[-1]
        if not np.isnan(rsi_val):
            lines.append(f"  RSI: {rsi_val:.1f}")
            
    if indicators["macd"] is not None:
        m, s, h = indicators["macd"]
        m_val = m.iloc[-1]
        if not np.isnan(m_val):
            lines.append(f"  MACD: {m_val:.2f}")

    summary_text = "\n".join(lines)
    
    # Position box in the top right (in axes coordinates)
    ax.text(
        0.98, 0.96, summary_text,
        transform=ax.transAxes,
        fontsize=9, color=CHART_STYLE["text_color"],
        va="top", ha="right",
        fontfamily="monospace",
        bbox=dict(
            boxstyle="round,pad=0.8",
            facecolor="#000000",
            edgecolor=CHART_STYLE["grid_color"],
            alpha=0.7,
        ),
        zorder=10
    )


def _render_rsi(ax, rsi_series: pd.Series):
    """Render RSI indicator subplot."""
    valid = rsi_series.dropna()
    if len(valid) == 0:
        return

    dates = mdates.date2num(valid.index.to_pydatetime())
    
    ax.set_facecolor(CHART_STYLE["bg_color"])
    ax.plot(dates, valid.values, color=CHART_STYLE["rsi_line"], linewidth=1.2, zorder=3)

    # Overbought / Oversold zones
    ax.axhline(70, color=CHART_STYLE["rsi_ob"], linewidth=0.7, linestyle="--", alpha=0.6)
    ax.axhline(30, color=CHART_STYLE["rsi_os"], linewidth=0.7, linestyle="--", alpha=0.6)
    ax.axhline(50, color=CHART_STYLE["text_color"], linewidth=0.5, linestyle=":", alpha=0.3)

    # Fill overbought/oversold regions
    ax.fill_between(
        dates, valid.values, 70,
        where=(valid.values > 70),
        color=CHART_STYLE["rsi_fill_ob"], alpha=0.5, interpolate=True, zorder=2,
    )
    ax.fill_between(
        dates, valid.values, 30,
        where=(valid.values < 30),
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
    latest_val = valid.values[-1]
    label_color = CHART_STYLE["rsi_ob"] if latest_val > 70 else CHART_STYLE["rsi_os"] if latest_val < 30 else CHART_STYLE["rsi_line"]
    ax.text(
        dates[-1], latest_val, f"  {latest_val:.1f}",
        color=label_color, fontsize=8, fontweight="bold", va="center",
    )
    ax.xaxis_date()


def _render_macd(ax, macd: pd.Series, signal: pd.Series, hist: pd.Series):
    """Render MACD indicator subplot."""
    valid_macd = macd.dropna()
    valid_signal = signal.dropna()
    valid_hist = hist.dropna()

    if len(valid_macd) == 0:
        return

    ax.set_facecolor(CHART_STYLE["bg_color"])

    # Histogram bars
    if len(valid_hist) > 0:
        dates_h = mdates.date2num(valid_hist.index.to_pydatetime())
        if len(dates_h) > 1:
            bar_width = np.mean(np.diff(dates_h)) * 0.6
        else:
            bar_width = 0.0004

        colors = [
            CHART_STYLE["macd_hist_pos"] if v >= 0 else CHART_STYLE["macd_hist_neg"]
            for v in valid_hist.values
        ]
        ax.bar(dates_h, valid_hist.values, width=bar_width, color=colors, zorder=1)

    # MACD and Signal lines
    dates_m = mdates.date2num(valid_macd.index.to_pydatetime())
    ax.plot(dates_m, valid_macd.values, color=CHART_STYLE["macd_line"], linewidth=1.2, label="MACD", zorder=3)

    if len(valid_signal) > 0:
        dates_s = mdates.date2num(valid_signal.index.to_pydatetime())
        ax.plot(dates_s, valid_signal.values, color=CHART_STYLE["macd_signal"], linewidth=1.0, label="Signal", zorder=3)

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
    ax.xaxis_date()


def _render_atr(ax, atr_series: pd.Series):
    """Render ATR indicator subplot."""
    valid = atr_series.dropna()
    if len(valid) == 0:
        return

    dates = mdates.date2num(valid.index.to_pydatetime())

    ax.set_facecolor(CHART_STYLE["bg_color"])
    ax.fill_between(dates, 0, valid.values, color=CHART_STYLE["atr_line"], alpha=0.2, zorder=1)
    ax.plot(dates, valid.values, color=CHART_STYLE["atr_line"], linewidth=1.2, zorder=3)

    ax.set_ylabel("ATR", fontsize=8, color=CHART_STYLE["text_color"])
    ax.tick_params(colors=CHART_STYLE["text_color"], labelsize=7)
    ax.grid(True, color=CHART_STYLE["grid_color"], alpha=0.3, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_color(CHART_STYLE["grid_color"])
    ax.spines["left"].set_color(CHART_STYLE["grid_color"])
    ax.spines["bottom"].set_color(CHART_STYLE["grid_color"])

    # Latest value
    latest_val = valid.values[-1]
    ax.text(
        dates[-1], latest_val, f"  {latest_val:.2f}",
        color=CHART_STYLE["atr_line"], fontsize=8, fontweight="bold", va="center",
    )
    ax.xaxis_date()
