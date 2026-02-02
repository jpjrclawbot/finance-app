#!/usr/bin/env python3
"""
Run bulk SEC EDGAR data ingestion.

This script fetches quarterly financials for the largest US public companies
from SEC EDGAR, going back to 1990.

Usage:
    python scripts/run_bulk_ingestion.py [--limit N] [--min-year YEAR] [--resume]

Example:
    # Ingest top 100 companies (quick test)
    python scripts/run_bulk_ingestion.py --limit 100
    
    # Full run: 2500 companies back to 1990
    python scripts/run_bulk_ingestion.py --limit 2500 --min-year 1990
    
    # Resume interrupted run
    python scripts/run_bulk_ingestion.py --resume

Progress is saved to data/ingestion_progress.json and can be resumed.
"""

import sys
import argparse
import logging
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.edgar_bulk import EdgarBulkService


def main():
    parser = argparse.ArgumentParser(description="Bulk SEC EDGAR data ingestion")
    parser.add_argument("--limit", type=int, default=2500, help="Number of companies to process")
    parser.add_argument("--min-year", type=int, default=1990, help="Earliest year to fetch")
    parser.add_argument("--resume", action="store_true", help="Resume from previous progress")
    parser.add_argument("--user-agent", type=str, default="FinanceApp jp@example.com",
                        help="User agent for SEC API (include your email)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("data/ingestion.log"),
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("SEC EDGAR Bulk Ingestion")
    logger.info("=" * 60)
    logger.info(f"Target companies: {args.limit}")
    logger.info(f"Min year: {args.min_year}")
    logger.info(f"Resume: {args.resume}")
    logger.info("=" * 60)
    
    # Run ingestion
    service = EdgarBulkService(user_agent=args.user_agent)
    
    try:
        result = service.run_bulk_ingestion(
            limit=args.limit,
            min_year=args.min_year,
            resume=args.resume,
        )
        
        logger.info("=" * 60)
        logger.info("INGESTION COMPLETE")
        logger.info(f"Completed: {len(result.get('completed', []))}")
        logger.info(f"Failed: {len(result.get('failed', []))}")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\nInterrupted! Progress has been saved. Run with --resume to continue.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
