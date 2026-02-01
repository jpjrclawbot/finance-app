-- Finance App Database Schema
-- PostgreSQL

-- ============================================
-- COMPANIES & TICKERS
-- ============================================

CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    cik VARCHAR(10) UNIQUE,                    -- SEC Central Index Key (padded to 10 digits)
    name VARCHAR(500) NOT NULL,
    ticker VARCHAR(20),                         -- Primary ticker (nullable for private companies)
    sic_code VARCHAR(4),                        -- Standard Industrial Classification
    state_of_incorporation VARCHAR(50),
    fiscal_year_end VARCHAR(4),                 -- e.g., "1231" for Dec 31
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_companies_ticker ON companies(ticker);
CREATE INDEX idx_companies_cik ON companies(cik);

-- Ticker history (companies change tickers, have multiple listings)
CREATE TABLE IF NOT EXISTS ticker_history (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    exchange VARCHAR(50),                       -- NYSE, NASDAQ, etc.
    start_date DATE,
    end_date DATE,                              -- NULL if current
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ticker_history_ticker ON ticker_history(ticker);
CREATE INDEX idx_ticker_history_company ON ticker_history(company_id);

-- ============================================
-- STOCK PRICES
-- ============================================

CREATE TABLE IF NOT EXISTS stock_prices (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,                -- Denormalized for fast queries
    date DATE NOT NULL,
    open DECIMAL(18, 6),
    high DECIMAL(18, 6),
    low DECIMAL(18, 6),
    close DECIMAL(18, 6),                       -- Split-adjusted close (from Yahoo)
    adj_close DECIMAL(18, 6),                   -- Split + dividend adjusted (total return)
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ticker, date)
);

CREATE INDEX idx_stock_prices_ticker_date ON stock_prices(ticker, date DESC);
CREATE INDEX idx_stock_prices_company ON stock_prices(company_id);

-- ============================================
-- CORPORATE ACTIONS
-- ============================================

CREATE TABLE IF NOT EXISTS stock_splits (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    date DATE NOT NULL,                         -- Effective date
    split_ratio DECIMAL(18, 6) NOT NULL,        -- e.g., 4.0 for 4:1 split, 0.1 for 1:10 reverse
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ticker, date)
);

CREATE INDEX idx_stock_splits_ticker ON stock_splits(ticker, date);

CREATE TABLE IF NOT EXISTS dividends (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    ex_date DATE NOT NULL,                      -- Ex-dividend date
    payment_date DATE,
    amount DECIMAL(18, 6) NOT NULL,             -- Per-share amount (split-adjusted)
    dividend_type VARCHAR(50) DEFAULT 'cash',   -- cash, stock, special
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ticker, ex_date, dividend_type)
);

CREATE INDEX idx_dividends_ticker ON dividends(ticker, ex_date);

-- ============================================
-- SHARES OUTSTANDING (for market cap)
-- ============================================

CREATE TABLE IF NOT EXISTS shares_outstanding (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    date DATE NOT NULL,                         -- Filing/report date
    shares_basic BIGINT,                        -- Basic shares outstanding
    shares_diluted BIGINT,                      -- Diluted (includes options, warrants)
    source VARCHAR(100),                        -- '10-K', '10-Q', 'yahoo', etc.
    filing_accession VARCHAR(50),               -- SEC accession number if from EDGAR
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ticker, date, source)
);

CREATE INDEX idx_shares_outstanding_ticker ON shares_outstanding(ticker, date DESC);

-- ============================================
-- SEC FILINGS
-- ============================================

