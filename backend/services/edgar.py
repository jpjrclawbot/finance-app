"""SEC EDGAR data service."""

import time
import logging
from datetime import date
from typing import Optional

import requests
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from backend.models import Company, SecFiling, FinancialFact
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# SEC EDGAR API endpoints
SEC_COMPANY_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANY_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class EdgarService:
    """Service for fetching SEC EDGAR filings and financial data."""
    
    def __init__(self, db: Session):
        self.db = db
        self.headers = {
            "User-Agent": settings.sec_user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
    
    def _request(self, url: str) -> dict:
        """Make rate-limited request to SEC API."""
        time.sleep(settings.sec_rate_limit)
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def lookup_cik(self, ticker: str) -> Optional[str]:
        """Look up CIK for a ticker symbol."""
        try:
            data = self._request(SEC_COMPANY_TICKERS)
            
            for entry in data.values():
                if entry.get("ticker", "").upper() == ticker.upper():
                    # Pad CIK to 10 digits
                    cik = str(entry["cik_str"]).zfill(10)
                    return cik
            
            return None
            
        except Exception as e:
            logger.error(f"Error looking up CIK for {ticker}: {e}")
            return None
    
    def sync_company_info(self, ticker: str) -> Optional[Company]:
        """Sync company info from SEC including CIK."""
        cik = self.lookup_cik(ticker)
        if not cik:
            logger.warning(f"No CIK found for {ticker}")
            return None
        
        # Get submissions for more company details
        try:
            subs = self._request(SEC_SUBMISSIONS.format(cik=cik))
        except Exception as e:
            logger.error(f"Error fetching submissions for {ticker}: {e}")
            return None
        
        # Update or create company
        company = self.db.query(Company).filter(Company.ticker == ticker).first()
        if not company:
            company = Company(ticker=ticker)
            self.db.add(company)
        
        company.cik = cik
        company.name = subs.get("name", company.name or ticker)
        company.sic_code = subs.get("sic")
        company.state_of_incorporation = subs.get("stateOfIncorporation")
        company.fiscal_year_end = subs.get("fiscalYearEnd")
        
        self.db.commit()
        self.db.refresh(company)
        
        logger.info(f"Synced company info for {ticker} (CIK: {cik})")
        return company
    
    def fetch_filings(
        self,
        ticker: str,
        form_types: list[str] = ["10-K", "10-Q"],
        limit: int = 40,
    ) -> int:
        """Fetch recent SEC filings for a company."""
        company = self.db.query(Company).filter(Company.ticker == ticker).first()
        
        if not company or not company.cik:
            company = self.sync_company_info(ticker)
            if not company:
                return 0
        
        try:
            subs = self._request(SEC_SUBMISSIONS.format(cik=company.cik))
        except Exception as e:
            logger.error(f"Error fetching filings for {ticker}: {e}")
            return 0
        
        filings_data = subs.get("filings", {}).get("recent", {})
        if not filings_data:
            return 0
        
        records = []
        for i in range(min(limit, len(filings_data.get("form", [])))):
            form_type = filings_data["form"][i]
            if form_type not in form_types:
                continue
            
            accession = filings_data["accessionNumber"][i].replace("-", "")
            filing_date_str = filings_data["filingDate"][i]
            report_date_str = filings_data.get("reportDate", [None] * (i + 1))[i]
            
            records.append({
                "company_id": company.id,
                "cik": company.cik,
                "accession_number": filings_data["accessionNumber"][i],
                "form_type": form_type,
                "filing_date": date.fromisoformat(filing_date_str),
                "report_date": date.fromisoformat(report_date_str) if report_date_str else None,
                "primary_document": filings_data.get("primaryDocument", [None] * (i + 1))[i],
                "file_url": f"https://www.sec.gov/Archives/edgar/data/{company.cik}/{accession}",
            })
        
        if records:
            stmt = insert(SecFiling.__table__).values(records)
            stmt = stmt.on_conflict_do_nothing(index_elements=["accession_number"])
            self.db.execute(stmt)
            self.db.commit()
        
        logger.info(f"Synced {len(records)} filings for {ticker}")
        return len(records)
    
    def fetch_company_facts(self, ticker: str) -> int:
        """Fetch XBRL financial facts for a company."""
        company = self.db.query(Company).filter(Company.ticker == ticker).first()
        
        if not company or not company.cik:
            company = self.sync_company_info(ticker)
            if not company:
                return 0
        
        try:
            facts = self._request(SEC_COMPANY_FACTS.format(cik=company.cik))
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"No XBRL facts available for {ticker}")
            else:
                logger.error(f"Error fetching facts for {ticker}: {e}")
            return 0
        
        records = []
        facts_data = facts.get("facts", {})
        
        for taxonomy, concepts in facts_data.items():
            for concept_name, concept_data in concepts.items():
                units = concept_data.get("units", {})
                
                for unit_type, values in units.items():
                    for val in values:
                        # Skip if no value
                        if val.get("val") is None:
                            continue
                        
                        records.append({
                            "company_id": company.id,
                            "cik": company.cik,
                            "taxonomy": taxonomy,
                            "concept": concept_name,
                            "value": val["val"],
                            "unit": unit_type,
                            "period_start": val.get("start"),
                            "period_end": val["end"],
                            "fiscal_year": val.get("fy"),
                            "fiscal_period": val.get("fp"),
                            "instant": "start" not in val,
                        })
        
        # Batch insert (skip duplicates)
        if records:
            # Insert in chunks to avoid memory issues
            chunk_size = 1000
            for i in range(0, len(records), chunk_size):
                chunk = records[i:i + chunk_size]
                stmt = insert(FinancialFact.__table__).values(chunk)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["cik", "concept", "period_end", "fiscal_period"]
                )
                self.db.execute(stmt)
            
            self.db.commit()
        
        logger.info(f"Synced {len(records)} financial facts for {ticker}")
        return len(records)
    
    def get_shares_outstanding(self, ticker: str) -> Optional[int]:
        """Get latest shares outstanding from SEC filings."""
        company = self.db.query(Company).filter(Company.ticker == ticker).first()
        if not company:
            return None
        
        # Look for common share concepts
        share_concepts = [
            "CommonStockSharesOutstanding",
            "CommonStockSharesIssued", 
            "WeightedAverageNumberOfSharesOutstandingBasic",
        ]
        
        for concept in share_concepts:
            fact = (
                self.db.query(FinancialFact)
                .filter(
                    FinancialFact.company_id == company.id,
                    FinancialFact.concept == concept,
                    FinancialFact.unit == "shares",
                )
                .order_by(FinancialFact.period_end.desc())
                .first()
            )
            
            if fact and fact.value:
                return int(fact.value)
        
        return None
