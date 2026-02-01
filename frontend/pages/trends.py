"""
Valuation Trends Page - Time series analysis with bundle comparisons.

Features:
- Multi-security selection
- Custom bundle creation
- Pre-made bundles (sectors, FAANG, etc.)
- Properly weighted aggregate metrics
- Bundle vs bundle comparison
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import SessionLocal
from backend.models import Company
from backend.services.timeseries import TimeSeriesService, PREMADE_BUNDLES, SECTOR_DEFINITIONS

st.set_page_config(
    page_title="Valuation Trends",
    page_icon="📈",
    layout="wide",
)


def get_db():
    return SessionLocal()


@st.cache_data(ttl=300)
def load_all_tickers():
    """Load all available tickers."""
    db = get_db()
    try:
        companies = db.query(Company).filter(Company.ticker.isnot(None)).all()
        return {c.ticker: c.name for c in companies}
    finally:
        db.close()


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
    return f"${num:,.0f}"


# Metric display names
METRIC_LABELS = {
    "aggregate_pe": "P/E Ratio",
    "aggregate_ps": "P/S Ratio",
    "aggregate_ev_revenue": "EV/Revenue",
    "aggregate_ev_ebitda": "EV/EBITDA",
    "pe_ratio": "P/E Ratio",
    "ps_ratio": "P/S Ratio",
    "ev_revenue": "EV/Revenue",
    "ev_ebitda": "EV/EBITDA",
}


def render_individual_trends():
    """Render individual stock trend analysis."""
    st.subheader("📈 Individual Stock Trends")
    
    tickers = load_all_tickers()
    
    if not tickers:
        st.warning("No companies in database.")
        return
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected = st.multiselect(
            "Select Securities",
            options=list(tickers.keys()),
            default=list(tickers.keys())[:4] if len(tickers) >= 4 else list(tickers.keys()),
            format_func=lambda x: f"{x} - {tickers.get(x, '')}",
        )
    
    with col2:
        metric = st.selectbox(
            "Metric",
            options=["pe_ratio", "ps_ratio", "ev_revenue", "ev_ebitda"],
            format_func=lambda x: METRIC_LABELS.get(x, x),
        )
    
    # Date range
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime.now().date() - timedelta(days=30),
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            value=datetime.now().date(),
        )
    
    if not selected:
        st.info("Select at least one security to view trends.")
        return
    
    # Get data
    db = get_db()
    try:
        service = TimeSeriesService(db)
        df = service.get_metrics_dataframe(selected, start_date, end_date)
    finally:
        db.close()
    
    if df.empty:
        st.warning("No data available for the selected securities and date range.")
        return
    
    # Plot individual trends
    fig = px.line(
        df,
        x="date",
        y=metric,
        color="ticker",
        title=f"{METRIC_LABELS.get(metric, metric)} Over Time",
        labels={metric: METRIC_LABELS.get(metric, metric), "date": "Date"},
    )
    fig.update_layout(height=500, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    
    # Summary table
    st.subheader("Current Values")
    
    latest = df.sort_values("date").groupby("ticker").last().reset_index()
    display_cols = ["ticker", "price", "market_cap", metric]
    
    display_df = latest[display_cols].copy()
    display_df["market_cap"] = display_df["market_cap"].apply(format_large_number)
    display_df[metric] = display_df[metric].apply(lambda x: f"{x:.2f}x" if x else "N/A")
    display_df.columns = ["Ticker", "Price", "Market Cap", METRIC_LABELS.get(metric, metric)]
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_bundle_comparison():
    """Render bundle comparison analysis."""
    st.subheader("📊 Bundle Comparison")
    
    st.markdown("""
    Compare weighted averages across bundles. Metrics are properly weighted:
    - **Aggregate P/E** = Total Market Cap ÷ Total Net Income
    - **Aggregate EV/Revenue** = Total Enterprise Value ÷ Total Revenue
    
    This shows what you'd pay (and earn) if you bought all the companies in the bundle.
    """)
    
    tickers = load_all_tickers()
    
    # Bundle selection
    st.markdown("### Select Bundles to Compare")
    
    tab1, tab2, tab3 = st.tabs(["Pre-made Bundles", "Sectors", "Custom Bundle"])
    
    selected_bundles = {}
    
    with tab1:
        premade_options = list(PREMADE_BUNDLES.keys())
        selected_premade = st.multiselect(
            "Pre-made Bundles",
            options=premade_options,
            default=[],
            help="Select from popular stock groupings",
        )
        
        for bundle in selected_premade:
            bundle_tickers = [t for t in PREMADE_BUNDLES[bundle] if t in tickers]
            if bundle_tickers:
                selected_bundles[bundle] = bundle_tickers
                st.caption(f"**{bundle}**: {', '.join(bundle_tickers)}")
    
    with tab2:
        sector_options = list(SECTOR_DEFINITIONS.keys())
        selected_sectors = st.multiselect(
            "Sectors",
            options=sector_options,
            default=[],
            help="Select industry sectors",
        )
        
        db = get_db()
        try:
            service = TimeSeriesService(db)
            for sector in selected_sectors:
                sector_tickers = service.get_companies_by_sector(sector)
                sector_tickers = [t for t in sector_tickers if t in tickers]
                if sector_tickers:
                    selected_bundles[f"Sector: {sector}"] = sector_tickers
                    st.caption(f"**{sector}**: {', '.join(sector_tickers[:5])}{'...' if len(sector_tickers) > 5 else ''}")
        finally:
            db.close()
    
    with tab3:
        st.markdown("Create custom bundles by selecting securities:")
        
        # Allow up to 3 custom bundles
        for i in range(1, 4):
            with st.expander(f"Custom Bundle {i}", expanded=(i == 1)):
                bundle_name = st.text_input(
                    "Bundle Name",
                    value=f"My Bundle {i}",
                    key=f"custom_name_{i}",
                )
                bundle_stocks = st.multiselect(
                    "Select Securities",
                    options=list(tickers.keys()),
                    key=f"custom_stocks_{i}",
                    format_func=lambda x: f"{x} - {tickers.get(x, '')}",
                )
                
                if bundle_stocks and bundle_name:
                    selected_bundles[bundle_name] = bundle_stocks
    
    if not selected_bundles:
        st.info("Select at least one bundle or create a custom bundle to compare.")
        return
    
    # Metric and date range
    col1, col2, col3 = st.columns(3)
    
    with col1:
        metric = st.selectbox(
            "Metric to Compare",
            options=["aggregate_pe", "aggregate_ps", "aggregate_ev_revenue", "aggregate_ev_ebitda"],
            format_func=lambda x: METRIC_LABELS.get(x, x),
            key="bundle_metric",
        )
    
    with col2:
        start_date = st.date_input(
            "Start Date",
            value=datetime.now().date() - timedelta(days=30),
            key="bundle_start",
        )
    
    with col3:
        end_date = st.date_input(
            "End Date",
            value=datetime.now().date(),
            key="bundle_end",
        )
    
    # Calculate and display
    st.markdown("### Trend Comparison")
    
    db = get_db()
    try:
        service = TimeSeriesService(db)
        
        # Get comparison data
        comparison_df = service.compare_bundles(
            selected_bundles,
            start_date,
            end_date,
            metric,
        )
    finally:
        db.close()
    
    if comparison_df.empty:
        st.warning("No data available for the selected bundles and date range.")
        return
    
    # Plot comparison
    fig = go.Figure()
    
    colors = px.colors.qualitative.Set2
    
    for i, bundle in enumerate(comparison_df.columns):
        fig.add_trace(go.Scatter(
            x=comparison_df.index,
            y=comparison_df[bundle],
            mode="lines",
            name=bundle,
            line=dict(color=colors[i % len(colors)], width=2),
        ))
    
    fig.update_layout(
        title=f"Aggregate {METRIC_LABELS.get(metric, metric)} Comparison",
        xaxis_title="Date",
        yaxis_title=METRIC_LABELS.get(metric, metric),
        height=500,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Summary statistics
    st.markdown("### Bundle Statistics")
    
    summary_data = []
    
    db = get_db()
    try:
        service = TimeSeriesService(db)
        
        for bundle_name, bundle_tickers in selected_bundles.items():
            metrics = service.calculate_bundle_metrics(
                bundle_tickers, bundle_name, start_date, end_date
            )
            
            if metrics:
                latest = metrics[-1]
                first = metrics[0]
                
                current_val = getattr(latest, metric)
                start_val = getattr(first, metric)
                
                change = None
                if current_val and start_val:
                    change = ((current_val - start_val) / start_val) * 100
                
                summary_data.append({
                    "Bundle": bundle_name,
                    "Companies": latest.company_count,
                    "Total Market Cap": format_large_number(latest.total_market_cap),
                    "Total EV": format_large_number(latest.total_enterprise_value),
                    f"Current {METRIC_LABELS.get(metric, metric)}": f"{current_val:.2f}x" if current_val else "N/A",
                    "Change": f"{change:+.1f}%" if change else "N/A",
                })
    finally:
        db.close()
    
    if summary_data:
        st.dataframe(
            pd.DataFrame(summary_data),
            use_container_width=True,
            hide_index=True,
        )


def render_weighted_methodology():
    """Explain the weighted average methodology."""
    with st.expander("ℹ️ How Weighted Averages Work"):
        st.markdown("""
        ### Proper Aggregate Weighting
        
        We don't simply average the ratios — that would be misleading. Instead, we sum the components:
        
        | Metric | Formula |
        |--------|---------|
        | **Aggregate P/E** | Sum(Market Caps) ÷ Sum(Net Incomes) |
        | **Aggregate P/S** | Sum(Market Caps) ÷ Sum(Revenues) |
        | **Aggregate EV/Revenue** | Sum(Enterprise Values) ÷ Sum(Revenues) |
        | **Aggregate EV/EBITDA** | Sum(Enterprise Values) ÷ Sum(EBITDAs) |
        
        ### Why This Matters
        
        **Example**: Bundle with 2 companies:
        - Company A: $100B market cap, $10B earnings → P/E = 10x
        - Company B: $10B market cap, $0.5B earnings → P/E = 20x
        
        ❌ **Simple average**: (10 + 20) / 2 = **15x** (misleading)
        
        ✅ **Proper aggregate**: ($100B + $10B) / ($10B + $0.5B) = **10.5x**
        
        The proper aggregate reflects what you'd actually pay if you bought both companies — 
        it's dominated by the larger company (which is correct!).
        """)


def main():
    st.title("📈 Valuation Trends")
    
    st.markdown("""
    Analyze valuation metrics over time. Compare individual securities or create bundles 
    with properly weighted aggregates.
    """)
    
    # Methodology explanation
    render_weighted_methodology()
    
    st.divider()
    
    # Tabs for different views
    tab1, tab2 = st.tabs(["Individual Securities", "Bundle Comparison"])
    
    with tab1:
        render_individual_trends()
    
    with tab2:
        render_bundle_comparison()


if __name__ == "__main__":
    main()
