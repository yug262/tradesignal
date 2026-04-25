import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

load_dotenv()

def create_database():
    # We need to connect to 'postgres' database to create a new one
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/tradesignal")
    
    # Extract connection info but target 'postgres' db
    # URL format: postgresql://user:password@host:port/dbname
    base_url = db_url.rsplit('/', 1)[0] + '/postgres'
    target_db = db_url.rsplit('/', 1)[1]

    print(f"Connecting to {base_url} to create {target_db}...")

    try:
        conn = psycopg2.connect(base_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Check if exists
        cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{target_db}'")
        exists = cur.fetchone()
        
        if not exists:
            print(f"Database {target_db} does not exist. Creating...")
            cur.execute(f"CREATE DATABASE {target_db}")
            print(f"Database {target_db} created successfully.")
        else:
            print(f"Database {target_db} already exists.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error creating database: {e}")
        print("\nPlease ensure PostgreSQL is running and your credentials in .env are correct.")
        return

    # Now connect to the target database and ensure all tables exist
    print(f"\nEnsuring tables exist in {target_db}...")
    try:
        conn = psycopg2.connect(db_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        # Create tables if they don't exist
        tables = {
            "news_articles": """
                CREATE TABLE IF NOT EXISTS news_articles (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    source TEXT,
                    published_at BIGINT,
                    analyzed_at BIGINT,
                    image_url TEXT,
                    impact_score FLOAT,
                    impact_summary TEXT,
                    executive_summary TEXT,
                    news_relevance TEXT,
                    news_category TEXT,
                    affected_symbols TEXT[],
                    processing_status TEXT,
                    raw_analysis_data JSON
                );
            """,
            "system_config": """
                CREATE TABLE IF NOT EXISTS system_config (
                    id SERIAL PRIMARY KEY,
                    capital FLOAT DEFAULT 100000.0,
                    risk_per_trade_pct FLOAT DEFAULT 1.0,
                    max_open_positions INTEGER DEFAULT 5,
                    max_daily_loss_pct FLOAT DEFAULT 3.0,
                    min_rr FLOAT DEFAULT 1.5,
                    news_endpoint_url TEXT,
                    polling_interval_mins INTEGER DEFAULT 5,
                    processing_mode TEXT DEFAULT 'pre_market'
                );
            """,
            "processing_state": """
                CREATE TABLE IF NOT EXISTS processing_state (
                    id SERIAL PRIMARY KEY,
                    last_processed_article_id TEXT,
                    last_poll_timestamp BIGINT DEFAULT 0,
                    total_articles_processed INTEGER DEFAULT 0,
                    current_mode TEXT DEFAULT 'pre_market',
                    is_polling_active BOOLEAN DEFAULT FALSE,
                    articles_in_queue INTEGER DEFAULT 0
                );
            """,
            "trade_signals": """
                CREATE TABLE IF NOT EXISTS trade_signals (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    trade_mode TEXT NOT NULL,
                    entry_price FLOAT,
                    stop_loss FLOAT,
                    target_price FLOAT,
                    risk_reward FLOAT,
                    confidence FLOAT,
                    reasoning JSON,
                    news_article_ids JSON,
                    stock_snapshot JSON,
                    generated_at BIGINT NOT NULL,
                    market_date TEXT NOT NULL,
                    status TEXT DEFAULT 'pending_confirmation',
                    confirmation_status TEXT DEFAULT 'pending',
                    confirmed_at BIGINT,
                    confirmation_data JSON,
                    execution_status TEXT DEFAULT 'pending',
                    executed_at BIGINT,
                    execution_data JSON
                );
                CREATE INDEX IF NOT EXISTS idx_trade_signals_symbol ON trade_signals(symbol);
                CREATE INDEX IF NOT EXISTS idx_trade_signals_market_date ON trade_signals(market_date);
            """,
            "paper_trades": """
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entry_price FLOAT NOT NULL,
                    exit_price FLOAT,
                    quantity INTEGER NOT NULL,
                    stop_loss FLOAT NOT NULL,
                    target_price FLOAT NOT NULL,
                    current_price FLOAT,
                    pnl FLOAT DEFAULT 0.0,
                    pnl_percentage FLOAT DEFAULT 0.0,
                    status TEXT DEFAULT 'OPEN',
                    confidence_score FLOAT DEFAULT 0.0,
                    risk_level TEXT,
                    trade_reason TEXT,
                    exit_reason TEXT,
                    signal_id TEXT,
                    trade_mode TEXT DEFAULT 'INTRADAY',
                    risk_reward TEXT,
                    position_value FLOAT DEFAULT 0.0,
                    max_loss_at_sl FLOAT DEFAULT 0.0,
                    entry_time BIGINT NOT NULL,
                    exit_time BIGINT,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol ON paper_trades(symbol);
                CREATE INDEX IF NOT EXISTS idx_paper_trades_status ON paper_trades(status);
                CREATE INDEX IF NOT EXISTS idx_paper_trades_signal_id ON paper_trades(signal_id);
            """,
            "portfolio": """
                CREATE TABLE IF NOT EXISTS portfolio (
                    id SERIAL PRIMARY KEY,
                    total_capital FLOAT DEFAULT 100000.0,
                    available_cash FLOAT DEFAULT 100000.0,
                    used_cash FLOAT DEFAULT 0.0,
                    total_profit FLOAT DEFAULT 0.0,
                    total_loss FLOAT DEFAULT 0.0,
                    total_pnl FLOAT DEFAULT 0.0,
                    win_rate FLOAT DEFAULT 0.0,
                    total_trades INTEGER DEFAULT 0,
                    open_trades INTEGER DEFAULT 0,
                    closed_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    todays_pnl FLOAT DEFAULT 0.0,
                    todays_date TEXT,
                    updated_at BIGINT
                );
            """,
            "market_sentiment": """
                CREATE TABLE IF NOT EXISTS market_sentiment (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    sector TEXT,
                    sentiment TEXT,
                    confidence_score FLOAT DEFAULT 0.0,
                    news_reason TEXT,
                    event_strength TEXT,
                    final_verdict TEXT,
                    market_date TEXT,
                    updated_at BIGINT
                );
                CREATE INDEX IF NOT EXISTS idx_market_sentiment_symbol ON market_sentiment(symbol);
                CREATE INDEX IF NOT EXISTS idx_market_sentiment_date ON market_sentiment(market_date);
            """,
            "agent_logs": """
                CREATE TABLE IF NOT EXISTS agent_logs (
                    id SERIAL PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    symbol TEXT,
                    signal TEXT,
                    confidence FLOAT DEFAULT 0.0,
                    message TEXT,
                    details JSON,
                    trade_id TEXT,
                    created_at BIGINT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_logs_symbol ON agent_logs(symbol);
            """,
            "indicator_data": """
                CREATE TABLE IF NOT EXISTS indicator_data (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    indicator_name TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamps BIGINT[],
                    values FLOAT[],
                    updated_at BIGINT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_indicator_data_symbol ON indicator_data(symbol);
            """,
            "live_news_events": """
                CREATE TABLE IF NOT EXISTS live_news_events (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    news_ids JSON,
                    triggered_at BIGINT NOT NULL,
                    current_price FLOAT,
                    publish_time_price FLOAT,
                    gemini_output JSON,
                    should_trade BOOLEAN DEFAULT FALSE,
                    confidence FLOAT DEFAULT 0.0,
                    agent3_triggered BOOLEAN DEFAULT FALSE,
                    market_date TEXT,
                    created_at BIGINT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_live_news_events_symbol ON live_news_events(symbol);
                CREATE INDEX IF NOT EXISTS idx_live_news_events_date ON live_news_events(market_date);
                CREATE INDEX IF NOT EXISTS idx_live_news_events_triggered_at ON live_news_events(triggered_at);
            """,
        }

        for table_name, create_sql in tables.items():
            cur.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')")
            exists = cur.fetchone()[0]
            if exists:
                print(f"  [OK] Table '{table_name}' already exists")
            else:
                cur.execute(create_sql)
                print(f"  [OK] Table '{table_name}' created")

        # --- Auto-migrate: add missing columns to existing tables ---
        migrations = [
            ("trade_signals", "confirmation_status", "TEXT DEFAULT 'pending'"),
            ("trade_signals", "confirmed_at", "BIGINT"),
            ("trade_signals", "confirmation_data", "JSON"),
            ("trade_signals", "execution_status", "TEXT DEFAULT 'pending'"),
            ("trade_signals", "executed_at", "BIGINT"),
            ("trade_signals", "execution_data", "JSON"),
            # Risk management columns for Agent 3 position sizing
            ("system_config", "max_loss_per_trade_pct", "FLOAT DEFAULT 1.0"),
            ("system_config", "max_capital_per_trade_pct", "FLOAT DEFAULT 20.0"),
            # Risk Monitor Agent (Phase 4) columns
            ("trade_signals", "risk_monitor_status", "TEXT"),
            ("trade_signals", "risk_monitor_data", "JSON"),
            ("trade_signals", "risk_last_checked_at", "BIGINT"),
        ]
        for tbl, col, col_type in migrations:
            cur.execute(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{tbl}' AND column_name = '{col}'
                )
            """)
            col_exists = cur.fetchone()[0]
            if not col_exists:
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}")
                print(f"  [MIGRATE] Added column '{col}' to '{tbl}'")

        cur.close()
        conn.close()
        print("\n[DONE] Database setup complete!")

    except Exception as e:
        print(f"Error setting up tables: {e}")


if __name__ == "__main__":
    create_database()
