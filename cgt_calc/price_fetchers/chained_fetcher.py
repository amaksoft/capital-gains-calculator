"""Chained price fetcher that tries multiple sources in order."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base_fetcher import BasePriceFetcher, PriceFetcher, PriceMissingError
from .fetcher_registry import register_fetcher
from .fetcher_type import FetcherType

if TYPE_CHECKING:
    import datetime
    from decimal import Decimal

    from .fetcher_factory import FetcherDependencies

logger = logging.getLogger(__name__)


@register_fetcher("chained", fetcher_type=FetcherType.TRANSIENT, show_in_help=False)
class ChainedPriceFetcher(BasePriceFetcher):
    """Tries multiple price fetchers in order until one succeeds.

    All fetchers must return prices in the same currency, specified at construction.
    Provides detailed logging of all attempts for visibility and debugging
    when verbose mode is enabled.
    """

    def __init__(
        self,
        fetchers: list[PriceFetcher],
        deps: FetcherDependencies,
        native_currency: str = "GBP",
    ):
        """Initialize chained price fetcher.

        Args:
            fetchers: List of price fetchers to try in order
            deps: Dependencies object (used for verbose flag)
            native_currency: Currency that all fetchers must return (default: GBP)

        Raises:
            ValueError: If fetchers list is empty or if any fetcher has a different native_currency

        """
        if not fetchers:
            raise ValueError("ChainedPriceFetcher requires at least one fetcher")

        # Validate all fetchers have the same native currency
        self._native_currency = native_currency
        for fetcher in fetchers:
            if fetcher.native_currency != native_currency:
                raise ValueError(
                    f"ChainedPriceFetcher requires all fetchers to have native_currency={native_currency!r}, "
                    f"but {fetcher.name} has native_currency={fetcher.native_currency!r}"
                )

        self._fetchers = fetchers
        self._verbose = deps.verbose

    def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Try each fetcher in order, return first success.

        Logs all attempts when verbose mode is enabled.

        Args:
            symbol: Stock ticker symbol
            date: Date for which to fetch the price

        Returns:
            Price in the chain's native_currency

        Raises:
            PriceMissingError: If all fetchers fail to find the price

        """
        if self._verbose:
            logger.info("Fetching price for %s on %s...", symbol, date)

        errors = []

        for i, fetcher in enumerate(self._fetchers, 1):
            try:
                if self._verbose:
                    logger.info(
                        "  [%s/%s] Trying %s...", i, len(self._fetchers), fetcher.name
                    )

                price = fetcher.get_closing_price(symbol, date)
            except PriceMissingError as e:
                if self._verbose:
                    logger.info("  ✗ %s failed: %s", fetcher.name, e)
                errors.append(f"{fetcher.name}: {e}")
                continue
            else:
                if self._verbose:
                    logger.info(
                        "  ✓ Found price for %s on %s: %s GBP (source: %s)",
                        symbol,
                        date,
                        price,
                        fetcher.name,
                    )

                return price

        # All fetchers failed
        all_names = ", ".join(f.name for f in self._fetchers)
        logger.error(
            "Price not found for %s on %s. Tried all sources: %s",
            symbol,
            date,
            all_names,
        )
        raise PriceMissingError(
            f"Price not found for {symbol} on {date}. Tried: {all_names}\n"
            + "\n".join(f"  - {err}" for err in errors)
        )

    def get_current_market_price(self, symbol: str) -> Decimal | None:
        """Try each fetcher in order for current price, return first success.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price in GBP, or None if not available from any source

        """
        if self._verbose:
            logger.info("Fetching current market price for %s...", symbol)

        for i, fetcher in enumerate(self._fetchers, 1):
            try:
                if self._verbose:
                    logger.info(
                        "  [%s/%s] Trying %s...", i, len(self._fetchers), fetcher.name
                    )

                price = fetcher.get_current_market_price(symbol)
            except PriceMissingError as e:
                if self._verbose:
                    logger.info(
                        "  ✗ %s does not support current prices: %s", fetcher.name, e
                    )
                continue
            else:
                if price is not None:
                    if self._verbose:
                        logger.info(
                            "  ✓ Found current price for %s: %s GBP (source: %s)",
                            symbol,
                            price,
                            fetcher.name,
                        )
                    return price
                if self._verbose:
                    logger.info("  ✗ %s: No current price available", fetcher.name)

        # All fetchers failed or returned None
        if self._verbose:
            all_names = ", ".join(f.name for f in self._fetchers)
            logger.info(
                "Current price not found for %s from any source: %s", symbol, all_names
            )
        return None

    @property
    def native_currency(self) -> str:
        """Return the native currency of this chain."""
        return self._native_currency

    @property
    def name(self) -> str:
        """Return fetcher name (auto-generated based on sub-fetchers)."""
        wrapper_name = self.fetcher_name
        sub_fetcher_names = "+".join(f.name for f in self._fetchers)
        return f"{wrapper_name}({sub_fetcher_names})"
