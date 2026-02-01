"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import stocks, filings, indices, metrics
from backend.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Finance App API",
    description="Financial data platform for stock prices, SEC filings, and valuation metrics",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"])
app.include_router(filings.router, prefix="/api/filings", tags=["filings"])
app.include_router(indices.router, prefix="/api/indices", tags=["indices"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])


@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok", "app": "finance-app"}


@app.get("/health")
def health():
    """Health check for load balancers."""
    return {"status": "healthy"}
