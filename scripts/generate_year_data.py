#!/usr/bin/env python3
"""Generate a year of realistic price data for demo companies."""

import sys
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal
import random
import math

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import engine, Base, SessionLocal
from backend.models.company import Company
from backend.models.prices import StockPrice
from backend.models.filings import FinancialFact
from backend.models.metrics import ValuationMetric

# Starting prices (1 year ago) and current targets
STOCK_CONFIG = {
    "AAPL": {"start": 185.0, "end": 246.30, "volatility": 0.015, "volume_base": 45000000},
    "NVDA": {"start": 85.0, "end": 158.20, "volatility": 0.025, "volume_base": 280000000},
    "TSLA": {"start": 250.0, "end": 476.80, "volatility": 0.035, "volume_base": 85000000},
    "NFLX": {"start": 580.0, "end": 1045.50, "volatility": 0.020, "volume_base": 4000000},
}


def generate_price_path(start_price, end_price, days, volatility):
    """Generate realistic price path using geometric Brownian motion with drift."""
    prices = [start_price]
    
    # Calculate drift needed to hit target
    total_return = end_price / start_price
    daily_drift = (math.log(total_return)) / days
    
    for i in range(1, days):
        # Random walk with drift
        daily_return = daily_drift + volatility * random.gauss(0, 1)
        new_price = prices[-1] * math.exp(daily_return)
        prices.append(new_price)
    
    # Ensure we hit the target on the last day (with small adjustment)
    prices[-1] = end_price
    
    return prices


def generate_ohlc(close_price, volatility):
    """Generate realistic OHLC from close price."""
    daily_range = close_price * volatility * random.uniform(0.5, 1.5)
    
    high = close_price + daily_range * random.uniform(0.3, 0.7)
    low = close_price - daily_range * random.uniform(0.3, 0.7)
    
    # Open somewhere between low and high
    open_price = low + (high - low) * random.uniform(0.2, 0.8)
    
    return open_price, high, low


def get_trading_days(start_date, end_date):
    """Get list of trading days (skip weekends)."""
    days = []
    current = start_date
    while current <= end_date:
        # Skip weekends (5 = Saturday, 6 = Sunday)
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def main():
    """Generate a year of price data."""
    print("Generating 1 year of price data...")
    
    # Date range: 1 year ago to today
    end_date = date(2026, 1, 31)
    start_date = date(2025, 2, 1)
    
    trading_days = get_trading_days(start_date, end_date)
    num_days = len(trading_days)
    
    print(f"Trading days: {num_days}")
    
    db = SessionLocal()
    
    try:
        # Clear existing prices
        db.query(StockPrice).delete()
        db.commit()
        
        for ticker, config in STOCK_CONFIG.items():
            print(f"Generating prices for {ticker}...")
            
            # Get company
            company = db.query(Company).filter(Company.ticker == ticker).first()
            if not company:
                print(f"  Company {ticker} not found, skipping")
                continue
            
            # Generate price path
            closes = generate_price_path(
                config["start"],
                config["end"],
                num_days,
                config["volatility"]
            )
            
            # Create price records
            for i, day in enumerate(trading_days):
                close = closes[i]
                open_price, high, low = generate_ohlc(close, config["volatility"])
                
                # Ensure OHLC consistency
                high = max(high, open_price, close)
                low = min(low, open_price, close)
                
                # Volume with some randomness
                volume = int(config["volume_base"] * random.uniform(0.6, 1.4))
                
                db.add(StockPrice(
                    company_id=company.id,
                    ticker=ticker,
                    date=day,
                    open=Decimal(str(round(open_price, 2))),
                    high=Decimal(str(round(high, 2))),
                    low=Decimal(str(round(low, 2))),
                    close=Decimal(str(round(close, 2))),
                    adj_close=Decimal(str(round(close, 2))),
                    volume=volume,
                ))
            
            print(f"  Added {num_days} price records for {ticker}")
        
        db.commit()
        print("\nDone! Year of price data generated.")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
