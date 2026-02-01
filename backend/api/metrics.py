"""Valuation metrics API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.metrics import MetricsService

router = APIRouter()


@router.get("/{ticker}")
def get_metrics(
    ticker: str,
    as_of: Optional[date] = Query(None, description="Calculate as of this date"),
    db: Session = Depends(get_db),
):
    """Calculate valuation metrics for a stock."""
    service = MetricsService(db)
    result = service.calculate_metrics(ticker.upper(), as_of)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.post("/{ticker}/store")
def store_metrics(
    ticker: str,
    as_of: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Calculate and store valuation metrics."""
    service = MetricsService(db)
    result = service.store_metrics(ticker.upper(), as_of)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.post("/batch/calculate")
def batch_calculate_metrics(
    tickers: list[str],
    as_of: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Calculate metrics for multiple tickers."""
    service = MetricsService(db)
    results = []
    
    for ticker in tickers:
        result = service.calculate_metrics(ticker.upper(), as_of)
        results.append(result)
    
    return {"results": results}
