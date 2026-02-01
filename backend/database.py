"""Database connection and session management."""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.config import get_settings

settings = get_settings()

# Configure engine based on database type
if settings.database_url.startswith("sqlite"):
    # Ensure data directory exists for SQLite
    db_path = settings.database_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},  # SQLite needs this
    )
else:
    # PostgreSQL
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
