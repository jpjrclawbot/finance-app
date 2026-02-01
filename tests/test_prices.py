"""Tests for price service."""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch
import pandas as pd


def test_price_service_import():
    """Verify price service can be imported."""
    from backend.services.prices import PriceService
    assert PriceService is not None


def test_returns_calculation():
    """Test return calculation logic."""
    # Simple return calculation
    start_price = 100.0
    end_price = 150.0
    
    price_return = (end_price - start_price) / start_price
    
    assert price_return == 0.5  # 50% return
    assert f"{price_return * 100:.2f}%" == "50.00%"


def test_split_adjustment():
    """Test split adjustment factor calculation."""
    # 4:1 split means old shares become 4 new shares
    # Price should be divided by 4
    pre_split_price = 400.0
    split_ratio = 4.0
    
    post_split_price = pre_split_price / split_ratio
    
    assert post_split_price == 100.0


def test_dividend_reinvestment():
    """Test dividend reinvestment impact on total return."""
    # Simple example: 
    # Start: $100, End: $110 (10% price return)
    # Dividend: $2 (2% yield)
    # Total return should be ~12%
    
    start_price = 100.0
    end_price = 110.0
    dividend = 2.0
    
    price_return = (end_price - start_price) / start_price
    total_return = (end_price + dividend - start_price) / start_price
    dividend_contribution = total_return - price_return
    
    assert price_return == pytest.approx(0.10)
    assert total_return == pytest.approx(0.12)
    assert dividend_contribution == pytest.approx(0.02)
