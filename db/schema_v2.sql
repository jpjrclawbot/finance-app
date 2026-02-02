-- Finance App Schema V2 - Enhanced for audit trail
-- Run this to add new columns/tables to existing schema

-- Add source tracking columns to financial_facts if not exists
ALTER TABLE financial_facts 
ADD COLUMN IF NOT EXISTS accession_number VARCHAR(50),
ADD COLUMN IF NOT EXISTS filing_url VARCHAR(1000),
ADD COLUMN IF NOT EXISTS fact_id VARCHAR(200),
ADD COLUMN IF NOT EXISTS frame VARCHAR(20);

-- Create index on accession_number for joining
CREATE INDEX IF NOT EXISTS idx_financial_facts_accession ON financial_facts(accession_number);

-- Ingestion tracking table
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',
    target_companies INTEGER,
    companies_processed INTEGER DEFAULT 0,
    companies_succeeded INTEGER DEFAULT 0,
    companies_failed INTEGER DEFAULT 0,
    facts_added INTEGER DEFAULT 0,
    error_log TEXT
);

-- Per-company ingestion status
CREATE TABLE IF NOT EXISTS company_ingestion_status (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    ticker VARCHAR(20),
    cik VARCHAR(10),
    status VARCHAR(20) DEFAULT 'pending',
    filings_found INTEGER,
    facts_extracted INTEGER,
    earliest_filing_date DATE,
    latest_filing_date DATE,
    last_processed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(cik)
);

CREATE INDEX IF NOT EXISTS idx_company_ingestion_status ON company_ingestion_status(status);

-- Update companies table with more metadata
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS exchange VARCHAR(20),
ADD COLUMN IF NOT EXISTS sector VARCHAR(100),
ADD COLUMN IF NOT EXISTS industry VARCHAR(200),
ADD COLUMN IF NOT EXISTS market_cap BIGINT,
ADD COLUMN IF NOT EXISTS last_market_cap_update TIMESTAMP;
