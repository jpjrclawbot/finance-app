# Finance App

A financial data platform for tracking stock prices, SEC filings, and calculating valuation metrics.

## Features

- **Stock Price Data**: Historical OHLCV data with split/dividend adjustments (via Yahoo Finance)
- **SEC EDGAR Integration**: 10-K/10-Q filings, shares outstanding, financial statements
- **Valuation Metrics**: P/E, EV/Revenue, EV/EBITDA, and more
- **S&P 500 Tracking**: Full index constituent tracking

## Tech Stack

- **Backend**: Python 3.11+ with FastAPI
- **Database**: PostgreSQL with SQLAlchemy
- **Data Sources**: Yahoo Finance, SEC EDGAR
- **Frontend**: TBD (React or simple Jinja templates)

## Project Structure

```
finance-app/
├── backend/
│   ├── api/          # FastAPI routes
│   ├── models/       # SQLAlchemy models
│   └── services/     # Business logic (prices, edgar, metrics)
├── db/
│   └── schema.sql    # Database schema
├── scripts/          # Data ingestion scripts
├── tests/            # Test suite
└── frontend/         # Web UI (TBD)
```

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up database
psql -U postgres -c "CREATE DATABASE finance_app;"
psql -U postgres -d finance_app -f db/schema.sql

# Run the API
uvicorn backend.api.main:app --reload
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```
DATABASE_URL=postgresql://user:pass@localhost/finance_app
SEC_USER_AGENT=FinanceApp yourname@email.com  # Required by SEC
```

## API Endpoints

### Stocks
- `GET /api/stocks/{ticker}/prices` - Get historical prices
- `POST /api/stocks/{ticker}/fetch` - Fetch prices from Yahoo Finance
- `GET /api/stocks/{ticker}/returns` - Calculate price/total returns
- `POST /api/stocks/batch/fetch` - Fetch multiple tickers

### SEC Filings
- `GET /api/filings/{ticker}/company` - Get company info (name, CIK)
- `POST /api/filings/{ticker}/sync` - Sync company info from SEC
- `GET /api/filings/{ticker}/filings` - Get SEC filings list
- `POST /api/filings/{ticker}/filings/fetch` - Fetch filings from EDGAR
- `POST /api/filings/{ticker}/facts/fetch` - Fetch XBRL financial facts
- `GET /api/filings/{ticker}/shares` - Get shares outstanding

### Indices
- `GET /api/indices/sp500/constituents` - Get S&P 500 members
- `POST /api/indices/sp500/sync` - Sync S&P 500 from Wikipedia
- `POST /api/indices/sp500/prices/fetch` - Fetch prices for all S&P 500

### Metrics
- `GET /api/metrics/{ticker}` - Calculate valuation metrics (P/E, EV/Revenue, etc.)
- `POST /api/metrics/{ticker}/store` - Calculate and store metrics
- `POST /api/metrics/batch/calculate` - Calculate for multiple tickers

## Quick Start

```bash
# 1. Set up database
createdb finance_app
psql -d finance_app -f db/schema.sql

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your settings

# 4. Run the API
uvicorn backend.api.main:app --reload

# 5. Ingest sample data (optional)
python scripts/ingest_sample.py
```

## Usage Example

```bash
# Fetch price data for Apple
curl -X POST http://localhost:8000/api/stocks/AAPL/fetch

# Get price history
curl http://localhost:8000/api/stocks/AAPL/prices

# Fetch SEC data
curl -X POST http://localhost:8000/api/filings/AAPL/sync
curl -X POST http://localhost:8000/api/filings/AAPL/facts/fetch

# Calculate valuation metrics
curl http://localhost:8000/api/metrics/AAPL
```
