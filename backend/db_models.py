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
    # Risk-per-trade controls (Agent 3 position sizing)
    max_loss_per_trade_pct = Column(Float, default=1.0)    # Max % of capital to LOSE per trade (stop width controls this)
    max_capital_per_trade_pct = Column(Float, default=20.0) # Max % of total capital allocated to a single position

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
    status = Column(String, default="pending_confirmation")  # pending_confirmation | confirmed | revised | invalidated

    # -- Market Open Confirmation Agent (Phase 2) columns --
    confirmation_status = Column(String, default="pending")  # pending | confirmed | revised | invalidated
    confirmed_at = Column(BigInteger, nullable=True)          # Timestamp when Agent 2 ran
    confirmation_data = Column(JSON, nullable=True)           # Full Gemini confirmation output

    # -- Execution Agent (Phase 3) columns --
    execution_status = Column(String, default="pending")      # pending | planned | skipped
    executed_at = Column(BigInteger, nullable=True)           # Timestamp when Agent 3 ran
    execution_data = Column(JSON, nullable=True)              # Full Gemini execution plan output

    # -- Risk Monitor Agent (Phase 4) columns --
    risk_monitor_status = Column(String, nullable=True)       # HOLD | HOLD_WITH_CAUTION | TIGHTEN_STOPLOSS | PARTIAL_EXIT | EXIT_NOW
    risk_monitor_data = Column(JSON, nullable=True)           # Full risk monitor output JSON
    risk_last_checked_at = Column(BigInteger, nullable=True)  # Timestamp of last risk check


# ═══════════════════════════════════════════════════════════════════════════════
# PAPER TRADING MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class DBPaperTrade(Base):
    """Paper trade lifecycle — from entry to exit."""
    __tablename__ = "paper_trades"

    id = Column(String, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)               # BUY | SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=False)
    stop_loss = Column(Float, nullable=False)
    target_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    pnl = Column(Float, default=0.0)
    pnl_percentage = Column(Float, default=0.0)
    status = Column(String, default="OPEN", index=True)    # OPEN | CLOSED | CANCELLED
    confidence_score = Column(Float, default=0.0)
    risk_level = Column(String, nullable=True)             # HIGH | MEDIUM | LOW
    trade_reason = Column(String, nullable=True)           # Agent reasoning summary
    exit_reason = Column(String, nullable=True)            # TARGET_HIT | STOP_LOSS_HIT | AGENT_SELL_SIGNAL | MANUAL_EXIT
    signal_id = Column(String, nullable=True, index=True)  # FK reference to trade_signals.id
    trade_mode = Column(String, default="INTRADAY")        # INTRADAY | DELIVERY
    risk_reward = Column(String, nullable=True)            # e.g. "1:2.3"
    position_value = Column(Float, default=0.0)            # quantity * entry_price
    max_loss_at_sl = Column(Float, default=0.0)
    entry_time = Column(BigInteger, nullable=False)        # ms epoch
    exit_time = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class DBPortfolio(Base):
    """Virtual portfolio state — single row, updated on every trade."""
    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, index=True)
    total_capital = Column(Float, default=100000.0)
    available_cash = Column(Float, default=100000.0)
    used_cash = Column(Float, default=0.0)
    total_profit = Column(Float, default=0.0)
    total_loss = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    open_trades = Column(Integer, default=0)
    closed_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    todays_pnl = Column(Float, default=0.0)
    todays_date = Column(String, nullable=True)            # YYYY-MM-DD, reset daily
    updated_at = Column(BigInteger, nullable=True)


class DBMarketSentiment(Base):
    """Market sentiment extracted from Agent 1 Discovery output."""
    __tablename__ = "market_sentiment"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    sector = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)              # BULLISH | BEARISH | NEUTRAL | MIXED
    confidence_score = Column(Float, default=0.0)
    news_reason = Column(String, nullable=True)
    event_strength = Column(String, nullable=True)         # STRONG | MODERATE | WEAK
    final_verdict = Column(String, nullable=True)          # IMPORTANT_EVENT | MODERATE_EVENT | MINOR_EVENT | NOISE
    market_date = Column(String, nullable=True, index=True)
    updated_at = Column(BigInteger, nullable=True)


class DBAgentLog(Base):
    """Structured agent activity log for audit trail."""
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_name = Column(String, nullable=False)            # AGENT_1 | AGENT_2 | AGENT_3 | AGENT_4 | PAPER_TRADING
    symbol = Column(String, nullable=True, index=True)
    signal = Column(String, nullable=True)                 # BUY | SELL | HOLD | TARGET_HIT | STOP_LOSS_HIT etc.
    confidence = Column(Float, default=0.0)
    message = Column(String, nullable=True)
    details = Column(JSON, nullable=True)                  # Extra structured data
    trade_id = Column(String, nullable=True)               # Reference to paper_trades.id
    created_at = Column(BigInteger, nullable=False)
