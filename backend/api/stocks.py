"""Stock price API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.services.prices import PriceService

router = APIRouter()


class PriceResponse(BaseModel):
    """Stock price data point."""
    date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    adj_close: Optional[float]
    volume: Optional[int]
    
    class Config:
        from_attributes = True


class FetchResult(BaseModel):
    """Result of a price fetch operation."""
    ticker: str
    prices: int
    splits: int
    dividends: int


class ReturnsResponse(BaseModel):
    """Return calculation result."""
    ticker: str
    start_date: str
    end_date: str
    start_price: float
    end_price: float
    price_return: float
    price_return_pct: str
    total_return: float
    total_return_pct: str
    dividend_contribution: float


@router.get("/{ticker}/prices", response_model=list[PriceResponse])
def get_prices(
    ticker: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Get historical prices for a stock."""
    service = PriceService(db)
    prices = service.get_price_history(ticker.upper(), start_date, end_date)
    
    if not prices:
        raise HTTPException(
            status_code=404,
            detail=f"No price data found for {ticker}. Try POST /api/stocks/{ticker}/fetch first."
        )
    
    return prices


@router.post("/{ticker}/fetch", response_model=FetchResult)
def fetch_prices(
    ticker: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Fetch and store price data from Yahoo Finance."""
    service = PriceService(db)
    result = service.fetch_prices(ticker.upper(), start_date, end_date)
    
    return FetchResult(ticker=ticker.upper(), **result)


@router.get("/{ticker}/returns", response_model=ReturnsResponse)
def get_returns(
    ticker: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Calculate price and total returns for a stock."""
    service = PriceService(db)
    result = service.calculate_returns(ticker.upper(), start_date, end_date)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return ReturnsResponse(**result)


@router.post("/batch/fetch")
def batch_fetch(
    tickers: list[str],
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Fetch prices for multiple tickers."""
    service = PriceService(db)
    results = []
    
    for ticker in tickers:
        try:
            result = service.fetch_prices(ticker.upper(), start_date, end_date)
            results.append({"ticker": ticker.upper(), "status": "success", **result})
        except Exception as e:
            results.append({"ticker": ticker.upper(), "status": "error", "error": str(e)})
    
    return {"results": results}
