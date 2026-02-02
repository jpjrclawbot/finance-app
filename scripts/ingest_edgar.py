#!/usr/bin/env python3
"""
SEC EDGAR Data Ingestion Script

This is the main entry point for bulk data ingestion.
Processes companies from largest to smallest market cap.

Usage:
    # Quick test (10 companies)
    python scripts/ingest_edgar.py --test
    
    # Full run with S&P 500 + 400 + NASDAQ 100
    python scripts/ingest_edgar.py --full
    
    # Custom limit
    python scripts/ingest_edgar.py --limit 100

Progress is saved and can be resumed.
"""

import sys
import argparse
import logging
import json
import time
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import requests

from backend.services.edgar_ingestion import (
    EdgarIngestionService,
    CompanyInfo,
    load_company_list,
)
from backend.database import engine
from sqlalchemy import text


# Configure logging
def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    
    # Create logs directory
    log_dir = Path(__file__).parent.parent / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"ingestion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file),
        ]
    )
    
    return logging.getLogger(__name__)


def fetch_html(url: str) -> str:
    """Fetch HTML with proper headers to avoid 403."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text


def get_sp500_companies() -> list[dict]:
    """Fetch S&P 500 companies from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    html = fetch_html(url)
    tables = pd.read_html(html)
    df = tables[0]
    
    companies = []
    for _, row in df.iterrows():
        ticker = str(row.get("Symbol", "")).replace(".", "-")
        companies.append({
            "ticker": ticker,
            "name": row.get("Security", ""),
            "sector": row.get("GICS Sector", ""),
            "industry": row.get("GICS Sub-Industry", ""),
        })
    
    return companies


