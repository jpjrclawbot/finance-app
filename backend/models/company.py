"""Company and ticker models."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base


class Company(Base):
    """Company master record."""
    
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    cik = Column(String(10), unique=True)  # SEC Central Index Key
    name = Column(String(500), nullable=False)
    ticker = Column(String(20))  # Primary ticker
    sic_code = Column(String(4))
    state_of_incorporation = Column(String(50))
    fiscal_year_end = Column(String(4))  # e.g., "1231" for Dec 31
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    ticker_history = relationship("TickerHistory", back_populates="company")
    prices = relationship("StockPrice", back_populates="company")
    splits = relationship("StockSplit", back_populates="company")
    dividends = relationship("Dividend", back_populates="company")
    filings = relationship("SecFiling", back_populates="company")
    
    def __repr__(self):
        return f"<Company {self.ticker}: {self.name}>"


class TickerHistory(Base):
    """Historical ticker symbols for a company."""
    
    __tablename__ = "ticker_history"
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    ticker = Column(String(20), nullable=False)
    exchange = Column(String(50))
    start_date = Column(Date)
    end_date = Column(Date)  # NULL if current
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="ticker_history")
    
    def __repr__(self):
        return f"<TickerHistory {self.ticker} ({self.exchange})>"
