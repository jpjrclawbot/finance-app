"""Market index models."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base


class Index(Base):
    """Market index (S&P 500, DJIA, etc.)."""
    
    __tablename__ = "indices"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), unique=True, nullable=False)  # ^GSPC
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    constituents = relationship("IndexConstituent", back_populates="index")
    
    def __repr__(self):
        return f"<Index {self.symbol}: {self.name}>"


class IndexConstituent(Base):
    """Index membership history."""
    
    __tablename__ = "index_constituents"
    
    id = Column(Integer, primary_key=True)
    index_id = Column(Integer, ForeignKey("indices.id", ondelete="CASCADE"))
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    ticker = Column(String(20), nullable=False)
    added_date = Column(Date)
    removed_date = Column(Date)  # NULL if still in index
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    index = relationship("Index", back_populates="constituents")
    
    def __repr__(self):
        return f"<IndexConstituent {self.ticker} in {self.index_id}>"
