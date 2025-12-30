"""Factory functions for creating price fetchers based on configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .base_fetcher import BasePriceFetcher, PriceFetcher
from .cached_fetcher import CachedPriceFetcher
from .chained_fetcher import ChainedPriceFetcher
from .csv_fetcher import CsvPriceFetcher
from .gbp_converting_fetcher import GbpConvertingFetcher
from .yfinance_fetcher import YFinancePriceFetcher

if TYPE_CHECKING:
    from pathlib import Path

    from cgt_calc.currency_converter import CurrencyConverter


@dataclass
class FetcherDependencies:
    """Dependencies for price fetchers.

    All price fetchers receive this object and access the properties they need.
    To add a new dependency:
    1. Add a typed property below
    2. Pass the value when creating FetcherDependencies in main.py
    3. Access it in your fetcher via deps.property_name

    Attributes:
        currency_converter: For converting prices to GBP
        initial_prices_csv: Path to CSV file with initial prices, or None for default
        verbose: Enable verbose logging

    """

    currency_converter: CurrencyConverter
    initial_prices_csv: Path | None = None
    verbose: bool = False


def _discover_fetchers() -> dict[str, type]:
    """Discover all registered price fetchers using reflection.

    Uses __subclasses__() to find all classes that inherit from BasePriceFetcher
    and have been decorated with @register_fetcher.

    Returns:
        Dictionary mapping fetcher name to class

    """
    registry: dict[str, type] = {}

    for subclass in BasePriceFetcher.__subclasses__():
        # Check if class was decorated with @register_fetcher
        if hasattr(subclass, "fetcher_name"):
            name = subclass.fetcher_name
            registry[name] = subclass

    return registry


def get_available_fetchers() -> list[str]:
    """Get all available price fetcher names that should be shown in help text.

    Uses __subclasses__() to discover all registered fetchers.

    Returns:
        List of fetcher names

    """
    registry = _discover_fetchers()

    return [
        name
        for name, fetcher_class in registry.items()
        if getattr(fetcher_class, "show_in_help", False)
    ]


def get_default_fetcher_priority() -> str:
    """Get the default priority order for price sources.

    Returns:
        Comma-separated string of default priority order

    """
    return f"{YFinancePriceFetcher.fetcher_name},{CsvPriceFetcher.fetcher_name}"


def parse_price_priority(priority_str: str) -> list[str]:
    """Parse comma-separated priority string into list of source names.

    Args:
        priority_str: Comma-separated list of source names (e.g., "yfinance,csv")

    Returns:
        List of source names in priority order

    Raises:
        ValueError: If unknown source name is provided

    Examples:
        >>> parse_price_priority("yfinance,csv")
        ["yfinance", "csv"]
        >>> parse_price_priority("csv")
        ["csv"]

    """
    sources = [s.strip() for s in priority_str.split(",")]
    valid_sources = set(get_available_fetchers())

    for source in sources:
        if source not in valid_sources:
            raise ValueError(
                f"Unknown price source: '{source}'. "
                f"Valid sources: {', '.join(sorted(valid_sources))}"
            )

    return sources


def create_price_fetcher(
    priority: str,
    deps: FetcherDependencies,
) -> PriceFetcher:
    """Create price fetcher from priority string and dependencies.

    Args:
        priority: Comma-separated string of fetcher names in priority order
        deps: Dependencies object with all required dependencies

    Returns:
        Single fetcher if priority has 1 element, ChainedPriceFetcher otherwise

    Raises:
        ValueError: If priority list is empty or unknown source

    """
    # Parse priority string into list
    priority_list = parse_price_priority(priority)

    if not priority_list:
        raise ValueError("Priority list cannot be empty")

    registry = _discover_fetchers()
    fetchers: list[PriceFetcher] = []

    for source in priority_list:
        if source not in registry:
            valid = ", ".join(sorted(registry.keys()))
            raise ValueError(
                f"Unknown price source: '{source}'. Valid sources: {valid}"
            )

        fetcher_class = registry[source]

        # Simple: just instantiate with deps
        fetcher_instance = fetcher_class(deps)

        # Auto-wrap native currency fetchers with converter (if not already GBP)
        if hasattr(fetcher_instance, "native_currency"):
            native_currency = fetcher_instance.native_currency
            if native_currency != "GBP":
                fetcher_instance = GbpConvertingFetcher(
                    fetcher_instance, deps.currency_converter, deps.verbose
                )

        # Auto-wrap fetchers that request caching
        if getattr(fetcher_class, "auto_cache", False):
            fetcher_instance = CachedPriceFetcher(fetcher_instance, deps)

        fetchers.append(fetcher_instance)

    if len(fetchers) == 1:
        return fetchers[0]
    return ChainedPriceFetcher(fetchers, deps, native_currency="GBP")
