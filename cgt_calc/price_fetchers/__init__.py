"""Price fetchers for historical stock prices.

This package provides a flexible system for fetching historical stock prices
from multiple sources with configurable priority ordering.
"""

from .base_fetcher import BasePriceFetcher, PriceFetcher, PriceMissingError
from .cached_fetcher import CachedPriceFetcher
from .chained_fetcher import ChainedPriceFetcher
from .csv_fetcher import CsvPriceFetcher
from .fetcher_factory import (
    FetcherDependencies,
    create_price_fetcher,
    get_available_fetchers,
    get_default_fetcher_priority,
    parse_price_priority,
)
from .fetcher_registry import register_fetcher
from .gbp_converting_fetcher import GbpConvertingFetcher
from .initial_prices_parser import InitialPrices  # Re-export for backward compatibility
from .yfinance_fetcher import YFinancePriceFetcher

__all__ = [
    "BasePriceFetcher",
    "CachedPriceFetcher",
    "ChainedPriceFetcher",
    "CsvPriceFetcher",
    "FetcherDependencies",
    "GbpConvertingFetcher",
    "InitialPrices",  # Backward compatibility
    "PriceFetcher",
    "PriceMissingError",
    "YFinancePriceFetcher",
    "create_price_fetcher",
    "get_available_fetchers",
    "get_default_fetcher_priority",
    "parse_price_priority",
    "register_fetcher",
]
