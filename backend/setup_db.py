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

if __name__ == "__main__":
    create_database()
