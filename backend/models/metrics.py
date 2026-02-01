"""Calculated valuation metrics model."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, BigInteger, Numeric, ForeignKey

from backend.database import Base


class ValuationMetric(Base):
    """Pre-calculated valuation metrics for fast querying."""
    
    __tablename__ = "valuation_metrics"
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    ticker = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    
    # Price data
    price = Column(Numeric(18, 6))
    market_cap = Column(BigInteger)
    
    # Valuation ratios
    pe_ratio = Column(Numeric(12, 4))
    pe_forward = Column(Numeric(12, 4))
    ps_ratio = Column(Numeric(12, 4))
    pb_ratio = Column(Numeric(12, 4))
    
    # Enterprise value metrics
    enterprise_value = Column(BigInteger)
    ev_revenue = Column(Numeric(12, 4))
    ev_ebitda = Column(Numeric(12, 4))
    ev_ebit = Column(Numeric(12, 4))
    
    # Profitability
    gross_margin = Column(Numeric(8, 4))
    operating_margin = Column(Numeric(8, 4))
    net_margin = Column(Numeric(8, 4))
    roe = Column(Numeric(8, 4))
    roa = Column(Numeric(8, 4))
    roic = Column(Numeric(8, 4))
    
    # Growth
    revenue_growth = Column(Numeric(8, 4))
    earnings_growth = Column(Numeric(8, 4))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ValuationMetric {self.ticker} {self.date}: P/E={self.pe_ratio}>"
