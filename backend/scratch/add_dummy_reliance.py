"""
Inject a dummy RELIANCE signal into the pipeline for end-to-end testing.
Uses current market data (2026-04-27).

Usage (from backend/ dir):
    python .\scratch\add_dummy_reliance.py
    python .\scratch\run_agent2.py --debug    # then trigger Agent 2
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from database import SessionLocal
import db_models

IST = timezone(timedelta(hours=5, minutes=30))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _market_date() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


# ── Current RELIANCE data (2026-04-27) ────────────────────────────────────────
# Jio IPO + ₹50,000 Cr Buyback catalyst
# Price: gapped down ~1.2% at open, recovered to near-flat, holding ₹1340–1350 zone

SYMBOL = "RELIANCE"
MARKET_DATE = _market_date()

STOCK_SNAPSHOT = {
    "previous_close": 1361.35,
    "last_close":     1349.60,          # current LTP
    "ltp":            1349.60,
    "open_price":     1330.00,          # gapped down at open
    "today_open":     1330.00,          # same as open_price — Agent 2 reads this
    "today_high":     1355.00,
    "today_low":      1326.50,
    "high":           1355.00,
    "low":            1326.50,
    "volume":         12_500_000,
    "avg_volume":     8_200_000,
    "avg_volume_20d": 8_200_000,        # Agent 2 uses this for volume_ratio calc
    "volume_ratio":   1.52,
    "gap_percent":    -2.15,            # gap-down at open
    "gap_direction":  "DOWN",
    "move_from_open": 1.48,             # recovered +1.48% from open low
    "vwap":           1341.20,
    "support_level":  1330.0,
    "resistance_level": 1365.0,
    "market_cap":     "18.2L Cr",
    "sector":         "Diversified",
    "exchange":       "NSE",
}

AGENT_1_REASONING = (
    "Reliance Industries announced the Jio IPO filing date and a Rs.50,000 Cr share buyback at premium. "
    "This is a dual catalyst -- structural (IPO unlocking Jio value) and near-term (buyback price support). "
    "Initial market reaction was a sell-the-news gap-down, but strong institutional dip-buying is evident "
    "with price recovering nearly 1.5% from the opening low. V-shaped recovery pattern forming with "
    "above-average volume confirming institutional interest. BULLISH thesis intact."
)

REASONING_COMBINED_VIEW = {
    "final_bias": "BULLISH",
    "final_confidence": "HIGH",
    "main_driver": "Jio IPO date announcement + Rs.50,000 Cr buyback at premium",
    "executive_summary": "Reliance announced Jio IPO date and a Rs.50,000 Cr share buyback at a premium.",
    "combined_trading_thesis": (
        "Price gapped down ~2.15% at open on 'sell the news' pressure but is showing a strong V-shaped "
        "recovery. Current LTP Rs.1349.60 is trading above VWAP (Rs.1341.20) and closing in on the daily high. "
        "Volume (1.52x avg) confirms institutional accumulation. The buyback provides a price floor near "
        "Rs.1330 making risk well-defined. Bullish momentum expected to continue into the day."
    ),
    "combined_invalidation": (
        "Break and close below Rs.1326.50 (day low) with rising volume would invalidate the V-shape recovery thesis."
    ),
    "key_risks": [
        "Broader market sell-off dragging the stock",
        "Buyback price significantly below current market -- reducing floor support",
        "Nifty 50 weakness during high-beta risk-off session",
    ],
    "supporting_points": [
        "Jio IPO unlocks significant hidden value",
        "Rs.50,000 Cr buyback provides strong price floor",
        "V-shaped recovery on above-average volume",
        "Price reclaimed VWAP -- institutional conviction signal",
    ],
    "reasoning": AGENT_1_REASONING,
}


def inject():
    db = SessionLocal()
    try:
        now_ms = _now_ms()
        sig_id = f"sig-{SYMBOL}-{MARKET_DATE}-{uuid.uuid4().hex[:6]}"

        # ── News Article ──────────────────────────────────────────────────────
        article_id = f"news-dummy-reliance-{MARKET_DATE}"
        existing_news = db.query(db_models.NewsArticle).filter(
            db_models.NewsArticle.id == article_id
        ).first()
        if not existing_news:
            article = db_models.NewsArticle(
                id=article_id,
                title="RELIANCE INDUSTRIES ANNOUNCES JIO IPO DATE AND MASSIVE SHARE BUYBACK",
                description=(
                    "Reliance Industries has announced the Jio IPO filing date along with a Rs.50,000 Crore "
                    "share buyback programme at a premium to current market price, creating significant "
                    "value for shareholders."
                ),
                source="BSE",
                link="https://bse.india.com/reliance-jio-ipo-buyback-2026",
                published_at=now_ms - 3600_000,  # 1hr ago
                impact_score=9.0,
                affected_symbols=[SYMBOL],
                news_category="CORPORATE_ACTION",
                market_bias="BULLISH",
                signal_bucket="HIGH_IMPACT",
                primary_symbol=SYMBOL,
                processing_status="analyzed",
                confidence=90,           # INTEGER column
                horizon="INTRADAY",
            )
            db.add(article)
            db.commit()
            print(f"[OK] Created news article: {article_id}")
        else:
            print(f"[SKIP] News article already exists: {article_id}")

        # ── Trade Signal ──────────────────────────────────────────────────────
        signal = db_models.DBTradeSignal(
            id=sig_id,
            symbol=SYMBOL,
            signal_type="BUY",
            confidence=99,
            status="pending_execution",
            confirmation_status="pending",   # Agent 2 will pick this up
            execution_status="pending",
            market_date=MARKET_DATE,
            generated_at=now_ms,
            news_article_ids=[article_id],
            agent_1_reasoning=AGENT_1_REASONING,
            reasoning={"combined_view": REASONING_COMBINED_VIEW},
            stock_snapshot=STOCK_SNAPSHOT,
            trade_mode="INTRADAY",
        )
        db.add(signal)
        db.commit()

        print(f"[OK] Created Agent 1 signal: {sig_id}")
        print(f"     Symbol:  {SYMBOL}")
        print(f"     Date:    {MARKET_DATE}")
        print(f"     LTP:     Rs.{STOCK_SNAPSHOT['ltp']}")
        print(f"     Bias:    BULLISH | Confidence: HIGH")
        print(f"     Status:  confirmation_status=pending -> Agent 2 will process next")
        print()
        print("Next step: python .\\scratch\\run_agent2.py --debug")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    inject()
