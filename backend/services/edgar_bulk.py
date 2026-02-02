"""
Bulk SEC EDGAR data ingestion service.

Fetches quarterly financials for all public companies from SEC EDGAR.
Uses the Company Facts API for structured XBRL data (available from ~2009+).

Rate limit: 10 requests/second per SEC guidelines.
"""

import time
import logging
import json
from datetime import datetime, date
from typing import Optional
from pathlib import Path
from dataclasses import dataclass
from decimal import Decimal

import requests
import yfinance as yf
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import text

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.filings import SecFiling, FinancialFact

logger = logging.getLogger(__name__)

# SEC API endpoints
SEC_COMPANY_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"

# Key financial concepts to extract
FINANCIAL_CONCEPTS = [
    # Income Statement
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "NetIncomeLoss",
    "GrossProfit",
    "OperatingIncomeLoss",
    "CostOfGoodsAndServicesSold",
    "CostOfRevenue",
    "ResearchAndDevelopmentExpense",
    "SellingGeneralAndAdministrativeExpense",
    "InterestExpense",
    "IncomeTaxExpenseBenefit",
    "EarningsPerShareBasic",
    "EarningsPerShareDiluted",
    
    # Balance Sheet
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "AccountsReceivableNetCurrent",
    "InventoryNet",
    "PropertyPlantAndEquipmentNet",
    "Goodwill",
    "IntangibleAssetsNetExcludingGoodwill",
    "LongTermDebt",
    "LongTermDebtNoncurrent",
    "ShortTermBorrowings",
    "AccountsPayableCurrent",
    "CommonStockSharesOutstanding",
    "CommonStockSharesIssued",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfSharesOutstandingDiluted",
    
    # Cash Flow
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInFinancingActivities",
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsOfDividends",
    "PaymentsForRepurchaseOfCommonStock",
]


@dataclass
class CompanyInfo:
    """Company info with market cap for sorting."""
    cik: str
    ticker: str
    name: str
    market_cap: float
    

