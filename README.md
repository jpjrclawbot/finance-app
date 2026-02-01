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

```
DATABASE_URL=postgresql://user:pass@localhost/finance_app
```
