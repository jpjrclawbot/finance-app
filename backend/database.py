"""Database connection and session management."""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def get_database_url():
    """Get database URL from various sources."""
    # 1. Check Streamlit secrets first (for cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            if 'database' in st.secrets and 'url' in st.secrets.database:
                return st.secrets.database.url
            elif 'DATABASE_URL' in st.secrets:
                return st.secrets.DATABASE_URL
    except Exception:
        pass
    
    # 2. Check environment variable
    if os.environ.get('DATABASE_URL'):
        return os.environ.get('DATABASE_URL')
    
    # 3. Fall back to local SQLite
    return f"sqlite:///{Path(__file__).parent.parent}/data/finance.db"


def create_db_engine(db_url: str):
    """Create SQLAlchemy engine based on database type."""
    if db_url.startswith("sqlite"):
        # Ensure data directory exists for SQLite
        db_path = db_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL
        return create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )


# Initialize
db_url = get_database_url()
engine = create_db_engine(db_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
