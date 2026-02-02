#!/usr/bin/env python3
"""
Get top companies by market cap using a smarter approach.
Uses known indices (S&P 500, etc.) + screens for large caps.
"""

import sys
import json
import time
from pathlib import Path
from io import StringIO

# Unbuffered output
sys.stdout.reconfigure(line_buffering=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

import yfinance as yf
import pandas as pd
import requests

# Sources for large companies
SP500_WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP400_WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
NASDAQ100_WIKI = "https://en.wikipedia.org/wiki/Nasdaq-100"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"


def fetch_wiki_html(url):
    """Fetch Wikipedia HTML with proper headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text


def get_sp500_tickers():
    """Get S&P 500 tickers from Wikipedia."""
    try:
        print("  Fetching S&P 500 HTML...")
        html = fetch_wiki_html(SP500_WIKI)
        print(f"  Got {len(html)} bytes, parsing...")
        tables = pd.read_html(StringIO(html))
        df = tables[0]
        tickers = df["Symbol"].str.replace(".", "-").tolist()
        return tickers
    except Exception as e:
        print(f"Error fetching S&P 500: {e}")
        return []


def get_sp400_tickers():
    """Get S&P 400 MidCap tickers."""
    try:
        print("  Fetching S&P 400 HTML...")
        html = fetch_wiki_html(SP400_WIKI)
        print(f"  Got {len(html)} bytes, parsing...")
        tables = pd.read_html(StringIO(html))
        df = tables[0]
        col = "Ticker symbol" if "Ticker symbol" in df.columns else df.columns[1]
        tickers = df[col].str.replace(".", "-").tolist()
        return tickers
    except Exception as e:
        print(f"Error fetching S&P 400: {e}")
        return []


def get_nasdaq100_tickers():
    """Get NASDAQ 100 tickers."""
    try:
        print("  Fetching NASDAQ 100 HTML...")
        html = fetch_wiki_html(NASDAQ100_WIKI)
        print(f"  Got {len(html)} bytes, parsing...")
        tables = pd.read_html(StringIO(html))
        for table in tables:
            if "Ticker" in table.columns:
                return table["Ticker"].tolist()
            if "Symbol" in table.columns:
                return table["Symbol"].tolist()
        return []
    except Exception as e:
        print(f"Error fetching NASDAQ 100: {e}")
        return []


def get_sec_ticker_to_cik():
    """Get SEC ticker to CIK mapping."""
    headers = {
        "User-Agent": "OpenClaw Finance App contact@openclaw.io",
        "Accept": "application/json",
    }
    response = requests.get(SEC_TICKERS, headers=headers)
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


def get_market_caps_batch(tickers: list[str]) -> dict[str, float]:
    """Get market caps for a list of tickers."""
    market_caps = {}
    
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            mc = info.get("marketCap", 0)
            if mc and mc > 0:
                market_caps[ticker] = mc
        except:
            pass
        time.sleep(0.2)  # Rate limit
    
    return market_caps


def main():
    output_file = Path(__file__).parent.parent / "data" / "top_companies.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print("Collecting tickers from indices...")
    
    # Get tickers from multiple sources
    sp500 = get_sp500_tickers()
    print(f"  S&P 500: {len(sp500)} tickers")
    
    sp400 = get_sp400_tickers()
    print(f"  S&P 400: {len(sp400)} tickers")
    
    nasdaq100 = get_nasdaq100_tickers()
    print(f"  NASDAQ 100: {len(nasdaq100)} tickers")
    
    # Combine and dedupe
    all_tickers = list(set(sp500 + sp400 + nasdaq100))
    print(f"  Combined unique: {len(all_tickers)} tickers")
    
    # Get SEC CIK mapping
    print("Fetching SEC CIK mappings...")
    sec_mapping = get_sec_ticker_to_cik()
    
    # Filter to those with SEC filings
    tickers_with_cik = [t for t in all_tickers if t in sec_mapping]
    print(f"  With SEC filings: {len(tickers_with_cik)} tickers")
    
    # Get market caps
    print("Fetching market caps (this takes a few minutes)...")
    market_caps = {}
    
    batch_size = 50
    for i in range(0, len(tickers_with_cik), batch_size):
        batch = tickers_with_cik[i:i+batch_size]
        batch_caps = get_market_caps_batch(batch)
        market_caps.update(batch_caps)
        print(f"  Processed {min(i+batch_size, len(tickers_with_cik))}/{len(tickers_with_cik)}")
    
    # Build sorted list
    companies = []
    for ticker, mc in market_caps.items():
        if ticker in sec_mapping:
            companies.append({
                "ticker": ticker,
                "cik": sec_mapping[ticker]["cik"],
                "name": sec_mapping[ticker]["name"],
                "market_cap": mc,
            })
    
    # Sort by market cap
    companies.sort(key=lambda x: x["market_cap"], reverse=True)
    
    # Save
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": pd.Timestamp.now().isoformat(),
            "count": len(companies),
            "companies": companies,
        }, f, indent=2)
    
    print(f"\nSaved {len(companies)} companies to {output_file}")
    print("\nTop 10 by market cap:")
    for i, c in enumerate(companies[:10], 1):
        print(f"  {i}. {c['ticker']} - ${c['market_cap']/1e9:.1f}B - {c['name']}")


if __name__ == "__main__":
    main()
