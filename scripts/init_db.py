#!/usr/bin/env python3
"""Initialize database with schema and seed data."""

import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import engine, Base, SessionLocal
from backend.models.company import Company
from backend.models.prices import StockPrice, StockSplit, Dividend
from backend.models.indices import Index, IndexConstituent
from backend.models.filings import FinancialFact
from backend.models.metrics import ValuationMetric

# Need to import Index for query


def init_db():
    """Create all tables."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created!")


def seed_demo_data():
    """Seed database with demo data for AAPL, NVDA, TSLA, NFLX."""
    db = SessionLocal()
    
    try:
        # Check if already seeded
        existing = db.query(Company).filter(Company.ticker == "AAPL").first()
        if existing:
            print("Demo data already exists. Skipping seed.")
            return
        
        print("Seeding demo data...")
        
        # Companies
        companies = [
            Company(id=1, cik="0000320193", name="Apple Inc.", ticker="AAPL", sic_code="3571", fiscal_year_end="0930"),
            Company(id=2, cik="0001045810", name="NVIDIA Corporation", ticker="NVDA", sic_code="3674", fiscal_year_end="0131"),
            Company(id=3, cik="0001318605", name="Tesla, Inc.", ticker="TSLA", sic_code="3711", fiscal_year_end="1231"),
            Company(id=4, cik="0001065280", name="Netflix, Inc.", ticker="NFLX", sic_code="7841", fiscal_year_end="1231"),
        ]
        db.add_all(companies)
        db.flush()
        
        # S&P 500 Index - get existing or it was created by schema
        sp500 = db.query(Index).filter(Index.symbol == "^GSPC").first()
        if not sp500:
            sp500 = Index(symbol="^GSPC", name="S&P 500")
            db.add(sp500)
            db.flush()
        
        # Index Constituents
        constituents = [
            IndexConstituent(index_id=sp500.id, company_id=1, ticker="AAPL", added_date=date(1982, 11, 30)),
            IndexConstituent(index_id=sp500.id, company_id=2, ticker="NVDA", added_date=date(2001, 11, 30)),
            IndexConstituent(index_id=sp500.id, company_id=3, ticker="TSLA", added_date=date(2020, 12, 21)),
            IndexConstituent(index_id=sp500.id, company_id=4, ticker="NFLX", added_date=date(2010, 12, 20)),
        ]
        db.add_all(constituents)
        
        # Sample stock prices (last 3 weeks of Jan 2026)
        price_data = [
            # AAPL ~$246
            (1, "AAPL", "2026-01-13", 236.90, 238.80, 236.20, 238.20, 238.20, 37000000),
            (1, "AAPL", "2026-01-14", 238.30, 239.50, 237.10, 238.70, 238.70, 36000000),
            (1, "AAPL", "2026-01-15", 238.80, 240.20, 238.00, 239.50, 239.50, 38000000),
            (1, "AAPL", "2026-01-16", 239.40, 241.00, 238.60, 240.20, 240.20, 35000000),
            (1, "AAPL", "2026-01-17", 240.10, 241.80, 239.20, 240.80, 240.80, 34000000),
            (1, "AAPL", "2026-01-21", 240.60, 242.30, 239.80, 241.50, 241.50, 33000000),
            (1, "AAPL", "2026-01-22", 241.40, 243.00, 240.50, 242.20, 242.20, 36000000),
            (1, "AAPL", "2026-01-23", 242.10, 243.80, 241.30, 243.00, 243.00, 35000000),
            (1, "AAPL", "2026-01-24", 242.80, 244.20, 241.50, 242.50, 242.50, 37000000),
            (1, "AAPL", "2026-01-27", 242.40, 244.50, 241.80, 244.00, 244.00, 34000000),
            (1, "AAPL", "2026-01-28", 244.10, 245.30, 243.20, 244.80, 244.80, 32000000),
            (1, "AAPL", "2026-01-29", 244.70, 246.00, 243.80, 245.20, 245.20, 33000000),
            (1, "AAPL", "2026-01-30", 245.00, 246.50, 244.20, 245.80, 245.80, 35000000),
            (1, "AAPL", "2026-01-31", 245.60, 247.00, 244.50, 246.30, 246.30, 36000000),
            # NVDA ~$158
            (2, "NVDA", "2026-01-13", 143.80, 146.20, 143.20, 145.80, 145.80, 285000000),
            (2, "NVDA", "2026-01-14", 146.00, 147.50, 145.20, 146.80, 146.80, 275000000),
            (2, "NVDA", "2026-01-15", 147.00, 148.80, 146.50, 148.20, 148.20, 280000000),
            (2, "NVDA", "2026-01-16", 148.30, 150.00, 147.50, 149.50, 149.50, 265000000),
            (2, "NVDA", "2026-01-17", 149.60, 151.20, 148.80, 150.50, 150.50, 260000000),
            (2, "NVDA", "2026-01-21", 150.40, 152.00, 149.50, 151.20, 151.20, 255000000),
            (2, "NVDA", "2026-01-22", 151.30, 153.00, 150.50, 152.50, 152.50, 270000000),
            (2, "NVDA", "2026-01-23", 152.60, 154.20, 151.80, 153.50, 153.50, 265000000),
            (2, "NVDA", "2026-01-24", 153.40, 155.00, 152.50, 154.00, 154.00, 275000000),
            (2, "NVDA", "2026-01-27", 153.80, 155.50, 153.00, 155.00, 155.00, 260000000),
            (2, "NVDA", "2026-01-28", 155.20, 156.80, 154.50, 156.20, 156.20, 250000000),
            (2, "NVDA", "2026-01-29", 156.30, 157.50, 155.50, 156.80, 156.80, 255000000),
            (2, "NVDA", "2026-01-30", 156.50, 158.00, 155.80, 157.50, 157.50, 265000000),
            (2, "NVDA", "2026-01-31", 157.60, 159.00, 156.80, 158.20, 158.20, 270000000),
            # TSLA ~$477
            (3, "TSLA", "2026-01-13", 426.00, 432.50, 424.00, 430.80, 430.80, 85000000),
            (3, "TSLA", "2026-01-14", 431.50, 436.00, 429.50, 434.20, 434.20, 82000000),
            (3, "TSLA", "2026-01-15", 434.80, 440.00, 433.00, 438.50, 438.50, 84000000),
            (3, "TSLA", "2026-01-16", 439.00, 445.50, 437.50, 443.20, 443.20, 79000000),
            (3, "TSLA", "2026-01-17", 443.80, 448.00, 441.50, 446.50, 446.50, 77000000),
            (3, "TSLA", "2026-01-21", 446.00, 452.00, 444.00, 450.20, 450.20, 75000000),
            (3, "TSLA", "2026-01-22", 450.80, 456.50, 448.50, 454.00, 454.00, 80000000),
            (3, "TSLA", "2026-01-23", 454.50, 460.00, 452.00, 457.80, 457.80, 78000000),
            (3, "TSLA", "2026-01-24", 458.00, 462.50, 455.00, 459.50, 459.50, 82000000),
            (3, "TSLA", "2026-01-27", 459.00, 465.00, 457.50, 463.20, 463.20, 76000000),
            (3, "TSLA", "2026-01-28", 463.80, 468.50, 462.00, 466.80, 466.80, 73000000),
            (3, "TSLA", "2026-01-29", 467.00, 472.00, 465.00, 469.50, 469.50, 75000000),
            (3, "TSLA", "2026-01-30", 469.00, 475.00, 467.50, 473.20, 473.20, 78000000),
            (3, "TSLA", "2026-01-31", 473.50, 478.50, 471.00, 476.80, 476.80, 80000000),
            # NFLX ~$1045
            (4, "NFLX", "2026-01-13", 957.50, 968.00, 955.00, 965.20, 965.20, 3900000),
            (4, "NFLX", "2026-01-14", 966.00, 975.00, 963.50, 972.50, 972.50, 3800000),
            (4, "NFLX", "2026-01-15", 973.00, 982.50, 970.00, 980.20, 980.20, 3950000),
            (4, "NFLX", "2026-01-16", 980.80, 990.00, 978.00, 987.50, 987.50, 3700000),
            (4, "NFLX", "2026-01-17", 988.00, 996.50, 985.00, 993.80, 993.80, 3600000),
            (4, "NFLX", "2026-01-21", 994.00, 1002.00, 990.50, 999.50, 999.50, 3550000),
            (4, "NFLX", "2026-01-22", 1000.00, 1010.00, 997.00, 1006.80, 1006.80, 3750000),
            (4, "NFLX", "2026-01-23", 1007.50, 1015.50, 1004.00, 1012.20, 1012.20, 3650000),
            (4, "NFLX", "2026-01-24", 1012.00, 1020.00, 1008.50, 1016.50, 1016.50, 3800000),
            (4, "NFLX", "2026-01-27", 1016.00, 1025.00, 1013.00, 1022.80, 1022.80, 3600000),
            (4, "NFLX", "2026-01-28", 1023.50, 1032.00, 1020.50, 1028.50, 1028.50, 3450000),
            (4, "NFLX", "2026-01-29", 1028.00, 1036.50, 1025.00, 1033.20, 1033.20, 3500000),
            (4, "NFLX", "2026-01-30", 1033.00, 1042.00, 1030.00, 1038.80, 1038.80, 3650000),
            (4, "NFLX", "2026-01-31", 1039.00, 1048.00, 1036.00, 1045.50, 1045.50, 3700000),
        ]
        
        for p in price_data:
            db.add(StockPrice(
                company_id=p[0],
                ticker=p[1],
                date=date.fromisoformat(p[2]),
                open=Decimal(str(p[3])),
                high=Decimal(str(p[4])),
                low=Decimal(str(p[5])),
                close=Decimal(str(p[6])),
                adj_close=Decimal(str(p[7])),
                volume=p[8],
            ))
        
        # Financial facts for time series calculations
        # Apple: ~$390B revenue TTM, ~$100B net income TTM, 15.2B shares
        financial_data = [
            # (company_id, cik, concept, value, unit, period_end, fiscal_year, fiscal_period)
            # AAPL
            (1, "0000320193", "Revenues", 95000000000, "USD", "2025-09-30", 2025, "Q4"),
            (1, "0000320193", "Revenues", 85000000000, "USD", "2025-06-30", 2025, "Q3"),
            (1, "0000320193", "Revenues", 90000000000, "USD", "2025-03-31", 2025, "Q2"),
            (1, "0000320193", "Revenues", 120000000000, "USD", "2024-12-31", 2025, "Q1"),
            (1, "0000320193", "NetIncomeLoss", 25000000000, "USD", "2025-09-30", 2025, "Q4"),
            (1, "0000320193", "NetIncomeLoss", 22000000000, "USD", "2025-06-30", 2025, "Q3"),
            (1, "0000320193", "NetIncomeLoss", 24000000000, "USD", "2025-03-31", 2025, "Q2"),
            (1, "0000320193", "NetIncomeLoss", 33000000000, "USD", "2024-12-31", 2025, "Q1"),
            (1, "0000320193", "CommonStockSharesOutstanding", 15200000000, "shares", "2025-09-30", 2025, "Q4"),
            (1, "0000320193", "LongTermDebt", 98000000000, "USD", "2025-09-30", 2025, "Q4"),
            (1, "0000320193", "CashAndCashEquivalentsAtCarryingValue", 30000000000, "USD", "2025-09-30", 2025, "Q4"),
            (1, "0000320193", "OperatingIncomeLoss", 30000000000, "USD", "2025-09-30", 2025, "Q4"),
            (1, "0000320193", "OperatingIncomeLoss", 26000000000, "USD", "2025-06-30", 2025, "Q3"),
            (1, "0000320193", "OperatingIncomeLoss", 28000000000, "USD", "2025-03-31", 2025, "Q2"),
            (1, "0000320193", "OperatingIncomeLoss", 38000000000, "USD", "2024-12-31", 2025, "Q1"),
            # NVDA
            (2, "0001045810", "Revenues", 35000000000, "USD", "2025-10-31", 2026, "Q3"),
            (2, "0001045810", "Revenues", 30000000000, "USD", "2025-07-31", 2026, "Q2"),
            (2, "0001045810", "Revenues", 26000000000, "USD", "2025-04-30", 2026, "Q1"),
            (2, "0001045810", "Revenues", 22000000000, "USD", "2025-01-31", 2025, "Q4"),
            (2, "0001045810", "NetIncomeLoss", 19500000000, "USD", "2025-10-31", 2026, "Q3"),
            (2, "0001045810", "NetIncomeLoss", 17000000000, "USD", "2025-07-31", 2026, "Q2"),
            (2, "0001045810", "NetIncomeLoss", 15000000000, "USD", "2025-04-30", 2026, "Q1"),
            (2, "0001045810", "NetIncomeLoss", 12500000000, "USD", "2024-01-31", 2025, "Q4"),
            (2, "0001045810", "CommonStockSharesOutstanding", 24500000000, "shares", "2025-10-31", 2026, "Q3"),
            (2, "0001045810", "LongTermDebt", 9000000000, "USD", "2025-10-31", 2026, "Q3"),
            (2, "0001045810", "CashAndCashEquivalentsAtCarryingValue", 8500000000, "USD", "2025-10-31", 2026, "Q3"),
            (2, "0001045810", "OperatingIncomeLoss", 22000000000, "USD", "2025-10-31", 2026, "Q3"),
            (2, "0001045810", "OperatingIncomeLoss", 19000000000, "USD", "2025-07-31", 2026, "Q2"),
            (2, "0001045810", "OperatingIncomeLoss", 17000000000, "USD", "2025-04-30", 2026, "Q1"),
            (2, "0001045810", "OperatingIncomeLoss", 14000000000, "USD", "2025-01-31", 2025, "Q4"),
            # TSLA
            (3, "0001318605", "Revenues", 25000000000, "USD", "2025-09-30", 2025, "Q3"),
            (3, "0001318605", "Revenues", 26000000000, "USD", "2025-06-30", 2025, "Q2"),
            (3, "0001318605", "Revenues", 21000000000, "USD", "2025-03-31", 2025, "Q1"),
            (3, "0001318605", "Revenues", 25000000000, "USD", "2024-12-31", 2024, "Q4"),
            (3, "0001318605", "NetIncomeLoss", 2200000000, "USD", "2025-09-30", 2025, "Q3"),
            (3, "0001318605", "NetIncomeLoss", 1800000000, "USD", "2025-06-30", 2025, "Q2"),
            (3, "0001318605", "NetIncomeLoss", 1100000000, "USD", "2025-03-31", 2025, "Q1"),
            (3, "0001318605", "NetIncomeLoss", 2500000000, "USD", "2024-12-31", 2024, "Q4"),
            (3, "0001318605", "CommonStockSharesOutstanding", 3200000000, "shares", "2025-09-30", 2025, "Q3"),
            (3, "0001318605", "LongTermDebt", 5000000000, "USD", "2025-09-30", 2025, "Q3"),
            (3, "0001318605", "CashAndCashEquivalentsAtCarryingValue", 18000000000, "USD", "2025-09-30", 2025, "Q3"),
            (3, "0001318605", "OperatingIncomeLoss", 2600000000, "USD", "2025-09-30", 2025, "Q3"),
            (3, "0001318605", "OperatingIncomeLoss", 2200000000, "USD", "2025-06-30", 2025, "Q2"),
            (3, "0001318605", "OperatingIncomeLoss", 1400000000, "USD", "2025-03-31", 2025, "Q1"),
            (3, "0001318605", "OperatingIncomeLoss", 2800000000, "USD", "2024-12-31", 2024, "Q4"),
            # NFLX
            (4, "0001065280", "Revenues", 10500000000, "USD", "2025-09-30", 2025, "Q3"),
            (4, "0001065280", "Revenues", 9800000000, "USD", "2025-06-30", 2025, "Q2"),
            (4, "0001065280", "Revenues", 9500000000, "USD", "2025-03-31", 2025, "Q1"),
            (4, "0001065280", "Revenues", 10200000000, "USD", "2024-12-31", 2024, "Q4"),
            (4, "0001065280", "NetIncomeLoss", 2100000000, "USD", "2025-09-30", 2025, "Q3"),
            (4, "0001065280", "NetIncomeLoss", 1900000000, "USD", "2025-06-30", 2025, "Q2"),
            (4, "0001065280", "NetIncomeLoss", 1800000000, "USD", "2025-03-31", 2025, "Q1"),
            (4, "0001065280", "NetIncomeLoss", 2000000000, "USD", "2024-12-31", 2024, "Q4"),
            (4, "0001065280", "CommonStockSharesOutstanding", 430000000, "shares", "2025-09-30", 2025, "Q3"),
            (4, "0001065280", "LongTermDebt", 14000000000, "USD", "2025-09-30", 2025, "Q3"),
            (4, "0001065280", "CashAndCashEquivalentsAtCarryingValue", 7500000000, "USD", "2025-09-30", 2025, "Q3"),
            (4, "0001065280", "OperatingIncomeLoss", 2800000000, "USD", "2025-09-30", 2025, "Q3"),
            (4, "0001065280", "OperatingIncomeLoss", 2500000000, "USD", "2025-06-30", 2025, "Q2"),
            (4, "0001065280", "OperatingIncomeLoss", 2400000000, "USD", "2025-03-31", 2025, "Q1"),
            (4, "0001065280", "OperatingIncomeLoss", 2600000000, "USD", "2024-12-31", 2024, "Q4"),
        ]
        
        for f in financial_data:
            db.add(FinancialFact(
                company_id=f[0],
                cik=f[1],
                taxonomy="us-gaap",
                concept=f[2],
                value=Decimal(str(f[3])),
                unit=f[4],
                period_end=date.fromisoformat(f[5]),
                fiscal_year=f[6],
                fiscal_period=f[7],
            ))
        
        # Valuation metrics
        metrics = [
            # (company_id, ticker, date, price, market_cap, pe, ps, pb, ev, ev_rev, ev_ebitda, gm, om, nm, roe, roa)
            (1, "AAPL", "2026-01-31", 246.30, 3743760000000, 35.96, 9.60, 60.38, 3811760000000, 9.77, 28.5, 0.44, 0.32, 0.27, 1.68, 0.30),
            (2, "NVDA", "2026-01-31", 158.20, 3875900000000, 60.55, 34.30, 59.63, 3876400000000, 34.30, 42.0, 0.74, 0.63, 0.56, 0.98, 0.67),
            (3, "TSLA", "2026-01-31", 476.80, 1525760000000, 200.76, 15.73, 21.19, 1512760000000, 15.60, 85.0, 0.18, 0.10, 0.08, 0.11, 0.07),
            (4, "NFLX", "2026-01-31", 1045.50, 449565000000, 57.60, 11.24, 18.73, 456065000000, 11.40, 52.0, 0.40, 0.27, 0.20, 0.33, 0.15),
        ]
        
        for m in metrics:
            db.add(ValuationMetric(
                company_id=m[0],
                ticker=m[1],
                date=date.fromisoformat(m[2]),
                price=Decimal(str(m[3])),
                market_cap=m[4],
                pe_ratio=Decimal(str(m[5])),
                ps_ratio=Decimal(str(m[6])),
                pb_ratio=Decimal(str(m[7])),
                enterprise_value=m[8],
                ev_revenue=Decimal(str(m[9])),
                ev_ebitda=Decimal(str(m[10])),
                gross_margin=Decimal(str(m[11])),
                operating_margin=Decimal(str(m[12])),
                net_margin=Decimal(str(m[13])),
                roe=Decimal(str(m[14])),
                roa=Decimal(str(m[15])),
            ))
        
        db.commit()
        print("Demo data seeded successfully!")
        print("Companies: AAPL, NVDA, TSLA, NFLX")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    seed_demo_data()
    print("\nDatabase ready! Run the dashboard with:")
    print("  cd projects/finance-app && streamlit run frontend/app.py")
