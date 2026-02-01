"""Application configuration."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App settings loaded from environment variables."""
    
    # Database
    database_url: str = "postgresql://localhost/finance_app"
    
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
