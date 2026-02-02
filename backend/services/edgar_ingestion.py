"""
SEC EDGAR Data Ingestion Service - Production Grade

Design principles:
1. Every fact links to its source filing for audit trail
2. Resumable - tracks progress per company
3. Rate-limited to respect SEC guidelines (10 req/sec)
4. Comprehensive error handling and logging

Data flow:
1. Get company list (from pre-built index or SEC)
2. For each company:
   a. Fetch company facts from SEC API
   b. Extract financial facts with source references
   c. Store with full audit trail
"""

import time
import logging
import json
from datetime import datetime, date
from typing import Optional, Generator
from pathlib import Path
from dataclasses import dataclass, asdict
from decimal import Decimal

import requests
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import text

from backend.database import SessionLocal, engine
from backend.models.company import Company
from backend.models.filings import SecFiling, FinancialFact

logger = logging.getLogger(__name__)

# SEC API Configuration
SEC_BASE_URL = "https://data.sec.gov"
SEC_COMPANY_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS = f"{SEC_BASE_URL}/api/xbrl/companyfacts/CIK{{cik}}.json"
SEC_SUBMISSIONS = f"{SEC_BASE_URL}/submissions/CIK{{cik}}.json"
SEC_FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"

# Financial concepts to extract (comprehensive list)
INCOME_STATEMENT_CONCEPTS = [
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
    "CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold",
    "GrossProfit",
    "OperatingExpenses", "SellingGeneralAndAdministrativeExpense",
    "ResearchAndDevelopmentExpense", "GeneralAndAdministrativeExpense",
    "OperatingIncomeLoss",
    "InterestExpense", "InterestIncome", "InterestIncomeExpenseNet",
    "OtherNonoperatingIncomeExpense",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
    "IncomeTaxExpenseBenefit",
    "NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic",
    "EarningsPerShareBasic", "EarningsPerShareDiluted",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfSharesOutstandingDiluted",
]

BALANCE_SHEET_CONCEPTS = [
    # Assets
    "Assets", "AssetsCurrent", "AssetsNoncurrent",
    "CashAndCashEquivalentsAtCarryingValue", "Cash",
    "ShortTermInvestments", "MarketableSecuritiesCurrent",
    "AccountsReceivableNetCurrent", "AccountsReceivableNet",
    "InventoryNet", "InventoryFinishedGoods", "InventoryRawMaterials",
    "PrepaidExpenseAndOtherAssetsCurrent",
    "PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipmentGross",
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
    "Goodwill", "IntangibleAssetsNetExcludingGoodwill", "OtherAssetsNoncurrent",
    # Liabilities
    "Liabilities", "LiabilitiesCurrent", "LiabilitiesNoncurrent",
    "AccountsPayableCurrent", "AccountsPayable",
    "AccruedLiabilitiesCurrent", "EmployeeRelatedLiabilitiesCurrent",
    "ShortTermBorrowings", "LongTermDebtCurrent",
    "LongTermDebt", "LongTermDebtNoncurrent",
    "DeferredRevenueCurrent", "DeferredRevenueNoncurrent",
    "OtherLiabilitiesNoncurrent",
    # Equity
    "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "CommonStockSharesOutstanding", "CommonStockSharesIssued", "CommonStockSharesAuthorized",
    "CommonStockValue", "AdditionalPaidInCapital",
    "RetainedEarningsAccumulatedDeficit", "TreasuryStockValue",
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax",
]

CASH_FLOW_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInFinancingActivities",
    "DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
    "ShareBasedCompensation", "StockIssuedDuringPeriodValueShareBasedCompensation",
    "DeferredIncomeTaxExpenseBenefit",
    "PaymentsToAcquirePropertyPlantAndEquipment", "CapitalExpendituresIncurredButNotYetPaid",
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
    "ProceedsFromIssuanceOfLongTermDebt", "RepaymentsOfLongTermDebt",
    "PaymentsOfDividends", "PaymentsOfDividendsCommonStock",
    "PaymentsForRepurchaseOfCommonStock",
    "ProceedsFromIssuanceOfCommonStock",
    "EffectOfExchangeRateOnCashAndCashEquivalents",
]

ALL_CONCEPTS = set(INCOME_STATEMENT_CONCEPTS + BALANCE_SHEET_CONCEPTS + CASH_FLOW_CONCEPTS)


@dataclass
class CompanyInfo:
    cik: str
    ticker: str
    name: str
    market_cap: Optional[float] = None
    exchange: Optional[str] = None
    