CREATE TABLE IF NOT EXISTS sec_filings (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    cik VARCHAR(10) NOT NULL,
    accession_number VARCHAR(50) UNIQUE NOT NULL,
    form_type VARCHAR(20) NOT NULL,             -- 10-K, 10-Q, 8-K, etc.
    filing_date DATE NOT NULL,
    report_date DATE,                           -- Period end date
    primary_document VARCHAR(500),              -- Main document filename
    file_url VARCHAR(1000),
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sec_filings_cik ON sec_filings(cik);
CREATE INDEX idx_sec_filings_company ON sec_filings(company_id);
CREATE INDEX idx_sec_filings_form ON sec_filings(form_type, filing_date DESC);

-- ============================================
-- FINANCIAL STATEMENTS (from SEC filings)
-- ============================================

CREATE TABLE IF NOT EXISTS financial_facts (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    filing_id INTEGER REFERENCES sec_filings(id) ON DELETE CASCADE,
    cik VARCHAR(10) NOT NULL,
    taxonomy VARCHAR(50) NOT NULL,              -- us-gaap, dei, etc.
    concept VARCHAR(200) NOT NULL,              -- e.g., 'Revenues', 'NetIncomeLoss'
    value DECIMAL(24, 4),
    unit VARCHAR(50),                           -- USD, shares, pure, etc.
    period_start DATE,
    period_end DATE NOT NULL,
    fiscal_year INTEGER,
    fiscal_period VARCHAR(10),                  -- FY, Q1, Q2, Q3, Q4
    instant BOOLEAN DEFAULT FALSE,              -- Point-in-time vs period
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(cik, concept, period_end, fiscal_period)
);

CREATE INDEX idx_financial_facts_cik ON financial_facts(cik);
CREATE INDEX idx_financial_facts_concept ON financial_facts(concept);
CREATE INDEX idx_financial_facts_company ON financial_facts(company_id);

-- ============================================
-- INDEX CONSTITUENTS (S&P 500, etc.)
-- ============================================

CREATE TABLE IF NOT EXISTS indices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,         -- ^GSPC, ^DJI, ^IXIC
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO indices (symbol, name) VALUES 
    ('^GSPC', 'S&P 500'),
    ('^DJI', 'Dow Jones Industrial Average'),
    ('^IXIC', 'NASDAQ Composite')
ON CONFLICT (symbol) DO NOTHING;

CREATE TABLE IF NOT EXISTS index_constituents (
    id SERIAL PRIMARY KEY,
    index_id INTEGER REFERENCES indices(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    added_date DATE,
    removed_date DATE,                          -- NULL if still in index
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(index_id, ticker, added_date)
);

CREATE INDEX idx_index_constituents_index ON index_constituents(index_id);
CREATE INDEX idx_index_constituents_ticker ON index_constituents(ticker);

-- ============================================
-- CALCULATED METRICS (cache for performance)
-- ============================================

CREATE TABLE IF NOT EXISTS valuation_metrics (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    
    -- Price data
    price DECIMAL(18, 6),
    market_cap BIGINT,                          -- price * shares_outstanding
    
    -- Valuation ratios
    pe_ratio DECIMAL(12, 4),                    -- Price / EPS
    pe_forward DECIMAL(12, 4),                  -- Price / Forward EPS (analyst est)
    ps_ratio DECIMAL(12, 4),                    -- Price / Sales per share
    pb_ratio DECIMAL(12, 4),                    -- Price / Book value per share
    
    -- Enterprise value metrics
    enterprise_value BIGINT,                    -- market_cap + debt - cash
    ev_revenue DECIMAL(12, 4),
    ev_ebitda DECIMAL(12, 4),
    ev_ebit DECIMAL(12, 4),
    
    -- Profitability
    gross_margin DECIMAL(8, 4),
    operating_margin DECIMAL(8, 4),
    net_margin DECIMAL(8, 4),
    roe DECIMAL(8, 4),                          -- Return on equity
    roa DECIMAL(8, 4),                          -- Return on assets
    roic DECIMAL(8, 4),                         -- Return on invested capital
    
    -- Growth (YoY)
    revenue_growth DECIMAL(8, 4),
    earnings_growth DECIMAL(8, 4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ticker, date)
);

CREATE INDEX idx_valuation_metrics_ticker ON valuation_metrics(ticker, date DESC);

-- ============================================
-- DATA SYNC TRACKING
-- ============================================

CREATE TABLE IF NOT EXISTS sync_log (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,           -- 'prices', 'filings', 'sp500', etc.
    entity_id VARCHAR(100),                     -- ticker, CIK, etc.
    last_sync TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'success',       -- success, partial, failed
    records_processed INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sync_log_entity ON sync_log(entity_type, entity_id);
