"""Scoring engine — pure rule-based multi-factor analysis for stock tradability."""

import json
import time
import math


def _parse_sentiment(raw_analysis_data) -> tuple[str, float]:
    """Extract sentiment direction and confidence from raw_analysis_data."""
    if not raw_analysis_data:
        return "neutral", 0.5

    data = raw_analysis_data
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return "neutral", 0.5

    sentiment = data.get("sentiment", "neutral") if isinstance(data, dict) else "neutral"
    confidence = data.get("confidence", 0.5) if isinstance(data, dict) else 0.5
    return sentiment, confidence


def _recency_weight(published_at_ms: int) -> float:
    """Weight based on how recent the article is from now."""
    now_ms = int(time.time() * 1000)
    age_hours = (now_ms - published_at_ms) / 3_600_000

    if age_hours < 4:
        return 1.0
    elif age_hours < 12:
        return 0.7
    elif age_hours < 18:
        return 0.4
    else:
        return 0.2


def _category_boost(category: str) -> float:
    """Multiplier based on news category importance."""
    boosts = {
        "earnings": 1.20,
        "regulatory": 1.15,
        "product": 1.10,
        "merger": 1.15,
        "macro": 1.05,
    }
    return boosts.get(category, 1.0)


def calculate_news_score(articles: list[dict]) -> tuple[float, dict]:
    """
    Calculate news sentiment score for a symbol.
    Returns (score 0-100, breakdown dict).
    """
    if not articles:
        return 0.0, {"reason": "No news articles found", "article_count": 0}

    article_scores = []
    sentiments = []
    details = []

    for art in articles:
        sentiment, confidence = _parse_sentiment(art.get("raw_analysis_data"))
        impact = float(art.get("impact_score", 5.0)) / 10.0  # normalize to 0-1
        recency = _recency_weight(art.get("published_at", 0))
        cat_boost = _category_boost(art.get("news_category", ""))

        # Direction: bullish=1, bearish=-1, neutral=0
        direction = 1 if sentiment == "bullish" else (-1 if sentiment == "bearish" else 0)
        sentiments.append(direction)

        # Raw article contribution (absolute value for scoring, direction for signal)
        raw = abs(direction) * impact * confidence * recency * cat_boost
        article_scores.append(raw)

        details.append({
            "title": art.get("title", "")[:80],
            "sentiment": sentiment,
            "impact": round(impact * 10, 1),
            "confidence": round(confidence, 2),
            "recency": round(recency, 2),
            "contribution": round(raw * 100, 1),
        })

    avg_score = sum(article_scores) / len(article_scores) if article_scores else 0
    cluster_mult = min(1.3, 1.0 + (len(articles) - 1) * 0.1) if len(articles) > 1 else 1.0
    final = min(100, avg_score * cluster_mult * 100)

    net_sentiment = sum(sentiments)
    dominant = "bullish" if net_sentiment > 0 else ("bearish" if net_sentiment < 0 else "neutral")

    return round(final, 1), {
        "article_count": len(articles),
        "dominant_sentiment": dominant,
        "net_sentiment_score": net_sentiment,
        "cluster_multiplier": round(cluster_mult, 2),
        "top_articles": details[:5],
    }


def calculate_price_score(stock_data: dict) -> tuple[float, dict]:
    """
    Calculate price action score from Groww stock data.
    Returns (score 0-100, breakdown dict).
    """
    breakdown = {}

    # 1. Gap Signal
    gap = abs(stock_data.get("gap_percentage") or 0)
    if gap > 3:
        gap_signal = 100
    elif gap > 2:
        gap_signal = 80
    elif gap > 1:
        gap_signal = 60
    elif gap > 0.5:
        gap_signal = 40
    else:
        gap_signal = 20
    breakdown["gap_pct"] = round(stock_data.get("gap_percentage") or 0, 2)
    breakdown["gap_signal"] = gap_signal

    # 2. Volume Signal
    vol = stock_data.get("current_volume") or 0
    if vol > 50_000_000:
        vol_signal = 100
    elif vol > 10_000_000:
        vol_signal = 80
    elif vol > 5_000_000:
        vol_signal = 60
    elif vol > 1_000_000:
        vol_signal = 40
    else:
        vol_signal = 20
    breakdown["volume"] = vol
    breakdown["volume_signal"] = vol_signal

    # 3. 52-Week Range Position
    w52_high = stock_data.get("52_week_high") or 0
    w52_low = stock_data.get("52_week_low") or 0
    last_close = stock_data.get("last_close") or 0
    if w52_high > w52_low and last_close > 0:
        range_pos = (last_close - w52_low) / (w52_high - w52_low) * 100
        if range_pos > 90:
            pos_signal = 70  # momentum play
        elif range_pos < 10:
            pos_signal = 65  # value play
        elif range_pos > 70:
            pos_signal = 60
        else:
            pos_signal = 40
    else:
        range_pos = 50
        pos_signal = 40
    breakdown["52w_range_position"] = round(range_pos, 1)
    breakdown["position_signal"] = pos_signal

    # 4. Intraday Volatility
    today_high = stock_data.get("today_high") or 0
    today_low = stock_data.get("today_low") or 0
    if last_close > 0 and today_high > 0 and today_low > 0:
        volatility = (today_high - today_low) / last_close * 100
    else:
        volatility = 0

    if volatility > 3:
        vol_sig = 100
    elif volatility > 2:
        vol_sig = 80
    elif volatility > 1:
        vol_sig = 60
    else:
        vol_sig = 40
    breakdown["day_volatility_pct"] = round(volatility, 2)
    breakdown["volatility_signal"] = vol_sig

    final = (gap_signal + vol_signal + pos_signal + vol_sig) / 4
    return round(final, 1), breakdown