class EdgarBulkService:
    """Service for bulk EDGAR data ingestion."""
    
    def __init__(self, user_agent: str = "FinanceApp contact@example.com"):
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self.request_count = 0
        self.last_request_time = 0
        self.rate_limit = 0.1  # 10 requests per second
        
        # Progress tracking
        self.progress_file = Path(__file__).parent.parent.parent / "data" / "ingestion_progress.json"
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _rate_limited_request(self, url: str) -> Optional[dict]:
        """Make rate-limited request to SEC API."""
        # Enforce rate limit
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        
        self.last_request_time = time.time()
        self.request_count += 1
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(f"SEC API returned {response.status_code} for {url}")
                return None
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
    
    def get_all_companies(self) -> list[dict]:
        """Get all SEC-registered companies."""
        logger.info("Fetching all SEC-registered companies...")
        data = self._rate_limited_request(SEC_COMPANY_TICKERS)
        
        if not data:
            return []
        
        companies = []
        for entry in data.values():
            companies.append({
                "cik": str(entry["cik_str"]).zfill(10),
                "ticker": entry.get("ticker", ""),
                "name": entry.get("title", ""),
            })
        
        logger.info(f"Found {len(companies)} SEC-registered companies")
        return companies
    
    def get_market_caps(self, tickers: list[str], batch_size: int = 100) -> dict[str, float]:
        """Get market caps for tickers using Yahoo Finance."""
        logger.info(f"Fetching market caps for {len(tickers)} tickers...")
        market_caps = {}
        
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i+batch_size]
            batch_str = " ".join(batch)
            
            try:
                data = yf.download(batch_str, period="1d", progress=False)
                
                for ticker in batch:
                    try:
                        info = yf.Ticker(ticker).info
                        mc = info.get("marketCap", 0)
                        if mc:
                            market_caps[ticker] = mc
                    except:
                        pass
                
                logger.info(f"Processed {min(i+batch_size, len(tickers))}/{len(tickers)} tickers")
                time.sleep(1)  # Rate limit Yahoo
                
            except Exception as e:
                logger.warning(f"Error fetching batch: {e}")
        
        return market_caps
    
    def load_pregenerated_companies(self) -> list[CompanyInfo]:
        """Load pre-generated company list from top_companies.json."""
        companies_file = Path(__file__).parent.parent.parent / "data" / "top_companies.json"
        
        if not companies_file.exists():
            logger.warning(f"Pre-generated company list not found: {companies_file}")
            return []
        
        with open(companies_file) as f:
            data = json.load(f)
        
        companies = []
        for c in data.get("companies", []):
            companies.append(CompanyInfo(
                cik=c["cik"],
                ticker=c["ticker"],
                name=c["name"],
                market_cap=c.get("market_cap", 0),
            ))
        
        logger.info(f"Loaded {len(companies)} companies from pre-generated list")
        return companies
    
    def get_top_companies_by_market_cap(self, limit: int = 2500) -> list[CompanyInfo]:
        """Get top N companies by market cap. Uses pre-generated list if available."""
        # Try to use pre-generated list first
        companies = self.load_pregenerated_companies()
        
        if companies:
            # Already sorted by market cap in the file
            return companies[:limit]
        
        # Fallback to fetching dynamically (slow)
        logger.info("Falling back to dynamic market cap fetch (this will be slow)...")
        
        # Get all SEC companies
        all_companies = self.get_all_companies()
        
        # Filter to those with tickers
        tickers = [c["ticker"] for c in all_companies if c["ticker"]]
        
        # Get market caps
        market_caps = self.get_market_caps(tickers)
        
        # Build sorted list
        companies_with_mc = []
        for company in all_companies:
            ticker = company["ticker"]
            if ticker in market_caps:
                companies_with_mc.append(CompanyInfo(
                    cik=company["cik"],
                    ticker=ticker,
                    name=company["name"],
                    market_cap=market_caps[ticker],
                ))
        
        # Sort by market cap descending
        companies_with_mc.sort(key=lambda x: x.market_cap, reverse=True)
        
        return companies_with_mc[:limit]
    
    def fetch_company_facts(self, cik: str) -> Optional[dict]:
        """Fetch all XBRL facts for a company."""
        url = SEC_COMPANY_FACTS.format(cik=cik)
        return self._rate_limited_request(url)
    
    def process_company(self, db: Session, company: CompanyInfo, min_year: int = 1990) -> dict:
        """Process a single company - fetch and store all financials."""
        logger.info(f"Processing {company.ticker} (CIK: {company.cik})...")
        
        # Get or create company record
        db_company = db.query(Company).filter(Company.cik == company.cik).first()
        if not db_company:
            db_company = Company(
                cik=company.cik,
                ticker=company.ticker,
                name=company.name,
            )
            db.add(db_company)
            db.flush()
        
        # Fetch company facts
        facts_data = self.fetch_company_facts(company.cik)
        if not facts_data:
            logger.warning(f"No XBRL data for {company.ticker}")
            return {"ticker": company.ticker, "status": "no_data", "facts": 0}
        
        # Process facts
        facts_added = 0
        facts_by_taxonomy = facts_data.get("facts", {})
        
        for taxonomy, concepts in facts_by_taxonomy.items():
            for concept_name, concept_data in concepts.items():
                # Only process concepts we care about
                if concept_name not in FINANCIAL_CONCEPTS:
                    continue
                
                units = concept_data.get("units", {})
                
                for unit_type, values in units.items():
                    records = []
                    for val in values:
                        # Skip if no value or too old
                        if val.get("val") is None:
                            continue
                        
                        period_end = val.get("end")
                        if not period_end:
                            continue
                        
                        try:
                            end_date = date.fromisoformat(period_end)
                            if end_date.year < min_year:
                                continue
                        except:
                            continue
                        
                        records.append({
                            "company_id": db_company.id,
                            "cik": company.cik,
                            "taxonomy": taxonomy,
                            "concept": concept_name,
                            "value": val["val"],
                            "unit": unit_type,
                            "period_start": val.get("start"),
                            "period_end": period_end,
                            "fiscal_year": val.get("fy"),
                            "fiscal_period": val.get("fp"),
                            "instant": "start" not in val,
                        })
                    
                    if records:
                        # Upsert records
                        stmt = insert(FinancialFact.__table__).values(records)
                        stmt = stmt.on_conflict_do_nothing(
                            index_elements=["cik", "concept", "period_end", "fiscal_period"]
                        )
                        db.execute(stmt)
                        facts_added += len(records)
        
        db.commit()
        logger.info(f"  Added {facts_added} facts for {company.ticker}")
        
        return {"ticker": company.ticker, "status": "ok", "facts": facts_added}
    
    def save_progress(self, progress: dict):
        """Save ingestion progress to file."""
        with open(self.progress_file, "w") as f:
            json.dump(progress, f, indent=2, default=str)
    
    def load_progress(self) -> dict:
        """Load ingestion progress from file."""
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                return json.load(f)
        return {"completed": [], "failed": [], "last_index": 0}
    
    def run_bulk_ingestion(
        self,
        limit: int = 2500,
        min_year: int = 1990,
        resume: bool = True,
    ) -> dict:
        """
        Run bulk ingestion for top N companies.
        
        Args:
            limit: Number of companies to process
            min_year: Earliest year to fetch data for
            resume: Whether to resume from previous progress
        """
        logger.info(f"Starting bulk ingestion for top {limit} companies...")
        
        # Load progress
        progress = self.load_progress() if resume else {"completed": [], "failed": [], "last_index": 0}
        
        # Get top companies
        companies = self.get_top_companies_by_market_cap(limit)
        logger.info(f"Found {len(companies)} companies to process")
        
        # Save company list
        progress["total"] = len(companies)
        progress["companies"] = [
            {"ticker": c.ticker, "cik": c.cik, "market_cap": c.market_cap}
            for c in companies
        ]
        self.save_progress(progress)
        
        # Process each company
        db = SessionLocal()
        start_index = progress.get("last_index", 0)
        
        try:
            for i, company in enumerate(companies[start_index:], start=start_index):
                if company.ticker in progress["completed"]:
                    continue
                
                try:
                    result = self.process_company(db, company, min_year)
                    
                    if result["status"] == "ok":
                        progress["completed"].append(company.ticker)
                    else:
                        progress["failed"].append({
                            "ticker": company.ticker,
                            "reason": result["status"],
                        })
                    
                except Exception as e:
                    logger.error(f"Error processing {company.ticker}: {e}")
                    db.rollback()  # Rollback on error so session stays usable
                    progress["failed"].append({
                        "ticker": company.ticker,
                        "reason": str(e),
                    })
                
                progress["last_index"] = i + 1
                progress["last_updated"] = datetime.now().isoformat()
                
                # Save progress every 10 companies
                if (i + 1) % 10 == 0:
                    self.save_progress(progress)
                    logger.info(f"Progress: {i+1}/{len(companies)} companies processed")
        
        finally:
            db.close()
            self.save_progress(progress)
        
        logger.info(f"Bulk ingestion complete: {len(progress['completed'])} succeeded, {len(progress['failed'])} failed")
        return progress


def run_ingestion(limit: int = 2500, min_year: int = 1990, user_agent: str = None):
    """Entry point for bulk ingestion."""
    if not user_agent:
        user_agent = "FinanceApp contact@example.com"  # Update this!
    
    service = EdgarBulkService(user_agent=user_agent)
    return service.run_bulk_ingestion(limit=limit, min_year=min_year)


if __name__ == "__main__":
    import sys
    
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2500
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    run_ingestion(limit=limit)
