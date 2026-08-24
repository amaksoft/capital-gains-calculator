"""Obtain current prices to calculate unrealized gains."""

from __future__ import annotations

from contextlib import suppress
import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import yfinance as yf  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from .currency_converter import CurrencyConverter


class CurrentPriceFetcher:
    """Converter which holds rate history."""

    def __init__(
        self,
        converter: CurrencyConverter,
        current_prices_data: dict[str, Decimal | None] | None = None,
        historical_prices_data: dict[str, dict[datetime.date, Decimal]] | None = None,
    ):
        """Load data from exchange_rates_file and optionally from initial_data."""
        self.current_prices_data = current_prices_data
        self.historical_prices_data = historical_prices_data or {}
        self.converter = converter

    def _convert_to_gbp(self, price: Decimal, currency: str | None) -> Decimal:
        """Convert a price quoted in the given yfinance currency to GBP.

        yfinance uses the non-ISO code "GBp" (lowercase p) for LSE-listed
        instruments quoted in pence rather than pounds, so that case is
        converted directly instead of going through CurrencyConverter, which
        only knows real ISO currency codes and has no exchange rate for it.
        """
        if currency == "GBp":
            return price / Decimal(100)
        return self.converter.to_gbp(
            price, currency or "USD", datetime.datetime.now().date()
        )

    def get_current_market_price(self, symbol: str) -> Decimal | None:
        """Given a symbol gets the current market price."""
        if self.current_prices_data is not None and symbol in self.current_prices_data:
            return self.current_prices_data[symbol]

        ticker = yf.Ticker(symbol).info
        if not ticker:
            return None
        # ETFs often lack currentPrice, e.g. VTI only has regularMarketPrice
        # and navPrice.
        market_price = (
            ticker.get("currentPrice")
            or ticker.get("regularMarketPrice")
            or ticker.get("navPrice")
        )
        if market_price is None:
            return None
        market_price_decimal = Decimal(format(market_price, ".15g"))
        return self._convert_to_gbp(market_price_decimal, ticker.get("currency"))

    @staticmethod
    def _split_factor_after(yf_ticker: yf.Ticker, date: datetime.date) -> Decimal:
        """Return the factor that undoes split back-adjustment for a date.

        yfinance always restates historical prices in today's share units, so a
        close from before a split comes back divided by that split's ratio.
        That is the wrong basis here: the price gets multiplied by a holding
        recorded in the units of the day, so a later split would silently value
        the position at a fraction of its worth. Multiplying by the ratio of
        every split since restores the price actually quoted on the day.
        """
        factor = Decimal(1)
        try:
            splits = yf_ticker.splits
        except Exception:  # noqa: BLE001 - price data must not fail on this
            return factor

        for split_date, ratio in splits.items():
            if split_date.date() > date and ratio:
                factor *= Decimal(format(ratio, ".15g"))
        return factor

    def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Get the price of the share on closing time."""
        with suppress(KeyError):
            return self.historical_prices_data[symbol][date]

        yf_ticker = yf.Ticker(symbol)
        prices = yf_ticker.history(
            interval="1d",
            start=date.strftime("%Y-%m-%d"),
            end=(date + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
            # yfinance defaults to auto_adjust=True, which back-adjusts closes
            # for every dividend paid since. That is the wrong number for a
            # historical valuation - a spin-off apportionment has to use the
            # price actually quoted on the day - and it is not reproducible,
            # because the adjustment factor moves each time a dividend goes ex.
            auto_adjust=False,
        )
        closing_price = prices.iloc[0]["Close"]
        closing_price_decimal = Decimal(format(closing_price, ".15g"))
        closing_price_decimal *= self._split_factor_after(yf_ticker, date)
        currency = yf_ticker.info.get("currency") if yf_ticker.info else None
        return self._convert_to_gbp(closing_price_decimal, currency)
