"""Stock price and corporate action models."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Date, DateTime, BigInteger, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base


class StockPrice(Base):
    """Daily stock price data (split-adjusted from Yahoo Finance)."""
    
    __tablename__ = "stock_prices"
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    ticker = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Numeric(18, 6))
    high = Column(Numeric(18, 6))
    low = Column(Numeric(18, 6))
    close = Column(Numeric(18, 6))  # Split-adjusted
    adj_close = Column(Numeric(18, 6))  # Split + dividend adjusted (total return)
    volume = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="prices")
    
    def __repr__(self):
        return f"<StockPrice {self.ticker} {self.date}: {self.close}>"


class StockSplit(Base):
    """Stock split events."""
    
    __tablename__ = "stock_splits"
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    ticker = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    split_ratio = Column(Numeric(18, 6), nullable=False)  # 4.0 = 4:1 split
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="splits")
    
    def __repr__(self):
        return f"<StockSplit {self.ticker} {self.date}: {self.split_ratio}:1>"


class Dividend(Base):
    """Dividend payments."""
    
    __tablename__ = "dividends"
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    ticker = Column(String(20), nullable=False)
    ex_date = Column(Date, nullable=False)
    payment_date = Column(Date)
    amount = Column(Numeric(18, 6), nullable=False)  # Per-share, split-adjusted
    dividend_type = Column(String(50), default="cash")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="dividends")
    
    def __repr__(self):
        return f"<Dividend {self.ticker} {self.ex_date}: ${self.amount}>"


class SharesOutstanding(Base):
    """Shares outstanding history for market cap calculations."""
    
    __tablename__ = "shares_outstanding"
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    ticker = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    shares_basic = Column(BigInteger)
    shares_diluted = Column(BigInteger)
    source = Column(String(100))  # '10-K', '10-Q', 'yahoo'
    filing_accession = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<SharesOutstanding {self.ticker} {self.date}: {self.shares_basic:,}>"
