"""Registration decorator for price fetchers."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from .base_fetcher import BasePriceFetcher
    from .fetcher_type import FetcherType

T = TypeVar("T", bound="BasePriceFetcher")


def register_fetcher(
    name: str,
    *,
    fetcher_type: FetcherType,
    show_in_help: bool = False,
    auto_cache: bool = False,
) -> Callable[[type[T]], type[T]]:
    """Register a price fetcher with metadata.

    Args:
        name: Short alias for this fetcher (e.g., 'csv', 'yfinance')
        fetcher_type: Type of fetcher (NETWORK, LOCAL, or TRANSIENT)
        show_in_help: Whether to show in CLI help text
        auto_cache: Whether to automatically wrap with CachedPriceFetcher

    Returns:
        Decorator function that adds metadata to the class

    Example:
        @register_fetcher('yfinance', fetcher_type=FetcherType.NETWORK, show_in_help=True, auto_cache=True)
        class YFinancePriceFetcher(BasePriceFetcher):
            ...

    """

    def decorator(cls: type[T]) -> type[T]:
        # Store metadata on the class for reflection (public framework API)
        cls.fetcher_name = name
        cls.fetcher_type = fetcher_type
        cls.show_in_help = show_in_help
        cls.auto_cache = auto_cache
        return cls

    return decorator
