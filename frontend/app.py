"""
Finance App Dashboard - Streamlit Frontend
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import SessionLocal
from backend.models import Company, StockPrice, ValuationMetric, FinancialFact

# Page config
st.set_page_config(
    page_title="Finance Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #666;
    }
    .positive { color: #00c853; }
    .negative { color: #ff1744; }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
</style>
""", unsafe_allow_html=True)


def get_db():
    """Get database session."""
    return SessionLocal()


def format_large_number(num):
    """Format large numbers with B/M/K suffixes."""
    if num is None:
        return "N/A"
    if abs(num) >= 1e12:
        return f"${num/1e12:.2f}T"
    if abs(num) >= 1e9:
        return f"${num/1e9:.2f}B"
    if abs(num) >= 1e6:
        return f"${num/1e6:.2f}M"
    if abs(num) >= 1e3:
        return f"${num/1e3:.1f}K"
    return f"${num:.2f}"


def format_ratio(num, suffix="x"):
    """Format ratio with suffix."""
    if num is None:
        return "N/A"
    return f"{num:.2f}{suffix}"


def format_percent(num):
    """Format as percentage."""
    if num is None:
        return "N/A"
    return f"{num*100:.1f}%"


@st.cache_data(ttl=300)
def load_companies():
    """Load all companies."""
    db = get_db()
    try:
        companies = db.query(Company).all()
        return [(c.ticker, c.name) for c in companies if c.ticker]
    finally:
        db.close()


@st.cache_data(ttl=60)
def load_stock_prices(ticker: str):
    """Load stock prices for a ticker."""
    db = get_db()
    try:
        prices = (
            db.query(StockPrice)
            .filter(StockPrice.ticker == ticker)
            .order_by(StockPrice.date)
            .all()
        )
        if not prices:
            return pd.DataFrame()
        
        data = [{
            "date": p.date,
            "open": float(p.open) if p.open else None,
            "high": float(p.high) if p.high else None,
            "low": float(p.low) if p.low else None,
            "close": float(p.close) if p.close else None,
            "volume": p.volume,
        } for p in prices]
        
        return pd.DataFrame(data)
    finally:
        db.close()


@st.cache_data(ttl=60)
def load_metrics(ticker: str):
    """Load latest valuation metrics."""
    db = get_db()
    try:
        metric = (
            db.query(ValuationMetric)
            .filter(ValuationMetric.ticker == ticker)
            .order_by(ValuationMetric.date.desc())
            .first()
        )
        return metric
    finally:
        db.close()


@st.cache_data(ttl=60)
def load_all_metrics():
    """Load metrics for all companies."""
    db = get_db()
    try:
        # Get latest metric for each ticker
        from sqlalchemy import func
        
        subq = (
            db.query(
                ValuationMetric.ticker,
                func.max(ValuationMetric.date).label("max_date")
            )
            .group_by(ValuationMetric.ticker)
            .subquery()
        )
        
        metrics = (
            db.query(ValuationMetric)
            .join(
                subq,
                (ValuationMetric.ticker == subq.c.ticker) &
                (ValuationMetric.date == subq.c.max_date)
            )
            .all()
        )
        
        data = []
        for m in metrics:
            company = db.query(Company).filter(Company.ticker == m.ticker).first()
            data.append({
                "Ticker": m.ticker,
                "Company": company.name if company else m.ticker,
                "Price": float(m.price) if m.price else None,
                "Market Cap": m.market_cap,
                "P/E": float(m.pe_ratio) if m.pe_ratio else None,
                "P/S": float(m.ps_ratio) if m.ps_ratio else None,
                "P/B": float(m.pb_ratio) if m.pb_ratio else None,
                "EV/Revenue": float(m.ev_revenue) if m.ev_revenue else None,
                "EV/EBITDA": float(m.ev_ebitda) if m.ev_ebitda else None,
                "Gross Margin": float(m.gross_margin) if m.gross_margin else None,
                "Operating Margin": float(m.operating_margin) if m.operating_margin else None,
                "Net Margin": float(m.net_margin) if m.net_margin else None,
                "ROE": float(m.roe) if m.roe else None,
                "ROA": float(m.roa) if m.roa else None,
            })
        
        return pd.DataFrame(data)
    finally:
        db.close()


