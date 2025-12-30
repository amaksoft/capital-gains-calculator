"""GBP conversion wrapper for price fetchers."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from cgt_calc.exceptions import ExchangeRateMissingError

from .base_fetcher import BasePriceFetcher, PriceFetcher, PriceMissingError
from .fetcher_registry import register_fetcher
from .fetcher_type import FetcherType

if TYPE_CHECKING:
    from decimal import Decimal

    from cgt_calc.currency_converter import CurrencyConverter

logger = logging.getLogger(__name__)


@register_fetcher(
    "gbp_converting", fetcher_type=FetcherType.TRANSIENT, show_in_help=False
)
class GbpConvertingFetcher(BasePriceFetcher):
    """Wrapper that automatically converts prices from native currency to GBP.

    This wrapper implements the PriceFetcher protocol with native_currency="GBP".
    It wraps another PriceFetcher and converts prices to GBP using CurrencyConverter.

    This provides separation of concerns:
    - The wrapped fetcher focuses on fetching prices in its native currency
    - This wrapper handles conversion to GBP
    - Errors during conversion are converted to PriceMissingError

    The wrapper is transparent to users - the factory automatically applies it when
    needed based on the fetcher's native_currency property.
    """

    def __init__(
        self,
        fetcher: PriceFetcher,
        converter: CurrencyConverter,
        verbose: bool = False,
    ):
        """Initialize currency converting fetcher.

        Args:
            fetcher: The underlying PriceFetcher to wrap
            converter: CurrencyConverter for converting to GBP
            verbose: Enable verbose logging

        Raises:
            ValueError: If fetcher already returns GBP (wrapping would be redundant)

        """
        if fetcher.native_currency == "GBP":
            raise ValueError(
                f"GbpConvertingFetcher cannot wrap a GBP fetcher ({fetcher.name}). "
                f"This wrapper is only for converting non-GBP prices to GBP."
            )

        self._wrapped_fetcher = fetcher
        self._converter = converter
        self._verbose = verbose

    def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Fetch historical price and convert to GBP.

        Args:
            symbol: Stock ticker symbol
            date: Date for which to fetch the price

        Returns:
            Price in GBP (this fetcher's native currency)

        Raises:
            PriceMissingError: If price not found or conversion fails

        """
        # Fetch price in wrapped fetcher's native currency
        wrapped_currency = self._wrapped_fetcher.native_currency
        native_price = self._wrapped_fetcher.get_closing_price(symbol, date)

        # Convert to GBP
        try:
            gbp_price = self._converter.to_gbp(native_price, wrapped_currency, date)
        except ExchangeRateMissingError as e:
            raise PriceMissingError(
                f"Cannot convert {symbol} price from {wrapped_currency} to GBP on {date}: {e}"
            ) from e
        else:
            if self._verbose:
                logger.debug(
                    "Converted %s %s to %s GBP for %s on %s",
                    native_price,
                    wrapped_currency,
                    gbp_price,
                    symbol,
                    date,
                )
            return gbp_price

    def get_current_market_price(self, symbol: str) -> Decimal | None:
        """Fetch current price and convert to GBP.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price in GBP (this fetcher's native currency), or None if not available

        """
        # Fetch price in wrapped fetcher's native currency
        wrapped_currency = self._wrapped_fetcher.native_currency
        native_price = self._wrapped_fetcher.get_current_market_price(symbol)

        if native_price is None:
            return None

        # Convert to GBP
        today = datetime.date.today()
        try:
            gbp_price = self._converter.to_gbp(native_price, wrapped_currency, today)
        except ExchangeRateMissingError as e:
            # Can't convert current price - log and return None
            if self._verbose:
                logger.warning(
                    "Cannot convert current price for %s from %s to GBP: %s",
                    symbol,
                    wrapped_currency,
                    e,
                )
            return None
        else:
            if self._verbose:
                logger.debug(
                    "Converted current price %s %s to %s GBP for %s",
                    native_price,
                    wrapped_currency,
                    gbp_price,
                    symbol,
                )
            return gbp_price

    @property
    def native_currency(self) -> str:
        """Return native currency (always GBP since we convert to GBP)."""
        return "GBP"

    @property
    def name(self) -> str:
        """Return descriptive name showing conversion."""
        wrapped_currency = self._wrapped_fetcher.native_currency
        return (
            f"{self._wrapped_fetcher.name} ({wrapped_currency}->{self.native_currency})"
        )
