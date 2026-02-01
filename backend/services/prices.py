"""Stock price data service using Yahoo Finance."""

import time
from datetime import date, datetime, timedelta
from typing import Optional
import logging

import yfinance as yf
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from backend.models import Company, StockPrice, StockSplit, Dividend
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PriceService:
    """Service for fetching and storing stock price data."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_or_create_company(self, ticker: str) -> Company:
        """Get existing company or create a new one."""
        company = self.db.query(Company).filter(Company.ticker == ticker).first()
        if not company:
            # Get basic info from Yahoo
            info = yf.Ticker(ticker).info
            company = Company(
                ticker=ticker,
                name=info.get("longName") or info.get("shortName") or ticker,
            )
            self.db.add(company)
            self.db.commit()
            self.db.refresh(company)
            logger.info(f"Created company: {company}")
        return company
    
    def fetch_prices(
        self,
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """
        Fetch historical prices from Yahoo Finance and store in database.
        
        Returns dict with counts of records processed.
        """
        company = self.get_or_create_company(ticker)
        
        # Default to 5 years of history
        if not start_date:
            start_date = date.today() - timedelta(days=5*365)
        if not end_date:
            end_date = date.today()
        
        # Rate limiting
        time.sleep(settings.yahoo_rate_limit)
        
        # Fetch from Yahoo Finance
        yf_ticker = yf.Ticker(ticker)
        
        # Get price history
        hist = yf_ticker.history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=False,  # Get both Close and Adj Close
        )
        
        if hist.empty:
            logger.warning(f"No price data for {ticker}")
            return {"prices": 0, "splits": 0, "dividends": 0}
        
        # Process prices
        prices_added = self._store_prices(company, ticker, hist)
        
        # Get splits and dividends
        splits_added = self._store_splits(company, ticker, yf_ticker, start_date, end_date)
        dividends_added = self._store_dividends(company, ticker, yf_ticker, start_date, end_date)
        
        self.db.commit()
        
        return {
            "prices": prices_added,
            "splits": splits_added,
            "dividends": dividends_added,
        }
    
    def _store_prices(self, company: Company, ticker: str, hist: pd.DataFrame) -> int:
        """Store price data using upsert."""
        records = []
        for idx, row in hist.iterrows():
            price_date = idx.date() if hasattr(idx, 'date') else idx
            records.append({
                "company_id": company.id,
                "ticker": ticker,
                "date": price_date,
                "open": float(row["Open"]) if pd.notna(row["Open"]) else None,
                "high": float(row["High"]) if pd.notna(row["High"]) else None,
                "low": float(row["Low"]) if pd.notna(row["Low"]) else None,
                "close": float(row["Close"]) if pd.notna(row["Close"]) else None,
                "adj_close": float(row["Adj Close"]) if pd.notna(row.get("Adj Close", row["Close"])) else None,
                "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else None,
            })
        
        if records:
            stmt = insert(StockPrice.__table__).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "adj_close": stmt.excluded.adj_close,
                    "volume": stmt.excluded.volume,
                }
            )
            self.db.execute(stmt)
        
        logger.info(f"Stored {len(records)} price records for {ticker}")
        return len(records)
    
    def _store_splits(
        self,
        company: Company,
        ticker: str,
        yf_ticker: yf.Ticker,
        start_date: date,
        end_date: date,
    ) -> int:
        """Store stock split data."""
        try:
            splits = yf_ticker.splits
            if splits.empty:
                return 0
            
            # Filter by date range
            splits = splits[(splits.index >= pd.Timestamp(start_date)) & 
                           (splits.index <= pd.Timestamp(end_date))]
            
            records = []
            for idx, ratio in splits.items():
                split_date = idx.date() if hasattr(idx, 'date') else idx
                records.append({
                    "company_id": company.id,
                    "ticker": ticker,
                    "date": split_date,
                    "split_ratio": float(ratio),
                })
            
            if records:
                stmt = insert(StockSplit.__table__).values(records)
                stmt = stmt.on_conflict_do_nothing(index_elements=["ticker", "date"])
                self.db.execute(stmt)
            
            logger.info(f"Stored {len(records)} splits for {ticker}")
            return len(records)
            
        except Exception as e:
            logger.warning(f"Could not fetch splits for {ticker}: {e}")
            return 0
    
    def _store_dividends(
        self,
        company: Company,
        ticker: str,
        yf_ticker: yf.Ticker,
        start_date: date,
        end_date: date,
    ) -> int:
        """Store dividend data."""
        try:
            dividends = yf_ticker.dividends
            if dividends.empty:
                return 0
            
            # Filter by date range
            dividends = dividends[(dividends.index >= pd.Timestamp(start_date)) & 
                                  (dividends.index <= pd.Timestamp(end_date))]
            
            records = []
            for idx, amount in dividends.items():
                ex_date = idx.date() if hasattr(idx, 'date') else idx
                records.append({
                    "company_id": company.id,
                    "ticker": ticker,
                    "ex_date": ex_date,
                    "amount": float(amount),
                    "dividend_type": "cash",
                })
            
            if records:
                stmt = insert(Dividend.__table__).values(records)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["ticker", "ex_date", "dividend_type"]
                )
                self.db.execute(stmt)
            
            logger.info(f"Stored {len(records)} dividends for {ticker}")
            return len(records)
            
        except Exception as e:
            logger.warning(f"Could not fetch dividends for {ticker}: {e}")
            return 0
    
    def get_price_history(
        self,
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[StockPrice]:
        """Query stored price history."""
        query = self.db.query(StockPrice).filter(StockPrice.ticker == ticker)
        
        if start_date:
            query = query.filter(StockPrice.date >= start_date)
        if end_date:
            query = query.filter(StockPrice.date <= end_date)
        
        return query.order_by(StockPrice.date).all()
    
    def calculate_returns(
        self,
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Calculate price and total returns for a period."""
        prices = self.get_price_history(ticker, start_date, end_date)
        
        if len(prices) < 2:
            return {"error": "Insufficient price data"}
        
        first = prices[0]
        last = prices[-1]
        
        price_return = (float(last.close) - float(first.close)) / float(first.close)
        total_return = (float(last.adj_close) - float(first.adj_close)) / float(first.adj_close)
        
        return {
            "ticker": ticker,
            "start_date": first.date.isoformat(),
            "end_date": last.date.isoformat(),
            "start_price": float(first.close),
            "end_price": float(last.close),
            "price_return": price_return,
            "price_return_pct": f"{price_return * 100:.2f}%",
            "total_return": total_return,
            "total_return_pct": f"{total_return * 100:.2f}%",
            "dividend_contribution": total_return - price_return,
        }
