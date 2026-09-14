"""
SQLite database setup via SQLAlchemy.
Switch DATABASE_URL in config.py to postgres:// for prod.
"""
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

from app.config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Posting(Base):
    __tablename__ = "postings"

    url = Column(String, primary_key=True)          # dedup key
    title = Column(String, nullable=False)
    company = Column(String)
    description = Column(Text)
    source = Column(String)                          # "linkedin"
    posted_at = Column(DateTime)                     # when the job was originally posted
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String, default="new")           # new | rejected (set by the relevance filter)
    notified_at = Column(DateTime)                   # set once --watch-linkedin has notified for this posting


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