def render_overview():
    """Render market overview page."""
    st.title("📊 Market Overview")
    
    df = load_all_metrics()
    
    if df.empty:
        st.warning("No data available. Please run the seed script first.")
        st.code("psql -d finance_app -f db/seed_data.sql", language="bash")
        return
    
    # Summary cards
    st.subheader("Portfolio Snapshot")
    
    cols = st.columns(len(df))
    for i, (_, row) in enumerate(df.iterrows()):
        with cols[i]:
            st.metric(
                label=row["Ticker"],
                value=f"${row['Price']:.2f}",
                delta=None,  # Would show daily change if we had it
            )
            st.caption(format_large_number(row["Market Cap"]))
    
    st.divider()
    
    # Valuation comparison
    st.subheader("Valuation Comparison")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # P/E comparison
        fig_pe = px.bar(
            df.sort_values("P/E"),
            x="Ticker",
            y="P/E",
            title="Price-to-Earnings Ratio",
            color="P/E",
            color_continuous_scale="RdYlGn_r",
        )
        fig_pe.update_layout(showlegend=False)
        st.plotly_chart(fig_pe, use_container_width=True)
    
    with col2:
        # EV/Revenue comparison
        fig_ev = px.bar(
            df.sort_values("EV/Revenue"),
            x="Ticker",
            y="EV/Revenue",
            title="EV/Revenue Ratio",
            color="EV/Revenue",
            color_continuous_scale="RdYlGn_r",
        )
        fig_ev.update_layout(showlegend=False)
        st.plotly_chart(fig_ev, use_container_width=True)
    
    # Profitability comparison
    st.subheader("Profitability Metrics")
    
    margin_df = df.melt(
        id_vars=["Ticker"],
        value_vars=["Gross Margin", "Operating Margin", "Net Margin"],
        var_name="Metric",
        value_name="Value"
    )
    
    fig_margins = px.bar(
        margin_df,
        x="Ticker",
        y="Value",
        color="Metric",
        barmode="group",
        title="Margin Comparison",
    )
    fig_margins.update_layout(yaxis_tickformat=".0%")
    st.plotly_chart(fig_margins, use_container_width=True)
    
    # Data table
    st.subheader("Detailed Metrics")
    
    # Format the dataframe for display
    display_df = df.copy()
    display_df["Market Cap"] = display_df["Market Cap"].apply(format_large_number)
    display_df["Gross Margin"] = display_df["Gross Margin"].apply(format_percent)
    display_df["Operating Margin"] = display_df["Operating Margin"].apply(format_percent)
    display_df["Net Margin"] = display_df["Net Margin"].apply(format_percent)
    display_df["ROE"] = display_df["ROE"].apply(format_percent)
    display_df["ROA"] = display_df["ROA"].apply(format_percent)
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_stock_detail(ticker: str):
    """Render stock detail page."""
    db = get_db()
    try:
        company = db.query(Company).filter(Company.ticker == ticker).first()
    finally:
        db.close()
    
    if not company:
        st.error(f"Company not found: {ticker}")
        return
    
    st.title(f"📈 {company.name} ({ticker})")
    
    # Load data
    prices_df = load_stock_prices(ticker)
    metrics = load_metrics(ticker)
    
    if prices_df.empty:
        st.warning("No price data available for this stock.")
        return
    
    # Key metrics
    st.subheader("Key Metrics")
    
    if metrics:
        cols = st.columns(5)
        with cols[0]:
            st.metric("Price", f"${float(metrics.price):.2f}")
        with cols[1]:
            st.metric("Market Cap", format_large_number(metrics.market_cap))
        with cols[2]:
            st.metric("P/E Ratio", format_ratio(float(metrics.pe_ratio) if metrics.pe_ratio else None, "x"))
        with cols[3]:
            st.metric("EV/Revenue", format_ratio(float(metrics.ev_revenue) if metrics.ev_revenue else None, "x"))
        with cols[4]:
            st.metric("ROE", format_percent(float(metrics.roe) if metrics.roe else None))
    
    st.divider()
    
    # Price chart
    st.subheader("Price History")
    
    # Time range selector
    range_options = {
        "1W": 7,
        "1M": 30,
        "3M": 90,
        "6M": 180,
        "1Y": 365,
        "All": None,
    }
    
    selected_range = st.radio(
        "Time Range",
        options=list(range_options.keys()),
        horizontal=True,
        index=2,  # Default to 3M
    )
    
    days = range_options[selected_range]
    if days:
        cutoff = datetime.now().date() - timedelta(days=days)
        chart_df = prices_df[prices_df["date"] >= cutoff]
    else:
        chart_df = prices_df
    
    # Candlestick chart
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
    )
    
    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=chart_df["date"],
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            name="Price",
        ),
        row=1, col=1
    )
    
    # Volume
    colors = ["red" if close < open else "green" 
              for open, close in zip(chart_df["open"], chart_df["close"])]
    
    fig.add_trace(
        go.Bar(
            x=chart_df["date"],
            y=chart_df["volume"],
            marker_color=colors,
            name="Volume",
            opacity=0.5,
        ),
        row=2, col=1
    )
    
    fig.update_layout(
        title=f"{ticker} Stock Price",
        yaxis_title="Price ($)",
        yaxis2_title="Volume",
        xaxis_rangeslider_visible=False,
        height=600,
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Additional metrics cards
    if metrics:
        st.subheader("Valuation & Profitability")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("#### Valuation")
            st.metric("P/E", format_ratio(float(metrics.pe_ratio) if metrics.pe_ratio else None, "x"))
            st.metric("P/S", format_ratio(float(metrics.ps_ratio) if metrics.ps_ratio else None, "x"))
            st.metric("P/B", format_ratio(float(metrics.pb_ratio) if metrics.pb_ratio else None, "x"))
        
        with col2:
            st.markdown("#### Enterprise Value")
            st.metric("EV", format_large_number(metrics.enterprise_value))
            st.metric("EV/Revenue", format_ratio(float(metrics.ev_revenue) if metrics.ev_revenue else None, "x"))
            st.metric("EV/EBITDA", format_ratio(float(metrics.ev_ebitda) if metrics.ev_ebitda else None, "x"))
        
        with col3:
            st.markdown("#### Profitability")
            st.metric("Gross Margin", format_percent(float(metrics.gross_margin) if metrics.gross_margin else None))
            st.metric("Operating Margin", format_percent(float(metrics.operating_margin) if metrics.operating_margin else None))
            st.metric("Net Margin", format_percent(float(metrics.net_margin) if metrics.net_margin else None))
    
    # Price data table
    with st.expander("View Price Data"):
        st.dataframe(
            prices_df.sort_values("date", ascending=False).head(30),
            use_container_width=True,
            hide_index=True,
        )


def render_screener():
    """Render stock screener page."""
    st.title("🔍 Stock Screener")
    
    df = load_all_metrics()
    
    if df.empty:
        st.warning("No data available.")
        return
    
    st.markdown("Filter stocks by valuation and profitability metrics.")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        pe_range = st.slider(
            "P/E Ratio",
            min_value=0.0,
            max_value=float(df["P/E"].max()) if df["P/E"].max() else 200.0,
            value=(0.0, 100.0),
        )
    
    with col2:
        margin_min = st.slider(
            "Min Net Margin",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            format="%.0f%%",
        )
    
    with col3:
        roe_min = st.slider(
            "Min ROE",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            format="%.0f%%",
        )
    
    # Apply filters
    filtered = df[
        (df["P/E"].between(pe_range[0], pe_range[1]) | df["P/E"].isna()) &
        ((df["Net Margin"] >= margin_min) | df["Net Margin"].isna()) &
        ((df["ROE"] >= roe_min) | df["ROE"].isna())
    ]
    
    st.subheader(f"Results ({len(filtered)} stocks)")
    
    # Format for display
    display_df = filtered.copy()
    display_df["Price"] = display_df["Price"].apply(lambda x: f"${x:.2f}" if x else "N/A")
    display_df["Market Cap"] = display_df["Market Cap"].apply(format_large_number)
    display_df["P/E"] = display_df["P/E"].apply(lambda x: f"{x:.1f}" if x else "N/A")
    display_df["EV/Revenue"] = display_df["EV/Revenue"].apply(lambda x: f"{x:.1f}" if x else "N/A")
    display_df["Gross Margin"] = display_df["Gross Margin"].apply(format_percent)
    display_df["Net Margin"] = display_df["Net Margin"].apply(format_percent)
    display_df["ROE"] = display_df["ROE"].apply(format_percent)
    
    st.dataframe(
        display_df[["Ticker", "Company", "Price", "Market Cap", "P/E", "EV/Revenue", "Net Margin", "ROE"]],
        use_container_width=True,
        hide_index=True,
    )


def main():
    """Main app."""
    # Sidebar navigation
    st.sidebar.title("📊 Finance App")
    
    page = st.sidebar.radio(
        "Navigation",
        ["Overview", "Stock Detail", "Screener"],
        index=0,
    )
    
    if page == "Overview":
        render_overview()
    
    elif page == "Stock Detail":
        companies = load_companies()
        if companies:
            ticker = st.sidebar.selectbox(
                "Select Stock",
                options=[t for t, n in companies],
                format_func=lambda x: f"{x} - {dict(companies).get(x, x)}",
            )
            render_stock_detail(ticker)
        else:
            st.warning("No companies in database.")
    
    elif page == "Screener":
        render_screener()
    
    # Footer
    st.sidebar.divider()
    st.sidebar.caption("Finance App v0.1.0")
    st.sidebar.caption("Data for demo purposes only")


if __name__ == "__main__":
    main()
