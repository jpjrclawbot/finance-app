"""
Time series valuation metrics service.

Calculates daily valuation metrics and aggregate weighted averages for bundles.

IMPORTANT - Split Handling:
- Always use adj_close (split-adjusted) for prices
- Always use latest shares outstanding (also split-adjusted via SEC restatements)  
- Never use per-share metrics from SEC filings (EPS) for ratio calculations
- Calculate P/E as Market Cap / Net Income (not Price / EPS)

See VALUATION_METHODOLOGY.md for detailed explanation.

Key insight: Weighted averages are computed by summing the components, not averaging ratios.
- Aggregate P/E = Sum(Market Caps) / Sum(Net Incomes)
- Aggregate EV/Revenue = Sum(EVs) / Sum(Revenues)
- Aggregate EV/EBITDA = Sum(EVs) / Sum(EBITDAs)
- Aggregate Margin = Sum(Profits) / Sum(Revenues)
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models import Company, StockPrice, FinancialFact, ValuationMetric

logger = logging.getLogger(__name__)


@dataclass
class DailyMetrics:
    """Daily valuation metrics for a single company."""
    date: date
    ticker: str
    price: float
    market_cap: float
    enterprise_value: float
    
    # Components (for aggregate calculations)
    shares_outstanding: float
    net_income_ttm: float
    revenue_ttm: float
    ebitda_ttm: float
    total_debt: float
    cash: float
    
    # Ratios
    pe_ratio: Optional[float]
    ps_ratio: Optional[float]
    ev_revenue: Optional[float]
    ev_ebitda: Optional[float]


@dataclass  
class AggregateMetrics:
    """Aggregate metrics for a bundle of companies."""
    date: date
    bundle_name: str
    
    # Totals
    total_market_cap: float
    total_enterprise_value: float
    total_net_income: float
    total_revenue: float
    total_ebitda: float
    
    # Aggregate ratios (properly weighted)
    aggregate_pe: Optional[float]  # total_market_cap / total_net_income
    aggregate_ps: Optional[float]  # total_market_cap / total_revenue
    aggregate_ev_revenue: Optional[float]  # total_ev / total_revenue
    aggregate_ev_ebitda: Optional[float]  # total_ev / total_ebitda
    
    # Count of companies included
    company_count: int


# Sector definitions based on SIC codes (first 2 digits)
SECTOR_DEFINITIONS = {
    "Technology": ["35", "36", "37", "73"],  # Computers, Electronics, Software
    "Healthcare": ["28", "38", "80"],  # Pharma, Medical Instruments, Health Services
    "Financial": ["60", "61", "62", "63", "64", "65", "67"],  # Banks, Insurance, Investment
    "Consumer Discretionary": ["52", "53", "54", "55", "56", "57", "58", "59", "70", "78", "79"],
    "Consumer Staples": ["20", "21", "51", "54"],  # Food, Tobacco, Wholesale, Food Stores
    "Energy": ["10", "12", "13", "14", "29", "46"],  # Mining, Oil & Gas, Petroleum
    "Industrials": ["15", "16", "17", "24", "25", "30", "31", "32", "33", "34", "37", "40", "41", "42", "44", "45", "47"],
    "Materials": ["10", "12", "14", "24", "26", "28", "32", "33"],
    "Utilities": ["49"],
    "Real Estate": ["65", "67"],
    "Communication": ["48", "78", "79"],
}

# Pre-made bundles
PREMADE_BUNDLES = {
    "FAANG": ["META", "AAPL", "AMZN", "NFLX", "GOOGL"],
    "Magnificent 7": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"],
    "Big Tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
    "Chip Makers": ["NVDA", "AMD", "INTC", "AVGO", "QCOM"],
    "EV & Clean Energy": ["TSLA", "RIVN", "LCID", "NIO", "ENPH"],
    "Streaming": ["NFLX", "DIS", "WBD", "PARA", "CMCSA"],
}


class TimeSeriesService:
    """Service for time series valuation metrics."""
    
    def __init__(self, db: Session):
        self.db = db
        self._financial_cache = {}  # Cache TTM financials by (ticker, as_of_date)
    
    def get_financial_as_of(
        self,
        company_id: int,
        concept: str,
        as_of: date,
        ttm: bool = True,
    ) -> Optional[float]:
        """
        Get financial value as of a specific date.
        
        For TTM (trailing twelve months), sums the last 4 quarters.
        For point-in-time (balance sheet items), gets the latest value.
        """
        if ttm:
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
            
            if len(facts) >= 4:
                return sum(float(f.value) for f in facts if f.value)
            elif facts:
                # Annualize if we have fewer quarters
                avg = sum(float(f.value) for f in facts if f.value) / len(facts)
                return avg * 4
        
        # Point-in-time value
        fact = (
            self.db.query(FinancialFact)
            .filter(
                FinancialFact.company_id == company_id,
                FinancialFact.concept == concept,
                FinancialFact.period_end <= as_of,
            )
            .order_by(FinancialFact.period_end.desc())
            .first()
        )
        
        return float(fact.value) if fact and fact.value else None
    
    def get_shares_outstanding(self, company_id: int, as_of: date) -> Optional[float]:
        """Get shares outstanding as of a date."""
        return self.get_financial_as_of(
            company_id, 
            "CommonStockSharesOutstanding", 
            as_of, 
            ttm=False
        )
    
    def calculate_daily_metrics(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyMetrics]:
        """Calculate daily valuation metrics for a single company."""
        company = self.db.query(Company).filter(Company.ticker == ticker).first()
        if not company:
            return []
        
        # Get all prices in range
        prices = (
            self.db.query(StockPrice)
            .filter(
                StockPrice.ticker == ticker,
                StockPrice.date >= start_date,
                StockPrice.date <= end_date,
            )
            .order_by(StockPrice.date)
            .all()
        )
        
        if not prices:
            return []
        
        # Get financial data (use latest available for the whole period)
        # In production, you'd want to update these as new filings come in
        shares = self.get_shares_outstanding(company.id, end_date)
        revenue_ttm = self.get_financial_as_of(company.id, "Revenues", end_date, ttm=True)
        net_income_ttm = self.get_financial_as_of(company.id, "NetIncomeLoss", end_date, ttm=True)
        ebitda_ttm = self.get_financial_as_of(company.id, "EBITDA", end_date, ttm=True)
        
        # If no EBITDA, try to estimate from operating income + D&A
        if not ebitda_ttm:
            op_income = self.get_financial_as_of(company.id, "OperatingIncomeLoss", end_date, ttm=True)
            depreciation = self.get_financial_as_of(company.id, "DepreciationAndAmortization", end_date, ttm=True)
            if op_income and depreciation:
                ebitda_ttm = op_income + depreciation
            elif op_income:
                ebitda_ttm = op_income * 1.2  # Rough estimate
        
        # Balance sheet items
        total_debt = self.get_financial_as_of(company.id, "LongTermDebt", end_date, ttm=False) or 0
        short_debt = self.get_financial_as_of(company.id, "ShortTermBorrowings", end_date, ttm=False) or 0
        total_debt += short_debt
        
        cash = self.get_financial_as_of(company.id, "CashAndCashEquivalentsAtCarryingValue", end_date, ttm=False) or 0
        
        results = []
        for price in prices:
            if not shares:
                continue
            
            # NOTE on splits: Yahoo Finance history() returns split-adjusted prices
            # in BOTH the Close and Adj Close columns. The SEC filing shares are also
            # restated post-split in annual filings. So using latest shares + adj_close
            # should give consistent market cap calculations.
            #
            # P/E = Market Cap / Net Income avoids per-share issues entirely.
            price_val = float(price.adj_close) if price.adj_close else float(price.close)
            
            market_cap = price_val * shares
            enterprise_value = market_cap + total_debt - cash
            
            # Calculate ratios
            pe_ratio = market_cap / net_income_ttm if net_income_ttm and net_income_ttm > 0 else None
            ps_ratio = market_cap / revenue_ttm if revenue_ttm and revenue_ttm > 0 else None
            ev_revenue = enterprise_value / revenue_ttm if revenue_ttm and revenue_ttm > 0 else None
            ev_ebitda = enterprise_value / ebitda_ttm if ebitda_ttm and ebitda_ttm > 0 else None
            
            results.append(DailyMetrics(
                date=price.date,
                ticker=ticker,
                price=price_val,
                market_cap=market_cap,
                enterprise_value=enterprise_value,
                shares_outstanding=shares,
                net_income_ttm=net_income_ttm or 0,
                revenue_ttm=revenue_ttm or 0,
                ebitda_ttm=ebitda_ttm or 0,
                total_debt=total_debt,
                cash=cash,
                pe_ratio=pe_ratio,
                ps_ratio=ps_ratio,
                ev_revenue=ev_revenue,
                ev_ebitda=ev_ebitda,
            ))
        
        return results
    
    def calculate_bundle_metrics(
        self,
        tickers: list[str],
        bundle_name: str,
        start_date: date,
        end_date: date,
    ) -> list[AggregateMetrics]:
        """
        Calculate aggregate metrics for a bundle of companies.
        
        Uses proper weighting:
        - Aggregate P/E = Total Market Cap / Total Net Income
        - Aggregate EV/Revenue = Total EV / Total Revenue
        """
        # Get daily metrics for all companies
        all_metrics: dict[date, list[DailyMetrics]] = {}
        
        for ticker in tickers:
            daily = self.calculate_daily_metrics(ticker, start_date, end_date)
            for m in daily:
                if m.date not in all_metrics:
                    all_metrics[m.date] = []
                all_metrics[m.date].append(m)
        
        results = []
        for d in sorted(all_metrics.keys()):
            day_metrics = all_metrics[d]
            
            # Sum up components
            total_market_cap = sum(m.market_cap for m in day_metrics)
            total_ev = sum(m.enterprise_value for m in day_metrics)
            total_net_income = sum(m.net_income_ttm for m in day_metrics)
            total_revenue = sum(m.revenue_ttm for m in day_metrics)
            total_ebitda = sum(m.ebitda_ttm for m in day_metrics)
            
            # Calculate aggregate ratios
            agg_pe = total_market_cap / total_net_income if total_net_income > 0 else None
            agg_ps = total_market_cap / total_revenue if total_revenue > 0 else None
            agg_ev_rev = total_ev / total_revenue if total_revenue > 0 else None
            agg_ev_ebitda = total_ev / total_ebitda if total_ebitda > 0 else None
            
            results.append(AggregateMetrics(
                date=d,
                bundle_name=bundle_name,
                total_market_cap=total_market_cap,
                total_enterprise_value=total_ev,
                total_net_income=total_net_income,
                total_revenue=total_revenue,
                total_ebitda=total_ebitda,
                aggregate_pe=agg_pe,
                aggregate_ps=agg_ps,
                aggregate_ev_revenue=agg_ev_rev,
                aggregate_ev_ebitda=agg_ev_ebitda,
                company_count=len(day_metrics),
            ))
        
        return results
    
    def get_companies_by_sector(self, sector: str) -> list[str]:
        """Get tickers for companies in a sector based on SIC code."""
        if sector not in SECTOR_DEFINITIONS:
            return []
        
        sic_prefixes = SECTOR_DEFINITIONS[sector]
        
        companies = self.db.query(Company).filter(Company.sic_code.isnot(None)).all()
        
        tickers = []
        for company in companies:
            if company.sic_code and any(company.sic_code.startswith(p) for p in sic_prefixes):
                tickers.append(company.ticker)
        
        return tickers
    
    def get_premade_bundle(self, bundle_name: str) -> list[str]:
        """Get tickers for a pre-made bundle."""
        return PREMADE_BUNDLES.get(bundle_name, [])
    
    def list_available_bundles(self) -> dict:
        """List all available pre-made bundles and sectors."""
        return {
            "premade": list(PREMADE_BUNDLES.keys()),
            "sectors": list(SECTOR_DEFINITIONS.keys()),
        }
    
    def compare_bundles(
        self,
        bundles: dict[str, list[str]],  # {bundle_name: [tickers]}
        start_date: date,
        end_date: date,
        metric: str = "aggregate_pe",
    ) -> pd.DataFrame:
        """
        Compare multiple bundles over time.
        
        Returns DataFrame with date index and bundle names as columns.
        """
        all_data = []
        
        for bundle_name, tickers in bundles.items():
            metrics = self.calculate_bundle_metrics(tickers, bundle_name, start_date, end_date)
            
            for m in metrics:
                value = getattr(m, metric, None)
                all_data.append({
                    "date": m.date,
                    "bundle": bundle_name,
                    "value": value,
                    "market_cap": m.total_market_cap,
                    "company_count": m.company_count,
                })
        
        df = pd.DataFrame(all_data)
        
        if df.empty:
            return df
        
        # Pivot to wide format
        pivot = df.pivot(index="date", columns="bundle", values="value")
        
        return pivot
    
    def get_metrics_dataframe(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Get daily metrics for multiple tickers as a DataFrame."""
        all_data = []
        
        for ticker in tickers:
            metrics = self.calculate_daily_metrics(ticker, start_date, end_date)
            for m in metrics:
                all_data.append({
                    "date": m.date,
                    "ticker": m.ticker,
                    "price": m.price,
                    "market_cap": m.market_cap,
                    "enterprise_value": m.enterprise_value,
                    "pe_ratio": m.pe_ratio,
                    "ps_ratio": m.ps_ratio,
                    "ev_revenue": m.ev_revenue,
                    "ev_ebitda": m.ev_ebitda,
                    "net_income_ttm": m.net_income_ttm,
                    "revenue_ttm": m.revenue_ttm,
                })
        
        return pd.DataFrame(all_data)
