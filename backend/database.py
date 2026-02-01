"""Database connection and session management."""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.config import get_settings

settings = get_settings()

# Check for Streamlit secrets (for cloud deployment)
try:
    import streamlit as st
    if hasattr(st, 'secrets') and 'database' in st.secrets:
        db_url = st.secrets.database.url
    else:
        db_url = os.environ.get('DATABASE_URL', settings.database_url)
except:
    db_url = os.environ.get('DATABASE_URL', settings.database_url)

# Configure engine based on database type
if db_url.startswith("sqlite"):
    # Ensure data directory exists for SQLite
    db_path = db_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},  # SQLite needs this
    )
else:
    # PostgreSQL
    engine = create_engine(
        db_url,
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
