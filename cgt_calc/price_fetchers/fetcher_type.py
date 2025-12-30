"""Enum for categorizing price fetcher types."""

from __future__ import annotations

from enum import Enum


class FetcherType(Enum):
    """Categories of price fetchers based on their data source."""

    NETWORK = "network"  # Fetches from network (e.g., yfinance) - needs caching
    LOCAL = "local"  # Fetches from local files (e.g., CSV)
    TRANSIENT = "transient"  # Temporary/wrapper fetchers (e.g., cached, chained)
