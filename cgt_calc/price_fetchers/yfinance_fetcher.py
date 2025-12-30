"""yfinance-based price fetcher."""

from __future__ import annotations

import datetime
from decimal import Decimal
import logging
from typing import TYPE_CHECKING

import yfinance as yf  # type: ignore[import-untyped]  # yfinance has no type stubs

from .base_fetcher import BasePriceFetcher, PriceMissingError
from .fetcher_registry import register_fetcher
from .fetcher_type import FetcherType

if TYPE_CHECKING:
    from .fetcher_factory import FetcherDependencies

logger = logging.getLogger(__name__)


@register_fetcher(
    "yfinance", fetcher_type=FetcherType.NETWORK, show_in_help=True, auto_cache=True
)
class YFinancePriceFetcher(BasePriceFetcher):
    """Fetches prices from Yahoo Finance.

    This fetcher wraps yfinance API to provide both historical and current
    stock prices. For caching, wrap this fetcher with CachedPriceFetcher.
    """

    def __init__(self, deps: FetcherDependencies):
        """Initialize yfinance price fetcher.

        Args:
            deps: Dependencies object with verbose flag

        """
        self._verbose = deps.verbose

    def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Fetch historical closing price from Yahoo Finance.

        Args:
            symbol: Stock ticker symbol
            date: Date for which to fetch the price

        Returns:
            Price in USD

        Raises:
            PriceMissingError: If price not found on yfinance

        """
        try:
            prices = yf.Ticker(symbol).history(
                interval="1d",
                start=date.strftime("%Y-%m-%d"),
                end=(date + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
            )

            if prices.empty:
                msg = f"yfinance: No data found for {symbol} on {date}"
                raise PriceMissingError(msg)

            closing_price = prices.iloc[0]["Close"]
            return Decimal(format(closing_price, ".15g"))
        except (KeyError, IndexError) as e:
            # Expected: missing data in yfinance response
            raise PriceMissingError(f"yfinance: No data for {symbol} on {date}") from e
        except (ValueError, TypeError) as e:
            # Expected: data format issues during conversion
            raise PriceMissingError(
                f"yfinance: Invalid data format for {symbol} on {date}: {e}"
            ) from e
        # Let AttributeError and other exceptions propagate - they indicate bugs

    def get_current_market_price(self, symbol: str) -> Decimal | None:
        """Fetch current market price from Yahoo Finance.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price in USD, or None if not available

        """
        try:
            ticker = yf.Ticker(symbol).info
            if not ticker or "currentPrice" not in ticker:
                return None
            market_price_str = ticker["currentPrice"]
            return Decimal(format(market_price_str, ".15g"))
        except (KeyError, ValueError, TypeError) as e:
            # Expected: yfinance API errors, conversion errors, or missing data
            if self._verbose:
                logger.info(
                    "yfinance: Failed to get current price for %s: %s", symbol, e
                )
            return None
        # Let AttributeError and other exceptions propagate - they indicate bugs

    @property
    def native_currency(self) -> str:
        """Return native currency for this fetcher."""
        return "USD"

    @property
    def name(self) -> str:
        """Return fetcher name from decorator metadata."""
        return self.fetcher_name
