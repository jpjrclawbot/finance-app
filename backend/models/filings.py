"""SEC filing models."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from backend.database import Base


class SecFiling(Base):
    """SEC EDGAR filing metadata."""
    
    __tablename__ = "sec_filings"
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    cik = Column(String(10), nullable=False)
    accession_number = Column(String(50), unique=True, nullable=False)
    form_type = Column(String(20), nullable=False)  # 10-K, 10-Q, 8-K
    filing_date = Column(Date, nullable=False)
    report_date = Column(Date)  # Period end date
    primary_document = Column(String(500))
    file_url = Column(String(1000))
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="filings")
    facts = relationship("FinancialFact", back_populates="filing")
    
    def __repr__(self):
        return f"<SecFiling {self.form_type} {self.filing_date}>"


class FinancialFact(Base):
    """Extracted financial data from SEC filings (XBRL)."""
    
    __tablename__ = "financial_facts"
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    filing_id = Column(Integer, ForeignKey("sec_filings.id", ondelete="CASCADE"))
    cik = Column(String(10), nullable=False)
    taxonomy = Column(String(50), nullable=False)  # us-gaap, dei
    concept = Column(String(200), nullable=False)  # e.g., 'Revenues'
    value = Column(Numeric(24, 4))
    unit = Column(String(50))  # USD, shares, pure
    period_start = Column(Date)
    period_end = Column(Date, nullable=False)
    fiscal_year = Column(Integer)
    fiscal_period = Column(String(10))  # FY, Q1, Q2, Q3, Q4
    instant = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    filing = relationship("SecFiling", back_populates="facts")
    
    def __repr__(self):
        return f"<FinancialFact {self.concept}: {self.value} {self.unit}>"