@dataclass
class FactRecord:
    """A single financial fact with full source tracking."""
    cik: str
    taxonomy: str
    concept: str
    value: float
    unit: str
    period_end: str
    period_start: Optional[str]
    fiscal_year: Optional[int]
    fiscal_period: Optional[str]
    accession_number: Optional[str]
    filing_url: Optional[str]
    frame: Optional[str]
    instant: bool


class EdgarIngestionService:
    """Production-grade SEC EDGAR data ingestion."""
    
    def __init__(self, user_agent: str):
        """
        Initialize ingestion service.
        
        Args:
            user_agent: Required by SEC - include your email
                       Example: "FinanceApp admin@company.com"
        """
        self.user_agent = user_agent
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }
        self.request_count = 0
        self.last_request_time = 0
        self.rate_limit_delay = 0.1  # 10 requests per second
        
        # Progress tracking
        self.data_dir = Path(__file__).parent.parent.parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def _rate_limited_request(self, url: str, retries: int = 3) -> Optional[dict]:
        """Make rate-limited request to SEC API with retries."""
        for attempt in range(retries):
            # Enforce rate limit
            elapsed = time.time() - self.last_request_time
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
            
            self.last_request_time = time.time()
            self.request_count += 1
            
            try:
                response = requests.get(url, headers=self.headers, timeout=30)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                elif response.status_code == 429:
                    # Rate limited - back off
                    wait = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    logger.warning(f"HTTP {response.status_code} for {url}")
                    if attempt < retries - 1:
                        time.sleep(1)
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout for {url}, attempt {attempt + 1}")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Request error for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(1)
        
        return None
    
    def get_all_sec_companies(self) -> list[CompanyInfo]:
        """Get all SEC-registered companies."""
        logger.info("Fetching SEC company registry...")
        data = self._rate_limited_request(SEC_COMPANY_TICKERS)
        
        if not data:
            raise RuntimeError("Failed to fetch SEC company list")
        
        companies = []
        for entry in data.values():
            companies.append(CompanyInfo(
                cik=str(entry["cik_str"]).zfill(10),
                ticker=entry.get("ticker", ""),
                name=entry.get("title", ""),
            ))
        
        logger.info(f"Found {len(companies)} SEC-registered companies")
        return companies
    
    def fetch_company_facts(self, cik: str) -> Optional[dict]:
        """
        Fetch all XBRL facts for a company.
        
        Returns the full Company Facts API response which includes:
        - Company metadata
        - All reported facts organized by taxonomy and concept
        - Each fact includes the filing frame (accession info)
        """
        url = SEC_COMPANY_FACTS.format(cik=cik)
        return self._rate_limited_request(url)
    
    def extract_facts(self, cik: str, facts_data: dict, min_year: int = 1990) -> Generator[FactRecord, None, None]:
        """
        Extract financial facts from Company Facts API response.
        
        Yields FactRecord objects with full source tracking.
        """
        company_name = facts_data.get("entityName", "")
        facts_by_taxonomy = facts_data.get("facts", {})
        
        for taxonomy, concepts in facts_by_taxonomy.items():
            for concept_name, concept_data in concepts.items():
                # Only extract concepts we care about
                if concept_name not in ALL_CONCEPTS:
                    continue
                
                units = concept_data.get("units", {})
                
                for unit_type, values in units.items():
                    for val in values:
                        # Skip if no value
                        if val.get("val") is None:
                            continue
                        
                        period_end = val.get("end")
                        if not period_end:
                            continue
                        
                        # Filter by year
                        try:
                            end_date = date.fromisoformat(period_end)
                            if end_date.year < min_year:
                                continue
                        except ValueError:
                            continue
                        
                        # Extract accession number from frame if available
                        frame = val.get("frame")  # e.g., "CY2023Q1" or "CY2023Q1I"
                        accession = val.get("accn")  # Direct accession if provided
                        
                        # Build filing URL if we have accession
                        filing_url = None
                        if accession:
                            # Format: 0000320193-23-000077 -> 000032019323000077
                            clean_accession = accession.replace("-", "")
                            filing_url = SEC_FILING_URL.format(
                                cik=cik.lstrip("0"),
                                accession=clean_accession
                            )
                        
                        yield FactRecord(
                            cik=cik,
                            taxonomy=taxonomy,
                            concept=concept_name,
                            value=val["val"],
                            unit=unit_type,
                            period_end=period_end,
                            period_start=val.get("start"),
                            fiscal_year=val.get("fy"),
                            fiscal_period=val.get("fp"),
                            accession_number=accession,
                            filing_url=filing_url,
                            frame=frame,
                            instant="start" not in val,
                        )
    
    def store_facts(self, db: Session, company_id: int, facts: list[FactRecord]) -> int:
        """Store facts with upsert logic. Returns count of facts stored."""
        if not facts:
            return 0
        
        records = []
        for fact in facts:
            records.append({
                "company_id": company_id,
                "cik": fact.cik,
                "taxonomy": fact.taxonomy,
                "concept": fact.concept,
                "value": Decimal(str(fact.value)),
                "unit": fact.unit,
                "period_end": fact.period_end,
                "period_start": fact.period_start,
                "fiscal_year": fact.fiscal_year,
                "fiscal_period": fact.fiscal_period,
                "accession_number": fact.accession_number,
                "filing_url": fact.filing_url,
                "frame": fact.frame,
                "instant": fact.instant,
            })
        
        # Batch insert with conflict handling
        chunk_size = 500
        total_stored = 0
        
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            
            stmt = insert(FinancialFact.__table__).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["cik", "concept", "period_end", "fiscal_period"],
                set_={
                    "value": stmt.excluded.value,
                    "accession_number": stmt.excluded.accession_number,
                    "filing_url": stmt.excluded.filing_url,
                    "frame": stmt.excluded.frame,
                }
            )
            db.execute(stmt)
            total_stored += len(chunk)
        
        return total_stored
    
    def process_company(
        self,
        db: Session,
        company: CompanyInfo,
        min_year: int = 1990
    ) -> dict:
        """
        Process a single company - fetch and store all financials.
        
        Returns status dict with counts and any errors.
        """
        result = {
            "ticker": company.ticker,
            "cik": company.cik,
            "status": "pending",
            "facts_count": 0,
            "error": None,
        }
        
        try:
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
            
            # Fetch company facts from SEC
            facts_data = self.fetch_company_facts(company.cik)
            
            if not facts_data:
                result["status"] = "no_data"
                result["error"] = "No XBRL data available from SEC"
                return result
            
            # Extract and store facts
            facts = list(self.extract_facts(company.cik, facts_data, min_year))
            stored = self.store_facts(db, db_company.id, facts)
            
            db.commit()
            
            result["status"] = "ok"
            result["facts_count"] = stored
            
        except Exception as e:
            db.rollback()
            result["status"] = "error"
            result["error"] = str(e)
            logger.error(f"Error processing {company.ticker}: {e}")
        
        return result
    
    def run_ingestion(
        self,
        companies: list[CompanyInfo],
        min_year: int = 1990,
        progress_callback: callable = None,
    ) -> dict:
        """
        Run ingestion for a list of companies.
        
        Args:
            companies: List of companies to process
            min_year: Earliest year to fetch data for
            progress_callback: Optional callback(current, total, result) for progress updates
        
        Returns:
            Summary dict with counts
        """
        logger.info(f"Starting ingestion for {len(companies)} companies...")
        
        summary = {
            "total": len(companies),
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "no_data": 0,
            "total_facts": 0,
            "results": [],
        }
        
        db = SessionLocal()
        
        try:
            for i, company in enumerate(companies):
                result = self.process_company(db, company, min_year)
                
                summary["processed"] += 1
                summary["results"].append(result)
                
                if result["status"] == "ok":
                    summary["succeeded"] += 1
                    summary["total_facts"] += result["facts_count"]
                elif result["status"] == "no_data":
                    summary["no_data"] += 1
                else:
                    summary["failed"] += 1
                
                if progress_callback:
                    progress_callback(i + 1, len(companies), result)
                
                # Log progress every 10 companies
                if (i + 1) % 10 == 0:
                    logger.info(
                        f"Progress: {i + 1}/{len(companies)} | "
                        f"OK: {summary['succeeded']} | "
                        f"Failed: {summary['failed']} | "
                        f"Facts: {summary['total_facts']}"
                    )
        
        finally:
            db.close()
        
        logger.info(f"Ingestion complete: {summary['succeeded']}/{summary['total']} succeeded")
        return summary


def load_company_list(filepath: Path) -> list[CompanyInfo]:
    """Load pre-built company list from JSON file."""
    with open(filepath) as f:
        data = json.load(f)
    
    companies = []
    for c in data.get("companies", []):
        companies.append(CompanyInfo(
            cik=c["cik"],
            ticker=c["ticker"],
            name=c["name"],
            market_cap=c.get("market_cap"),
        ))
    
    return companies
