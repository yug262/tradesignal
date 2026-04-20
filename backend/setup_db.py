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
                    use_mock_data BOOLEAN DEFAULT FALSE,
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
                    status TEXT DEFAULT 'active'
                );
                CREATE INDEX IF NOT EXISTS idx_trade_signals_symbol ON trade_signals(symbol);
                CREATE INDEX IF NOT EXISTS idx_trade_signals_market_date ON trade_signals(market_date);
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

        cur.close()
        conn.close()
        print("\n[DONE] Database setup complete!")

    except Exception as e:
        print(f"Error setting up tables: {e}")


if __name__ == "__main__":
    create_database()
