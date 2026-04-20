from sqlalchemy import Column, String, Integer, Float, BigInteger, JSON, Boolean, ARRAY
from database import Base

class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    description = Column(String, nullable=True)
    source = Column(String)
    published_at = Column(BigInteger)
    analyzed_at = Column(BigInteger, nullable=True)
    image_url = Column(String, nullable=True)
    impact_score = Column(Float, default=0.0)
    impact_summary = Column(String, nullable=True)
    executive_summary = Column(String, nullable=True)
    news_relevance = Column(String, nullable=True)
    news_category = Column(String, nullable=True)
    affected_symbols = Column(ARRAY(String), default=[])
    processing_status = Column(String)
    raw_analysis_data = Column(JSON, nullable=True)

class DBSystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    capital = Column(Float, default=100000.0)
    risk_per_trade_pct = Column(Float, default=1.0)
    max_open_positions = Column(Integer, default=5)
    max_daily_loss_pct = Column(Float, default=3.0)
    min_rr = Column(Float, default=1.5)
    news_endpoint_url = Column(String)
    polling_interval_mins = Column(Integer, default=5)
    processing_mode = Column(String, default="pre_market")

class DBProcessingState(Base):
    __tablename__ = "processing_state"

    id = Column(Integer, primary_key=True, index=True)
    last_processed_article_id = Column(String, nullable=True)
    last_poll_timestamp = Column(BigInteger, default=0)
    total_articles_processed = Column(Integer, default=0)
    current_mode = Column(String, default="pre_market")
    is_polling_active = Column(Boolean, default=False)
    articles_in_queue = Column(Integer, default=0)


class DBTradeSignal(Base):
    __tablename__ = "trade_signals"

    id = Column(String, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    signal_type = Column(String, nullable=False)       # BUY | SELL | HOLD | NO_TRADE
    trade_mode = Column(String, nullable=False)         # INTRADAY | DELIVERY
    entry_price = Column(Float)
    stop_loss = Column(Float)
    target_price = Column(Float)
    risk_reward = Column(Float)
    confidence = Column(Float)
    reasoning = Column(JSON)                            # Gemini reasoning breakdown
    news_article_ids = Column(JSON)                     # List of article IDs used
    stock_snapshot = Column(JSON)                        # Price data at analysis time
    generated_at = Column(BigInteger, nullable=False)
    market_date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    status = Column(String, default="active")           # active | expired | triggered
