"""Caching wrapper for price fetchers."""

from __future__ import annotations

from contextlib import suppress
import logging
from typing import TYPE_CHECKING

from .base_fetcher import BasePriceFetcher, PriceFetcher
from .fetcher_registry import register_fetcher
from .fetcher_type import FetcherType

if TYPE_CHECKING:
    import datetime
    from decimal import Decimal

    from .fetcher_factory import FetcherDependencies

logger = logging.getLogger(__name__)


@register_fetcher("cached", fetcher_type=FetcherType.TRANSIENT, show_in_help=False)
class CachedPriceFetcher(BasePriceFetcher):
    """Wrapper that adds caching to any price fetcher.

    This wrapper maintains an in-memory cache of fetched prices to avoid
    redundant API calls for the same symbol/date combinations.

    The wrapper passes through the wrapped fetcher's native_currency.
    """

    def __init__(
        self,
        fetcher: PriceFetcher,
        deps: FetcherDependencies,
        historical_prices_data: dict[str, dict[datetime.date, Decimal]] | None = None,
        current_prices_data: dict[str, Decimal | None] | None = None,
    ):
        """Initialize cached price fetcher.

        Args:
            fetcher: The underlying price fetcher to wrap
            deps: Dependencies object (used for verbose flag)
            historical_prices_data: Optional pre-loaded historical prices (for testing)
            current_prices_data: Optional pre-loaded current prices (for testing)

        """
        self._wrapped_fetcher = fetcher
        self._historical_cache: dict[str, dict[datetime.date, Decimal]] = (
            historical_prices_data or {}
        )
        self._current_cache: dict[str, Decimal | None] = current_prices_data or {}
        self._verbose = deps.verbose

    def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Fetch historical closing price with caching.

        Args:
            symbol: Stock ticker symbol
            date: Date for which to fetch the price

        Returns:
            Price in GBP

        Raises:
            PriceMissingError: If price not found

        """
        # Check cache first
        with suppress(KeyError):
            price = self._historical_cache[symbol][date]
            if self._verbose:
                logger.info("Cache HIT: %s on %s = %s", symbol, date, price)
            return price

        # Cache miss - fetch from underlying fetcher
        if self._verbose:
            logger.info(
                "Cache MISS: %s on %s, fetching from %s",
                symbol,
                date,
                self._wrapped_fetcher.name,
            )

        price = self._wrapped_fetcher.get_closing_price(symbol, date)

        # Cache the result
        if symbol not in self._historical_cache:
            self._historical_cache[symbol] = {}
        self._historical_cache[symbol][date] = price

        return price

    def get_current_market_price(self, symbol: str) -> Decimal | None:
        """Fetch current market price with caching.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price in GBP, or None if not available

        """
        # Check cache first
        if symbol in self._current_cache:
            price = self._current_cache[symbol]
            if self._verbose:
                logger.info("Cache HIT: current price for %s = %s", symbol, price)
            return price

        # Cache miss - fetch from underlying fetcher
        if self._verbose:
            logger.info(
                "Cache MISS: current price for %s, fetching from %s",
                symbol,
                self._wrapped_fetcher.name,
            )

        price = self._wrapped_fetcher.get_current_market_price(symbol)

        # Cache the result
        self._current_cache[symbol] = price

        return price

    @property
    def native_currency(self) -> str:
        """Return the wrapped fetcher's native currency."""
        return self._wrapped_fetcher.native_currency

    @property
    def name(self) -> str:
        """Return fetcher name showing what's being cached."""
        wrapper_name = self.fetcher_name
        wrapped_name = self._wrapped_fetcher.name
        return f"{wrapper_name}({wrapped_name})"
