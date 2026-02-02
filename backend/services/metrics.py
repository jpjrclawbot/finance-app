"""Valuation metrics calculation service."""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from backend.models import Company, StockPrice, FinancialFact, ValuationMetric
from backend.services.edgar import EdgarService

logger = logging.getLogger(__name__)


class MetricsService:
    """Service for calculating and storing valuation metrics."""
    
    def __init__(self, db: Session):
        self.db = db
        self.edgar = EdgarService(db)
    
    def get_latest_fact(
        self,
        company_id: int,
        concept: str,
        as_of: Optional[date] = None,
    ) -> Optional[Decimal]:
        """Get the latest value for a financial concept."""
        query = (
            self.db.query(FinancialFact)
            .filter(
                FinancialFact.company_id == company_id,
                FinancialFact.concept == concept,
            )
        )
        
        if as_of:
            query = query.filter(FinancialFact.period_end <= as_of)
        
        fact = query.order_by(FinancialFact.period_end.desc()).first()
        
        return Decimal(str(fact.value)) if fact and fact.value else None
    
    def get_ttm_value(
        self,
        company_id: int,
        concept: str,
        as_of: Optional[date] = None,
    ) -> Optional[Decimal]:
        """Get trailing twelve month value by summing last 4 quarters."""
        if not as_of:
            as_of = date.today()
        
        # Get last 4 quarterly values
        facts = (
            self.db.query(FinancialFact)
            .filter(
                FinancialFact.company_id == company_id,
                FinancialFact.concept == concept,
                FinancialFact.fiscal_period.in_(["Q1", "Q2", "Q3", "Q4"]),
                FinancialFact.period_end <= as_of,
            )
            .order_by(FinancialFact.period_end.desc())
            .limit(4)
            .all()
        )
        
        if len(facts) < 4:
            # Fall back to annual value
            annual = self.get_latest_fact(company_id, concept, as_of)
            return annual
        
        return sum(Decimal(str(f.value)) for f in facts if f.value)
    
    def calculate_metrics(self, ticker: str, as_of: Optional[date] = None) -> dict:
        """Calculate valuation metrics for a company."""
        if not as_of:
            as_of = date.today()
        
        company = self.db.query(Company).filter(Company.ticker == ticker).first()
        if not company:
            return {"error": f"Company not found: {ticker}"}
        
        # Get latest price
        price_record = (
            self.db.query(StockPrice)
            .filter(StockPrice.company_id == company.id, StockPrice.date <= as_of)
            .order_by(StockPrice.date.desc())
            .first()
        )
        
        if not price_record:
            return {"error": f"No price data for {ticker}"}
        
        price = Decimal(str(price_record.close))
        
        # Get shares outstanding
        shares = self.edgar.get_shares_outstanding(ticker)
        if not shares:
            return {"error": f"No shares outstanding data for {ticker}"}
        
        market_cap = price * shares
        
        # Gather financial data
        metrics = {
            "ticker": ticker,
            "date": as_of.isoformat(),
            "price": float(price),
            "shares_outstanding": shares,
            "market_cap": int(market_cap),
        }
        
        # Revenue
        revenue = self.get_ttm_value(company.id, "Revenues", as_of)
        if not revenue:
            revenue = self.get_ttm_value(company.id, "RevenueFromContractWithCustomerExcludingAssessedTax", as_of)
        
        if revenue and revenue > 0:
            metrics["revenue_ttm"] = int(revenue)
            metrics["ps_ratio"] = float(market_cap / revenue)
        
        # Net Income - Use Market Cap / Net Income for P/E (avoids split issues)
        # NOTE: We intentionally DON'T calculate EPS from SEC data because
        # per-share metrics from filings aren't split-adjusted consistently.
        # The SEC restates annual filings post-split but quarterly filings
        # keep their original values, causing P/E distortions.
        net_income = self.get_ttm_value(company.id, "NetIncomeLoss", as_of)
        if net_income and net_income != 0:
            metrics["net_income_ttm"] = int(net_income)
            # P/E = Market Cap / Net Income (split-proof formula)
            if net_income > 0:
                metrics["pe_ratio"] = float(market_cap / net_income)
        
        # EBITDA
        ebitda = self.get_ttm_value(company.id, "EBITDA", as_of)
        if not ebitda:
            # Try to calculate: Net Income + Interest + Taxes + D&A
            operating_income = self.get_ttm_value(company.id, "OperatingIncomeLoss", as_of)
            depreciation = self.get_ttm_value(company.id, "DepreciationAndAmortization", as_of)
            if operating_income and depreciation:
                ebitda = operating_income + depreciation
        
        # Enterprise Value
        total_debt = self.get_latest_fact(company.id, "LongTermDebt", as_of)
        if not total_debt:
            total_debt = self.get_latest_fact(company.id, "LongTermDebtNoncurrent", as_of) or Decimal(0)
        
        short_term_debt = self.get_latest_fact(company.id, "ShortTermBorrowings", as_of) or Decimal(0)
        total_debt = (total_debt or Decimal(0)) + short_term_debt
        
        cash = self.get_latest_fact(company.id, "CashAndCashEquivalentsAtCarryingValue", as_of)
        if not cash:
            cash = self.get_latest_fact(company.id, "Cash", as_of) or Decimal(0)
        
        enterprise_value = market_cap + total_debt - (cash or Decimal(0))
        metrics["enterprise_value"] = int(enterprise_value)
        metrics["total_debt"] = int(total_debt) if total_debt else 0
        metrics["cash"] = int(cash) if cash else 0
        
        if revenue and revenue > 0:
            metrics["ev_revenue"] = float(enterprise_value / revenue)
        
        if ebitda and ebitda > 0:
            metrics["ebitda_ttm"] = int(ebitda)
            metrics["ev_ebitda"] = float(enterprise_value / ebitda)
        
        # Margins
        if revenue and revenue > 0:
            gross_profit = self.get_ttm_value(company.id, "GrossProfit", as_of)
            if gross_profit:
                metrics["gross_margin"] = float(gross_profit / revenue)
            
            operating_income = self.get_ttm_value(company.id, "OperatingIncomeLoss", as_of)
            if operating_income:
                metrics["operating_margin"] = float(operating_income / revenue)
            
            if net_income:
                metrics["net_margin"] = float(net_income / revenue)
        
        # Book Value / P/B - Use Market Cap / Book Value (avoids split issues)
        stockholders_equity = self.get_latest_fact(
            company.id, "StockholdersEquity", as_of
        )
        if stockholders_equity and stockholders_equity > 0:
            metrics["book_value"] = int(stockholders_equity)
            # P/B = Market Cap / Book Value (split-proof formula)
            metrics["pb_ratio"] = float(market_cap / stockholders_equity)
        
        # ROE
        if net_income and stockholders_equity and stockholders_equity > 0:
            metrics["roe"] = float(net_income / stockholders_equity)
        
        # Total Assets / ROA
        total_assets = self.get_latest_fact(company.id, "Assets", as_of)
        if net_income and total_assets and total_assets > 0:
            metrics["roa"] = float(net_income / total_assets)
        
        return metrics
    
    def store_metrics(self, ticker: str, as_of: Optional[date] = None) -> dict:
        """Calculate and store metrics for a company."""
        metrics = self.calculate_metrics(ticker, as_of)
        
        if "error" in metrics:
            return metrics
        
        company = self.db.query(Company).filter(Company.ticker == ticker).first()
        
        record = {
            "company_id": company.id,
            "ticker": ticker,
            "date": as_of or date.today(),
            "price": metrics.get("price"),
            "market_cap": metrics.get("market_cap"),
            "pe_ratio": metrics.get("pe_ratio"),
            "ps_ratio": metrics.get("ps_ratio"),
            "pb_ratio": metrics.get("pb_ratio"),
            "enterprise_value": metrics.get("enterprise_value"),
            "ev_revenue": metrics.get("ev_revenue"),
            "ev_ebitda": metrics.get("ev_ebitda"),
            "gross_margin": metrics.get("gross_margin"),
            "operating_margin": metrics.get("operating_margin"),
            "net_margin": metrics.get("net_margin"),
            "roe": metrics.get("roe"),
            "roa": metrics.get("roa"),
        }
        
        stmt = insert(ValuationMetric.__table__).values([record])
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={k: stmt.excluded[k] for k in record if k not in ["ticker", "date"]}
        )
        self.db.execute(stmt)
        self.db.commit()
        
        logger.info(f"Stored metrics for {ticker}")
        return metrics
