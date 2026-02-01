"""SEC filings API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.models import Company, SecFiling
from backend.services.edgar import EdgarService

router = APIRouter()


class CompanyResponse(BaseModel):
    """Company info response."""
    id: int
    ticker: Optional[str]
    name: str
    cik: Optional[str]
    sic_code: Optional[str]
    state_of_incorporation: Optional[str]
    fiscal_year_end: Optional[str]
    
    class Config:
        from_attributes = True


class FilingResponse(BaseModel):
    """SEC filing response."""
    id: int
    cik: str
    accession_number: str
    form_type: str
    filing_date: str
    report_date: Optional[str]
    file_url: Optional[str]
    
    class Config:
        from_attributes = True


@router.get("/{ticker}/company", response_model=CompanyResponse)
def get_company(
    ticker: str,
    db: Session = Depends(get_db),
):
    """Get company info including CIK."""
    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    
    if not company:
        # Try to sync from SEC
        service = EdgarService(db)
        company = service.sync_company_info(ticker.upper())
        
        if not company:
            raise HTTPException(status_code=404, detail=f"Company not found: {ticker}")
    
    return company


@router.post("/{ticker}/sync")
def sync_company(
    ticker: str,
    db: Session = Depends(get_db),
):
    """Sync company info from SEC EDGAR."""
    service = EdgarService(db)
    company = service.sync_company_info(ticker.upper())
    
    if not company:
        raise HTTPException(status_code=404, detail=f"Could not find {ticker} in SEC database")
    
    return {
        "ticker": company.ticker,
        "name": company.name,
        "cik": company.cik,
    }


@router.get("/{ticker}/filings", response_model=list[FilingResponse])
def get_filings(
    ticker: str,
    form_type: Optional[str] = Query(None, description="Filter by form type (10-K, 10-Q)"),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Get SEC filings for a company."""
    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    
    if not company:
        raise HTTPException(status_code=404, detail=f"Company not found: {ticker}")
    
    query = db.query(SecFiling).filter(SecFiling.company_id == company.id)
    
    if form_type:
        query = query.filter(SecFiling.form_type == form_type.upper())
    
    filings = query.order_by(SecFiling.filing_date.desc()).limit(limit).all()
    
    return filings


@router.post("/{ticker}/filings/fetch")
def fetch_filings(
    ticker: str,
    form_types: list[str] = Query(["10-K", "10-Q"]),
    limit: int = Query(40, le=100),
    db: Session = Depends(get_db),
):
    """Fetch SEC filings from EDGAR."""
    service = EdgarService(db)
    count = service.fetch_filings(ticker.upper(), form_types, limit)
    
    return {
        "ticker": ticker.upper(),
        "filings_synced": count,
    }


@router.post("/{ticker}/facts/fetch")
def fetch_facts(
    ticker: str,
    db: Session = Depends(get_db),
):
    """Fetch XBRL financial facts from SEC."""
    service = EdgarService(db)
    count = service.fetch_company_facts(ticker.upper())
    
    return {
        "ticker": ticker.upper(),
        "facts_synced": count,
    }


@router.get("/{ticker}/shares")
def get_shares_outstanding(
    ticker: str,
    db: Session = Depends(get_db),
):
    """Get latest shares outstanding from SEC filings."""
    service = EdgarService(db)
    shares = service.get_shares_outstanding(ticker.upper())
    
    if shares is None:
        raise HTTPException(
            status_code=404,
            detail=f"No shares outstanding data for {ticker}. Try POST /api/filings/{ticker}/facts/fetch first."
        )
    
    return {
        "ticker": ticker.upper(),
        "shares_outstanding": shares,
    }
