"""CSV-based price fetcher using InitialPrices."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cgt_calc.exceptions import ExchangeRateMissingError

from .base_fetcher import BasePriceFetcher, PriceMissingError
from .fetcher_registry import register_fetcher
from .fetcher_type import FetcherType
from .initial_prices_parser import InitialPrices

if TYPE_CHECKING:
    import datetime
    from decimal import Decimal

    from .fetcher_factory import FetcherDependencies

logger = logging.getLogger(__name__)


@register_fetcher("csv", fetcher_type=FetcherType.LOCAL, show_in_help=True)
class CsvPriceFetcher(BasePriceFetcher):
    """Fetches prices from CSV file (initial_prices csv).

    This fetcher wraps the existing InitialPrices class to provide
    a consistent interface with other price fetchers. It supports
    currency conversion from the specified CSV currency to GBP.
    """

    def __init__(self, deps: FetcherDependencies):
        """Initialize CSV price fetcher.

        Args:
            deps: Dependencies object with initial_prices_csv, verbose

        The currency is determined from:
        1. Currency header in CSV file (# Currency: USD)
        2. Default to "GBP" (with warning)

        """
        self._initial_prices = InitialPrices(deps.initial_prices_csv)
        self._verbose = deps.verbose

        # Determine currency from CSV header or default to GBP
        if self._initial_prices.currency is not None:
            self._csv_currency = self._initial_prices.currency
        else:
            # No currency specified - warn and default to GBP for backward compatibility
            self._csv_currency = "GBP"
            csv_file_name = (
                self._initial_prices.initial_prices_file.name
                if self._initial_prices.initial_prices_file
                else "built-in initial_prices.csv"
            )
            logger.warning(
                "CSV file '%s' has no currency header (# Currency: XXX). "
                "Assuming GBP for backward compatibility. "
                "Please add '# Currency: GBP' to the file header.",
                csv_file_name,
            )

    def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Fetch closing price from CSV file.

        Args:
            symbol: Stock ticker symbol
            date: Date for which to fetch the price

        Returns:
            Price in CSV's configured currency (native_currency)

        Raises:
            PriceMissingError: If price not found in CSV

        """
        # Fetch price from CSV (raises ExchangeRateMissingError if not found)
        try:
            return self._initial_prices.get(date, symbol)
        except ExchangeRateMissingError as e:
            raise PriceMissingError(f"CSV: {symbol} on {date} not in file") from e

    def get_current_market_price(self, symbol: str) -> Decimal | None:
        """CSV fetcher does not support current market prices.

        Returns:
            None: CSV only provides historical prices

        """
        if self._verbose:
            logger.info(
                "CSV fetcher does not support current market prices for %s", symbol
            )
        return None

    @property
    def native_currency(self) -> str:
        """Return native currency from CSV configuration."""
        return self._csv_currency

    @property
    def name(self) -> str:
        """Return fetcher name from decorator metadata."""
        return self.fetcher_name
