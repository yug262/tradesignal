import sys
import os
import time
from sqlalchemy.orm import Session

# Add current directory to path to import local modules
sys.path.append(os.getcwd())

import db_models
from database import SessionLocal, engine

def check_db():
    db = SessionLocal()
    try:
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - (48 * 3600 * 1000)
        
        recent = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.published_at >= cutoff_ms).all()
        print(f"Found {len(recent)} recent articles.\n")
        
        for a in recent:
            print(f"ID: {a.id}")
            print(f"Title: {a.title}")
            print(f"Impact: {a.impact_score}")
            print(f"Symbols: {a.affected_symbols}")
            print("-" * 30)

    finally:
        db.close()

if __name__ == "__main__":
    check_db()
