"""S&P 500 constituent data service."""

import logging
from datetime import date
from typing import Optional

import pandas as pd
import requests
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from backend.models import Company, Index, IndexConstituent
from backend.services.prices import PriceService

logger = logging.getLogger(__name__)

# Wikipedia table with S&P 500 constituents
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class SP500Service:
    """Service for managing S&P 500 constituent data."""
    
    def __init__(self, db: Session):
        self.db = db
        self.price_service = PriceService(db)
    
    def get_or_create_index(self) -> Index:
        """Get or create the S&P 500 index record."""
        index = self.db.query(Index).filter(Index.symbol == "^GSPC").first()
        if not index:
            index = Index(symbol="^GSPC", name="S&P 500")
            self.db.add(index)
            self.db.commit()
            self.db.refresh(index)
        return index
    
    def fetch_constituents(self) -> list[dict]:
        """Fetch current S&P 500 constituents from Wikipedia."""
        try:
            tables = pd.read_html(SP500_WIKI_URL)
            # First table has the constituents
            df = tables[0]
            
            constituents = []
            for _, row in df.iterrows():
                ticker = row.get("Symbol", row.get("Ticker", ""))
                # Clean up ticker (remove footnotes, fix dots)
                ticker = str(ticker).split("[")[0].strip()
                ticker = ticker.replace(".", "-")  # Yahoo uses - instead of .
                
                constituents.append({
                    "ticker": ticker,
                    "name": row.get("Security", ""),
                    "sector": row.get("GICS Sector", ""),
                    "sub_industry": row.get("GICS Sub-Industry", ""),
                    "headquarters": row.get("Headquarters Location", ""),
                    "date_added": row.get("Date added", ""),
                    "cik": row.get("CIK", ""),
                })
            
            logger.info(f"Fetched {len(constituents)} S&P 500 constituents")
            return constituents
            
        except Exception as e:
            logger.error(f"Error fetching S&P 500 constituents: {e}")
            return []
    
    def sync_constituents(self) -> dict:
        """Sync S&P 500 constituents to database."""
        constituents = self.fetch_constituents()
        if not constituents:
            return {"error": "Failed to fetch constituents"}
        
        index = self.get_or_create_index()
        
        companies_created = 0
        constituents_added = 0
        
        for const in constituents:
            ticker = const["ticker"]
            
            # Get or create company
            company = self.db.query(Company).filter(Company.ticker == ticker).first()
            if not company:
                company = Company(
                    ticker=ticker,
                    name=const["name"],
                    cik=str(const["cik"]).zfill(10) if const["cik"] else None,
                )
                self.db.add(company)
                self.db.commit()
                self.db.refresh(company)
                companies_created += 1
            
            # Check if already in index
            existing = (
                self.db.query(IndexConstituent)
                .filter(
                    IndexConstituent.index_id == index.id,
                    IndexConstituent.ticker == ticker,
                    IndexConstituent.removed_date.is_(None),
                )
                .first()
            )
            
            if not existing:
                constituent = IndexConstituent(
                    index_id=index.id,
                    company_id=company.id,
                    ticker=ticker,
                    added_date=date.today(),
                )
                self.db.add(constituent)
                constituents_added += 1
        
        self.db.commit()
        
        return {
            "total": len(constituents),
            "companies_created": companies_created,
            "constituents_added": constituents_added,
        }
    
    def get_constituents(self, include_removed: bool = False) -> list[IndexConstituent]:
        """Get current S&P 500 constituents."""
        index = self.get_or_create_index()
        
        query = self.db.query(IndexConstituent).filter(
            IndexConstituent.index_id == index.id
        )
        
        if not include_removed:
            query = query.filter(IndexConstituent.removed_date.is_(None))
        
        return query.all()
    
    def fetch_all_prices(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """Fetch prices for all S&P 500 constituents."""
        constituents = self.get_constituents()
        
        if limit:
            constituents = constituents[:limit]
        
        results = {"success": 0, "failed": 0, "errors": []}
        
        for const in constituents:
            try:
                self.price_service.fetch_prices(const.ticker, start_date, end_date)
                results["success"] += 1
                logger.info(f"Fetched prices for {const.ticker} ({results['success']}/{len(constituents)})")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"ticker": const.ticker, "error": str(e)})
                logger.error(f"Failed to fetch prices for {const.ticker}: {e}")
        
        return results
