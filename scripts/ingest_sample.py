#!/usr/bin/env python3
"""Sample data ingestion script - fetch data for a few stocks to test."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import SessionLocal
from backend.services.prices import PriceService
from backend.services.edgar import EdgarService
from backend.services.metrics import MetricsService


SAMPLE_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


def main():
    """Ingest sample data."""
    db = SessionLocal()
    
    try:
        price_service = PriceService(db)
        edgar_service = EdgarService(db)
        metrics_service = MetricsService(db)
        
        for ticker in SAMPLE_TICKERS:
            print(f"\n{'='*50}")
            print(f"Processing {ticker}")
            print('='*50)
            
            # Fetch prices
            print(f"Fetching prices for {ticker}...")
            result = price_service.fetch_prices(ticker)
            print(f"  Prices: {result['prices']}, Splits: {result['splits']}, Dividends: {result['dividends']}")
            
            # Sync company from SEC
            print(f"Syncing SEC info for {ticker}...")
            company = edgar_service.sync_company_info(ticker)
            if company:
                print(f"  CIK: {company.cik}, Name: {company.name}")
            
            # Fetch SEC filings
            print(f"Fetching SEC filings for {ticker}...")
            filings_count = edgar_service.fetch_filings(ticker)
            print(f"  Filings synced: {filings_count}")
            
            # Fetch XBRL facts
            print(f"Fetching financial facts for {ticker}...")
            facts_count = edgar_service.fetch_company_facts(ticker)
            print(f"  Facts synced: {facts_count}")
            
            # Calculate metrics
            print(f"Calculating metrics for {ticker}...")
            metrics = metrics_service.calculate_metrics(ticker)
            if "error" not in metrics:
                print(f"  Market Cap: ${metrics.get('market_cap', 0):,.0f}")
                print(f"  P/E Ratio: {metrics.get('pe_ratio', 'N/A')}")
                print(f"  EV/Revenue: {metrics.get('ev_revenue', 'N/A')}")
            else:
                print(f"  Error: {metrics['error']}")
            
            print()
        
        print("Sample ingestion complete!")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
