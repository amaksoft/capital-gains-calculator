"""Base protocol and exceptions for price fetchers."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cgt_calc.exceptions import CgtError

if TYPE_CHECKING:
    import datetime
    from decimal import Decimal

    from .fetcher_type import FetcherType


class PriceMissingError(CgtError):
    """Raised when a price cannot be found from any source."""


class BasePriceFetcher(ABC):
    """Abstract base class for price fetchers.

    This enables automatic discovery via __subclasses__().
    All concrete price fetchers should inherit from this class.

    Note: We also maintain the PriceFetcher Protocol for structural type checking.
    """

    # Attributes set by @register_fetcher decorator (public framework API)
    fetcher_name: str
    fetcher_type: FetcherType
    show_in_help: bool
    auto_cache: bool


@runtime_checkable
class PriceFetcher(Protocol):
    """Protocol for fetching stock prices with currency awareness.

    All price fetchers implement this unified protocol. Each fetcher declares
    what currency it returns via the native_currency property.

    The framework uses this to:
    - Compose wrappers (e.g., currency conversion, caching)
    - Validate currency homogeneity (e.g., in chained fetchers)
    - Provide clear contracts about what currency is returned

    Example:
        @register_fetcher("myapi", fetcher_type=FetcherType.NETWORK, auto_cache=True)
        class MyApiFetcher(BasePriceFetcher):
            @property
            def native_currency(self) -> str:
                return "USD"

            @property
            def name(self) -> str:
                return self.fetcher_name

            def get_closing_price(self, symbol, date) -> Decimal:
                # Fetch and return USD price
                return Decimal(self._api_call(symbol, date)['price'])

            def get_current_market_price(self, symbol) -> Decimal | None:
                # Fetch current USD price
                return Decimal(self._api_call_current(symbol)['price'])

    """

    @property
    def name(self) -> str:
        """Return fetcher name for logging and debugging."""
        ...

    @property
    def native_currency(self) -> str:
        """Return the ISO currency code this fetcher returns prices in.

        Examples: "USD", "EUR", "GBP"

        This property is used by:
        - The factory to determine if currency conversion is needed
        - Wrappers like CachedPriceFetcher to pass through the currency
        - ChainedPriceFetcher to validate currency homogeneity
        """
        ...

    def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Fetch historical closing price in native currency.

        Args:
            symbol: Stock ticker symbol
            date: Date for which to fetch the price

        Returns:
            Price in the fetcher's native_currency

        Raises:
            PriceMissingError: If price cannot be found

        """
        ...

    def get_current_market_price(self, symbol: str) -> Decimal | None:
        """Fetch current market price in native currency.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price in native_currency, or None if not available

        """
        ...