def calculate_feasibility_score(stock_data: dict) -> tuple[float, dict]:
    """
    Calculate trade feasibility score.
    Returns (score 0-100, breakdown dict).
    """
    breakdown = {}

    # 1. Liquidity
    vol = stock_data.get("current_volume") or 0
    if vol > 500_000:
        liq = 100
    elif vol > 100_000:
        liq = 60
    else:
        liq = 20
    breakdown["liquidity"] = liq

    # 2. Spread (using day range as proxy)
    last_close = stock_data.get("last_close") or 0
    today_high = stock_data.get("today_high") or 0
    today_low = stock_data.get("today_low") or 0
    if last_close > 0 and today_high > 0:
        spread = (today_high - today_low) / last_close * 100
        spread_score = 80 if spread > 1.0 else 40
    else:
        spread = 0
        spread_score = 40
    breakdown["spread_pct"] = round(spread, 2)
    breakdown["spread_score"] = spread_score

    # 3. Price actionability (not penny stock)
    if last_close > 100:
        price_score = 90
    elif last_close > 50:
        price_score = 70
    elif last_close > 10:
        price_score = 50
    else:
        price_score = 20
    breakdown["price_quality"] = price_score

    # 4. Capital fit (generic — configurable later)
    breakdown["capital_fit"] = 80

    final = (liq + spread_score + price_score + 80) / 4
    return round(final, 1), breakdown


def determine_signal_type(composite: float, dominant_sentiment: str) -> str:
    """Determine BUY/SELL/HOLD based on composite score and sentiment."""
    if composite >= 55:
        if dominant_sentiment == "bullish":
            return "BUY"
        elif dominant_sentiment == "bearish":
            return "SELL"
        else:
            return "HOLD"
    elif composite >= 35:
        return "HOLD"
    else:
        return "NO_TRADE"


def classify_trade_mode(articles: list[dict], stock_data: dict) -> str:
    """Classify whether the trade should be INTRADAY or DELIVERY."""
    intraday_score = 0
    delivery_score = 0

    # Factor 1: News recency
    now_ms = int(time.time() * 1000)
    recent_count = sum(1 for a in articles if (now_ms - a.get("published_at", 0)) < 12 * 3_600_000)
    if recent_count > len(articles) * 0.5:
        intraday_score += 2
    else:
        delivery_score += 2

    # Factor 2: Gap percentage
    gap = abs(stock_data.get("gap_percentage") or 0)
    if gap > 1:
        intraday_score += 2
    else:
        delivery_score += 1

    # Factor 3: Volume
    vol = stock_data.get("current_volume") or 0
    if vol > 5_000_000:
        intraday_score += 1

    # Factor 4: News category
    categories = [a.get("news_category", "") for a in articles]
    if "earnings" in categories or "product" in categories:
        intraday_score += 1
    if "macro" in categories or "regulatory" in categories:
        delivery_score += 1

    # Factor 5: Volatility
    last_close = stock_data.get("last_close") or 0
    today_high = stock_data.get("today_high") or 0
    today_low = stock_data.get("today_low") or 0
    if last_close > 0:
        day_range = (today_high - today_low) / last_close * 100
        if day_range > 2:
            intraday_score += 1
        else:
            delivery_score += 1

    return "INTRADAY" if intraday_score >= delivery_score else "DELIVERY"


def calculate_levels(stock_data: dict, signal_type: str) -> dict:
    """Calculate entry, stop-loss, and target levels."""
    last_close = stock_data.get("last_close") or 0
    today_open = stock_data.get("today_open") or last_close
    today_high = stock_data.get("today_high") or today_open
    today_low = stock_data.get("today_low") or today_open
    past_day_high = stock_data.get("past_day_high") or today_high
    past_day_low = stock_data.get("past_day_low") or today_low

    if signal_type == "BUY":
        entry = round(today_open, 2)
        sl = round(min(today_low, past_day_low) * 0.998, 2)  # just below support
        risk = entry - sl
        target = round(entry + risk * 2.0, 2)  # 1:2 R:R minimum
    elif signal_type == "SELL":
        entry = round(today_open, 2)
        sl = round(max(today_high, past_day_high) * 1.002, 2)  # just above resistance
        risk = sl - entry
        target = round(entry - risk * 2.0, 2)  # 1:2 R:R minimum
    else:
        entry = round(today_open, 2)
        sl = round(today_low * 0.99, 2)
        target = round(today_high * 1.01, 2)
        risk = abs(entry - sl) if entry != sl else 1

    rr = round(abs(target - entry) / risk, 2) if risk > 0 else 0

    return {
        "entry_price": entry,
        "stop_loss": sl,
        "target_price": target,
        "risk_reward": rr,
    }