def get_sp400_companies() -> list[dict]:
    """Fetch S&P 400 MidCap companies."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    try:
        html = fetch_html(url)
        tables = pd.read_html(html)
        df = tables[0]
        
        ticker_col = "Ticker symbol" if "Ticker symbol" in df.columns else "Symbol"
        name_col = "Company" if "Company" in df.columns else "Security"
        
        companies = []
        for _, row in df.iterrows():
            ticker = str(row.get(ticker_col, "")).replace(".", "-")
            companies.append({
                "ticker": ticker,
                "name": row.get(name_col, ""),
            })
        
        return companies
    except Exception as e:
        logging.warning(f"Could not fetch S&P 400: {e}")
        return []


def get_sec_cik_mapping() -> dict[str, str]:
    """Get ticker to CIK mapping from SEC."""
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {
        "User-Agent": "FinanceApp admin@openclaw.ai",
        "Accept": "application/json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    
    mapping = {}
    for entry in data.values():
        ticker = entry.get("ticker", "")
        cik = str(entry.get("cik_str", "")).zfill(10)
        name = entry.get("title", "")
        if ticker:
            mapping[ticker] = {"cik": cik, "name": name}
    
    return mapping


def get_market_caps(tickers: list[str], logger) -> dict[str, float]:
    """Get market caps using Yahoo Finance."""
    import yfinance as yf
    
    market_caps = {}
    batch_size = 20
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        logger.info(f"Fetching market caps: {i + len(batch)}/{len(tickers)}")
        
        for ticker in batch:
            try:
                info = yf.Ticker(ticker).info
                mc = info.get("marketCap")
                if mc and mc > 0:
                    market_caps[ticker] = mc
            except Exception:
                pass
            time.sleep(0.1)
        
        time.sleep(0.5)  # Rate limit
    
    return market_caps


def build_company_list(logger, limit: int = None) -> list[CompanyInfo]:
    """Build comprehensive company list sorted by market cap."""
    
    logger.info("=" * 60)
    logger.info("BUILDING COMPANY LIST")
    logger.info("=" * 60)
    
    # Get companies from indices
    logger.info("Fetching S&P 500...")
    sp500 = get_sp500_companies()
    logger.info(f"  Found {len(sp500)} S&P 500 companies")
    
    logger.info("Fetching S&P 400...")
    sp400 = get_sp400_companies()
    logger.info(f"  Found {len(sp400)} S&P 400 companies")
    
    # Combine and dedupe
    all_companies = {}
    for c in sp500 + sp400:
        ticker = c["ticker"]
        if ticker and ticker not in all_companies:
            all_companies[ticker] = c
    
    logger.info(f"Combined unique tickers: {len(all_companies)}")
    
    # Get SEC CIK mapping
    logger.info("Fetching SEC CIK mappings...")
    sec_mapping = get_sec_cik_mapping()
    
    # Filter to companies with SEC filings
    tickers_with_cik = [t for t in all_companies.keys() if t in sec_mapping]
    logger.info(f"Companies with SEC filings: {len(tickers_with_cik)}")
    
    # Get market caps
    logger.info("Fetching market caps (this takes a few minutes)...")
    market_caps = get_market_caps(tickers_with_cik, logger)
    logger.info(f"Got market caps for {len(market_caps)} companies")
    
    # Build final list
    companies = []
    for ticker in tickers_with_cik:
        if ticker in market_caps:
            sec_info = sec_mapping[ticker]
            company_info = all_companies.get(ticker, {})
            
            companies.append(CompanyInfo(
                cik=sec_info["cik"],
                ticker=ticker,
                name=sec_info.get("name") or company_info.get("name", ""),
                market_cap=market_caps[ticker],
            ))
    
    # Sort by market cap (largest first)
    companies.sort(key=lambda x: x.market_cap or 0, reverse=True)
    
    if limit:
        companies = companies[:limit]
    
    logger.info(f"Final company list: {len(companies)} companies")
    
    # Save the list
    output_file = Path(__file__).parent.parent / "data" / "company_list.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "count": len(companies),
            "companies": [
                {
                    "ticker": c.ticker,
                    "cik": c.cik,
                    "name": c.name,
                    "market_cap": c.market_cap,
                }
                for c in companies
            ]
        }, f, indent=2)
    
    logger.info(f"Saved company list to {output_file}")
    
    # Show top 10
    logger.info("\nTop 10 by market cap:")
    for i, c in enumerate(companies[:10], 1):
        mc_str = f"${c.market_cap / 1e9:.1f}B" if c.market_cap else "N/A"
        logger.info(f"  {i:2}. {c.ticker:6} {mc_str:>12}  {c.name[:40]}")
    
    return companies


def apply_schema_updates(logger):
    """Apply schema V2 updates if needed."""
    logger.info("Checking schema updates...")
    
    schema_file = Path(__file__).parent.parent / "db" / "schema_v2.sql"
    
    if schema_file.exists():
        with open(schema_file) as f:
            sql = f.read()
        
        with engine.connect() as conn:
            # Execute each statement separately
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    try:
                        conn.execute(text(statement))
                    except Exception as e:
                        # Ignore "already exists" errors
                        if "already exists" not in str(e).lower():
                            logger.warning(f"Schema update warning: {e}")
            conn.commit()
        
        logger.info("Schema updates applied")


def run_ingestion(companies: list[CompanyInfo], logger, min_year: int = 1990):
    """Run the actual ingestion."""
    
    logger.info("=" * 60)
    logger.info("STARTING DATA INGESTION")
    logger.info(f"Companies: {len(companies)}")
    logger.info(f"Min year: {min_year}")
    logger.info("=" * 60)
    
    # Initialize service
    service = EdgarIngestionService(
        user_agent="FinanceApp admin@openclaw.ai"  # Required by SEC
    )
    
    # Progress callback
    def on_progress(current, total, result):
        status_icon = "✓" if result["status"] == "ok" else "✗" if result["status"] == "error" else "○"
        logger.info(
            f"[{current:4}/{total}] {status_icon} {result['ticker']:6} | "
            f"Facts: {result.get('facts_count', 0):5} | "
            f"{result.get('error', '')[:50] if result.get('error') else ''}"
        )
    
    # Run
    start_time = time.time()
    summary = service.run_ingestion(
        companies=companies,
        min_year=min_year,
        progress_callback=on_progress,
    )
    elapsed = time.time() - start_time
    
    # Report
    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Time elapsed: {elapsed / 60:.1f} minutes")
    logger.info(f"Companies processed: {summary['processed']}")
    logger.info(f"  Succeeded: {summary['succeeded']}")
    logger.info(f"  No data: {summary['no_data']}")
    logger.info(f"  Failed: {summary['failed']}")
    logger.info(f"Total facts stored: {summary['total_facts']:,}")
    logger.info("=" * 60)
    
    # Save summary
    summary_file = Path(__file__).parent.parent / "data" / "ingestion_summary.json"
    with open(summary_file, "w") as f:
        json.dump({
            "completed_at": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "summary": {k: v for k, v in summary.items() if k != "results"},
        }, f, indent=2)
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="SEC EDGAR Data Ingestion")
    parser.add_argument("--test", action="store_true", help="Quick test with 10 companies")
    parser.add_argument("--full", action="store_true", help="Full run with all available companies")
    parser.add_argument("--limit", type=int, help="Limit number of companies")
    parser.add_argument("--min-year", type=int, default=1990, help="Earliest year to fetch")
    parser.add_argument("--use-cached", action="store_true", help="Use cached company list")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    logger = setup_logging(args.verbose)
    
    # Determine limit
    if args.test:
        limit = 10
    elif args.limit:
        limit = args.limit
    elif args.full:
        limit = None  # No limit
    else:
        limit = 100  # Default
    
    logger.info("=" * 60)
    logger.info("SEC EDGAR DATA INGESTION")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info(f"Limit: {limit or 'ALL'}")
    logger.info("=" * 60)
    
    try:
        # Apply schema updates
        apply_schema_updates(logger)
        
        # Build or load company list
        cached_file = Path(__file__).parent.parent / "data" / "company_list.json"
        
        if args.use_cached and cached_file.exists():
            logger.info(f"Loading cached company list from {cached_file}")
            companies = load_company_list(cached_file)
            if limit:
                companies = companies[:limit]
        else:
            companies = build_company_list(logger, limit)
        
        # Run ingestion
        run_ingestion(companies, logger, args.min_year)
        
    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user. Progress has been saved.")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
