"""Index (S&P 500) API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.services.sp500 import SP500Service

router = APIRouter()


class ConstituentResponse(BaseModel):
    """Index constituent response."""
    ticker: str
    added_date: Optional[date]
    removed_date: Optional[date]


class SyncResult(BaseModel):
    """Sync operation result."""
    total: int
    companies_created: int
    constituents_added: int


@router.get("/sp500/constituents", response_model=list[ConstituentResponse])
def get_sp500_constituents(
    include_removed: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Get current S&P 500 constituents."""
    service = SP500Service(db)
    constituents = service.get_constituents(include_removed)
    
    return [
        ConstituentResponse(
            ticker=c.ticker,
            added_date=c.added_date,
            removed_date=c.removed_date,
        )
        for c in constituents
    ]


@router.post("/sp500/sync", response_model=SyncResult)
def sync_sp500(db: Session = Depends(get_db)):
    """Sync S&P 500 constituents from Wikipedia."""
    service = SP500Service(db)
    result = service.sync_constituents()
    
    if "error" in result:
        return {"total": 0, "companies_created": 0, "constituents_added": 0}
    
    return SyncResult(**result)


@router.post("/sp500/prices/fetch")
def fetch_sp500_prices(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(None, description="Limit number of stocks to fetch"),
    db: Session = Depends(get_db),
):
    """Fetch prices for all S&P 500 constituents."""
    service = SP500Service(db)
    result = service.fetch_all_prices(start_date, end_date, limit)
    
    return result
