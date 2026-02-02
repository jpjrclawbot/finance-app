#!/usr/bin/env python3
"""
Bulk historical stock price ingestion from Yahoo Finance.
Fetches daily prices, splits, and dividends back to 1990.
"""

import argparse
import logging
import time
from datetime import date, datetime
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf
import pandas as pd

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Database connection
SUPABASE_URL = "postgresql://postgres:KOmnKE7zxDOg32VB@db.rgtaqngfeylwwybofvfm.supabase.co:5432/postgres"

# Rate limiting - Yahoo Finance tolerates ~2000 requests/hour
# Be conservative: 1 request every 2 seconds = 1800/hour
RATE_LIMIT_SECONDS = 2.0

# Start date for historical data
START_DATE = date(1990, 1, 1)


def get_companies(conn, limit: Optional[int] = None) -> list[dict]:
    """Get list of companies to process, sorted by market cap (largest first)."""
    cur = conn.cursor()
    
    # Get companies with their latest market cap from financial facts
    query = """
        WITH latest_market_caps AS (
            SELECT DISTINCT ON (cik) 
                cik,
                value as market_cap,
                period_end
            FROM financial_facts
            WHERE concept = 'MarketCapitalization'
            ORDER BY cik, period_end DESC
        )
        SELECT c.id, c.ticker, c.name, c.cik, COALESCE(m.market_cap, 0) as market_cap
        FROM companies c
        LEFT JOIN latest_market_caps m ON c.cik = m.cik
        ORDER BY market_cap DESC NULLS LAST
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    cur.execute(query)
    companies = []
    for row in cur.fetchall():
        companies.append({
            'id': row[0],
            'ticker': row[1],
            'name': row[2],
            'cik': row[3],
            'market_cap': row[4]
        })
    
    return companies


def get_existing_price_range(conn, ticker: str) -> tuple[Optional[date], Optional[date]]:
    """Get the date range of existing prices for a ticker."""
    cur = conn.cursor()
    cur.execute("""
        SELECT MIN(date), MAX(date) 
        FROM stock_prices 
        WHERE ticker = %s
    """, (ticker,))
    row = cur.fetchone()
    return row[0], row[1]


def fetch_and_store_prices(conn, company: dict, start_date: date, end_date: date) -> dict:
    """Fetch prices from Yahoo Finance and store in database."""
    ticker = company['ticker']
    company_id = company['id']
    
    results = {'prices': 0, 'splits': 0, 'dividends': 0, 'error': None}
    
    try:
        # Fetch from Yahoo Finance
        yf_ticker = yf.Ticker(ticker)
        
        # Get price history
        hist = yf_ticker.history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=False,
        )
        
        if hist.empty:
            logger.warning(f"  No price data for {ticker}")
            return results
        
        # Store prices
        cur = conn.cursor()
        
        price_records = []
        for idx, row in hist.iterrows():
            price_date = idx.date() if hasattr(idx, 'date') else idx
            price_records.append((
                company_id,
                ticker,
                price_date,
                float(row["Open"]) if pd.notna(row["Open"]) else None,
                float(row["High"]) if pd.notna(row["High"]) else None,
                float(row["Low"]) if pd.notna(row["Low"]) else None,
                float(row["Close"]) if pd.notna(row["Close"]) else None,
                float(row.get("Adj Close", row["Close"])) if pd.notna(row.get("Adj Close", row["Close"])) else None,
                int(row["Volume"]) if pd.notna(row["Volume"]) else None,
            ))
        
        if price_records:
            execute_values(cur, """
                INSERT INTO stock_prices (company_id, ticker, date, open, high, low, close, adj_close, volume)
                VALUES %s
                ON CONFLICT (ticker, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    adj_close = EXCLUDED.adj_close,
                    volume = EXCLUDED.volume
            """, price_records)
            results['prices'] = len(price_records)
        
        # Store splits
        try:
            splits = yf_ticker.splits
            if not splits.empty:
                splits = splits[(splits.index >= pd.Timestamp(start_date)) & 
                               (splits.index <= pd.Timestamp(end_date))]
                
                split_records = []
                for idx, ratio in splits.items():
                    split_date = idx.date() if hasattr(idx, 'date') else idx
                    split_records.append((company_id, ticker, split_date, float(ratio)))
                
                if split_records:
                    execute_values(cur, """
                        INSERT INTO stock_splits (company_id, ticker, date, split_ratio)
                        VALUES %s
                        ON CONFLICT (ticker, date) DO NOTHING
                    """, split_records)
                    results['splits'] = len(split_records)
        except Exception as e:
            logger.debug(f"  Could not fetch splits for {ticker}: {e}")
        
        # Store dividends
        try:
            dividends = yf_ticker.dividends
            if not dividends.empty:
                dividends = dividends[(dividends.index >= pd.Timestamp(start_date)) & 
                                     (dividends.index <= pd.Timestamp(end_date))]
                
                div_records = []
                for idx, amount in dividends.items():
                    ex_date = idx.date() if hasattr(idx, 'date') else idx
                    div_records.append((company_id, ticker, ex_date, float(amount), 'cash'))
                
                if div_records:
                    execute_values(cur, """
                        INSERT INTO dividends (company_id, ticker, ex_date, amount, dividend_type)
                        VALUES %s
                        ON CONFLICT (ticker, ex_date, dividend_type) DO NOTHING
                    """, div_records)
                    results['dividends'] = len(div_records)
        except Exception as e:
            logger.debug(f"  Could not fetch dividends for {ticker}: {e}")
        
        conn.commit()
        
    except Exception as e:
        results['error'] = str(e)
        logger.error(f"  Error fetching {ticker}: {e}")
        conn.rollback()
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Bulk ingest stock prices from Yahoo Finance')
    parser.add_argument('--limit', type=int, help='Limit number of companies to process')
    parser.add_argument('--start-from', type=str, help='Start from this ticker (skip earlier ones)')
    parser.add_argument('--ticker', type=str, help='Process only this ticker')
    parser.add_argument('--start-date', type=str, default='1990-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')
    args = parser.parse_args()
    
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
    end_date = date.today()
    
    logger.info("=" * 60)
    logger.info("Stock Price Bulk Ingestion")
    logger.info("=" * 60)
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Rate limit: {RATE_LIMIT_SECONDS}s between requests")
    
    # Connect to database
    conn = psycopg2.connect(SUPABASE_URL)
    
    # Get companies
    companies = get_companies(conn, args.limit)
    logger.info(f"Companies to process: {len(companies)}")
    
    # Filter to single ticker if specified
    if args.ticker:
        companies = [c for c in companies if c['ticker'] == args.ticker]
        if not companies:
            logger.error(f"Ticker {args.ticker} not found")
            return
    
    # Skip to start-from ticker if specified
    if args.start_from:
        skip_until = True
        filtered = []
        for c in companies:
            if c['ticker'] == args.start_from:
                skip_until = False
            if not skip_until:
                filtered.append(c)
        companies = filtered
        logger.info(f"Starting from {args.start_from}, {len(companies)} companies remaining")
    
    if args.dry_run:
        logger.info("DRY RUN - showing first 10 companies:")
        for c in companies[:10]:
            logger.info(f"  {c['ticker']}: {c['name']} (market cap: ${c['market_cap']:,.0f})")
        return
    
    # Process companies
    total_prices = 0
    total_splits = 0
    total_dividends = 0
    succeeded = 0
    failed = 0
    
    start_time = time.time()
    
    for i, company in enumerate(companies, 1):
        ticker = company['ticker']
        
        # Check existing data
        existing_min, existing_max = get_existing_price_range(conn, ticker)
        
        if existing_min and existing_min <= start_date:
            logger.info(f"[{i}/{len(companies)}] {ticker}: Already has data from {existing_min}, skipping")
            succeeded += 1
            continue
        
        logger.info(f"[{i}/{len(companies)}] {ticker}: Fetching prices...")
        
        # Rate limiting
        time.sleep(RATE_LIMIT_SECONDS)
        
        results = fetch_and_store_prices(conn, company, start_date, end_date)
        
        if results['error']:
            failed += 1
            logger.error(f"  FAILED: {results['error']}")
        else:
            succeeded += 1
            total_prices += results['prices']
            total_splits += results['splits']
            total_dividends += results['dividends']
            logger.info(f"  Stored: {results['prices']} prices, {results['splits']} splits, {results['dividends']} dividends")
        
        # Progress update every 50 companies
        if i % 50 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed * 60  # companies per minute
            remaining = (len(companies) - i) / rate if rate > 0 else 0
            logger.info(f"Progress: {i}/{len(companies)} ({i/len(companies)*100:.1f}%) - {rate:.1f} companies/min - ETA: {remaining:.0f} min")
    
    # Final summary
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Time elapsed: {elapsed/60:.1f} minutes")
    logger.info(f"Companies processed: {len(companies)}")
    logger.info(f"Succeeded: {succeeded}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total prices stored: {total_prices:,}")
    logger.info(f"Total splits stored: {total_splits:,}")
    logger.info(f"Total dividends stored: {total_dividends:,}")
    
    conn.close()


if __name__ == '__main__':
    main()
