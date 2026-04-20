import time
from database import SessionLocal
import db_models

db = SessionLocal()
arts = db.query(db_models.NewsArticle).filter(db_models.NewsArticle.published_at == 0).all()
count = 0
now = int(time.time() * 1000)

for a in arts:
    if a.analyzed_at and a.analyzed_at > 0:
        a.published_at = a.analyzed_at
    else:
        a.published_at = now
    count += 1

db.commit()
print(f"Fixed {count} articles with 0 timestamp")
db.close()
