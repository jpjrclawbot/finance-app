# Valuation Methodology

## The Split Problem

Stock splits cause data inconsistency between price data and SEC filings:

1. **Yahoo Finance prices**: Already split-adjusted. A 10:1 split means ALL historical prices 
   are divided by 10 retroactively.

2. **SEC filings**: NOT automatically adjusted. A company's Q1 2024 filing showing 400M shares 
   stays at 400M even after a 10:1 split. Only NEW filings (annual reports) restate historical 
   data.

3. **Per-share metrics (EPS)**: SEC-reported EPS from old filings is NOT adjusted. If a company 
   reported $10 EPS pre-split, that filing still shows $10 even though post-split it should be $1.

## Our Solution

### Rule 1: Never use SEC per-share metrics for calculations

❌ Don't calculate P/E as: `Price / SEC_EPS`
✅ Do calculate P/E as: `Market Cap / Net Income`

The `Market Cap / Net Income` formula is mathematically equivalent but avoids per-share math.

### Rule 2: Always use adj_close for prices

Yahoo's `adj_close` is adjusted for splits (and dividends). Using raw `close` would give 
incorrect market caps for historical analysis.

### Rule 3: Use latest shares outstanding with adj_close

Since adj_close divides historical prices by the split factor, and current shares multiplies 
by the split factor, the math cancels out:

```
Pre-split reality:  $1000 × 400M shares = $400B market cap
Post-split:         $100 × 4B shares = $400B market cap
Our calculation:    adj_close($100) × latest_shares(4B) = $400B ✓
```

### Rule 4: Don't store calculated per-share values

Store absolute values (Net Income, Total Revenue, Total Equity) instead of per-share values.
Calculate per-share metrics on-demand if needed, using the current share count.

## Implementation Checklist

- [x] `backend/services/metrics.py`: P/E = market_cap / net_income (not price / eps)
- [x] `backend/services/metrics.py`: P/B = market_cap / book_value (not price / book_per_share)
- [x] `backend/services/metrics.py`: Uses adj_close for price
- [x] `backend/services/timeseries.py`: Uses adj_close for price
- [x] `backend/services/timeseries.py`: P/E = market_cap / net_income
- [x] SEC EPS data is ingested but NOT used for ratio calculations

## Known Limitations

1. **Buybacks/Issuance**: Our approach assumes share count changes are primarily from splits.
   Major buybacks or issuances between historical dates and today could cause small inaccuracies 
   in historical market cap calculations.

2. **Dividend adjustments**: adj_close also adjusts for dividends, which slightly affects 
   historical price comparisons. For valuation metrics, this is usually negligible.

3. **Quarterly SEC data timing**: TTM values use the last 4 quarterly filings, which may not 
   perfectly align with the price date. This is standard practice in financial analysis.
