"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings


# Default to SQLite in project directory for easy demo
DEFAULT_DB = f"sqlite:///{Path(__file__).parent.parent}/data/finance.db"


class Settings(BaseSettings):
    """App settings loaded from environment variables."""
    
    # Database (defaults to SQLite for demo, use PostgreSQL for production)
    database_url: str = DEFAULT_DB
    
    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    
    # External APIs
    sec_user_agent: str = "FinanceApp contact@example.com"  # Required by SEC
    
    # Rate limiting
    yahoo_rate_limit: float = 0.5  # seconds between requests
    sec_rate_limit: float = 0.1   # SEC allows 10 req/sec
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
