"""Test CurrentPriceFetcher."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pandas as pd
import pytest

from cgt_calc.currency_converter import CurrencyConverter
from cgt_calc.current_price_fetcher import CurrentPriceFetcher
from cgt_calc.exceptions import MarketDataMissingError
from cgt_calc.model import CurrencyCode


class FakeTicker:
    """Stand-in for yf.Ticker that returns a canned info dict."""

    def __init__(self, info: dict[str, float | str]) -> None:
        """Store the info dict to return."""
        self.info = info


def _fetcher() -> CurrentPriceFetcher:
    today = datetime.datetime.now().date()
    converter = CurrencyConverter(
        None,
        {
            today: {
                CurrencyCode("USD"): Decimal("1.25"),
                CurrencyCode("EUR"): Decimal("1.15"),
            }
        },
    )
    return CurrentPriceFetcher(converter)


def test_uses_current_price_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """currentPrice, when present, is used as-is."""
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeTicker({"currentPrice": 100.0}),
    )
    price = _fetcher().get_current_market_price("AAPL")
    assert price == Decimal("100.0") / Decimal("1.25")


def test_falls_back_to_regular_market_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """ETFs like VTI lack currentPrice but carry regularMarketPrice and navPrice.

    See https://github.com/cgt-calc/capital-gains-calculator/issues/801.
    """
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeTicker({"regularMarketPrice": 366.79, "navPrice": 366.74}),
    )
    price = _fetcher().get_current_market_price("VTI")
    assert price == Decimal("366.79") / Decimal("1.25")


def test_falls_back_to_nav_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some tickers only carry navPrice, with no currentPrice or regularMarketPrice."""
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeTicker({"navPrice": 42.5}),
    )
    price = _fetcher().get_current_market_price("BND")
    assert price == Decimal("42.5") / Decimal("1.25")


def test_returns_none_when_no_price_field_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No known price field means the price is genuinely unavailable."""
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeTicker({"someOtherField": 1}),
    )
    assert _fetcher().get_current_market_price("XYZ") is None


def test_returns_none_when_ticker_info_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty info dict (e.g. an unknown symbol) yields no price."""
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeTicker({}),
    )
    assert _fetcher().get_current_market_price("UNKNOWN") is None


def test_gbp_pence_quoted_ticker_is_divided_by_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LSE-listed tickers are quoted in pence ("GBp"), not pounds or USD.

    yfinance's "GBp" is not a real ISO currency code, so it must be
    converted directly to GBP rather than looked up via CurrencyConverter.
    """
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeTicker({"currentPrice": 100.0, "currency": "GBp"}),
    )
    price = _fetcher().get_current_market_price("VOD.L")
    assert price == Decimal("1.0")


def test_eur_quoted_ticker_uses_eur_rate_not_usd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A EUR-quoted ticker should be converted using the EUR rate, not USD."""
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeTicker({"currentPrice": 100.0, "currency": "EUR"}),
    )
    price = _fetcher().get_current_market_price("MC.PA")
    assert price == Decimal("100.0") / Decimal("1.15")


def test_defaults_to_usd_when_currency_field_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When "currency" is missing from ticker info, fall back to USD."""
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeTicker({"currentPrice": 100.0}),
    )
    price = _fetcher().get_current_market_price("AAPL")
    assert price == Decimal("100.0") / Decimal("1.25")


class FakeEmptyHistoryTicker:
    """Stand-in for yf.Ticker with no historical data."""

    def history(self, **kwargs: str) -> pd.DataFrame:
        """Return an empty price history."""
        return pd.DataFrame()


def test_raises_clear_error_when_no_market_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty price history raises an error naming the symbol and date."""
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeEmptyHistoryTicker(),
    )
    with pytest.raises(MarketDataMissingError, match=r"FOO.*2021-05-10"):
        _fetcher().get_closing_price("FOO", datetime.date(2021, 5, 10))


class FakeHistoryTicker:
    """Stand-in for yf.Ticker with a single day of price history."""

    def __init__(self, close: float, currency: str) -> None:
        """Store the closing price and quote currency to return."""
        self._close = close
        self.info = {"currency": currency}
        self.splits = pd.Series(dtype=float)

    def history(self, **kwargs: str) -> pd.DataFrame:
        """Return a single-row price history."""
        return pd.DataFrame({"Close": [self._close]})


def test_closing_price_converted_at_historical_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Historical closing prices are converted at their own date's rate.

    Seeding today's rate with a different value pins the regression where
    the conversion silently used today's rate instead of the historical one.
    """
    historical_date = datetime.date(2021, 5, 10)
    today = datetime.datetime.now().date()
    converter = CurrencyConverter(
        None,
        {
            historical_date: {CurrencyCode("USD"): Decimal("1.25")},
            today: {CurrencyCode("USD"): Decimal(2)},
        },
    )
    fetcher = CurrentPriceFetcher(converter)
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeHistoryTicker(100.0, "USD"),
    )

    price = fetcher.get_closing_price("AAPL", historical_date)

    assert price == Decimal(100) / Decimal("1.25")


class FakeSplitTicker:
    """Stand-in for yf.Ticker carrying a price history and a split history."""

    def __init__(self, close: float, splits: dict[str, float]) -> None:
        """Store the closing price and the splits to report."""
        self._close = close
        self.info = {"currency": "USD"}
        self.last_history_kwargs: dict[str, object] = {}
        self.splits = pd.Series(
            list(splits.values()),
            index=pd.to_datetime(list(splits.keys())),
        )

    def history(self, **kwargs: object) -> pd.DataFrame:
        """Return a single-row price history, recording how it was asked for."""
        self.last_history_kwargs = kwargs
        return pd.DataFrame({"Close": [self._close]})


def _historical_fetcher(date: datetime.date) -> CurrentPriceFetcher:
    """Build a fetcher with a known USD rate on the given historical date."""
    return CurrentPriceFetcher(
        CurrencyConverter(None, {date: {CurrencyCode("USD"): Decimal("1.25")}})
    )


def test_closing_price_is_not_dividend_adjusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """History is requested unadjusted.

    yfinance defaults to auto_adjust=True, which restates past closes for
    every dividend paid since, so the same inputs stop producing the same
    answer as time passes.
    """
    ticker = FakeSplitTicker(100.0, {})
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker", lambda symbol: ticker
    )

    date = datetime.date(2021, 5, 10)
    _historical_fetcher(date).get_closing_price("AAPL", date)

    assert ticker.last_history_kwargs["auto_adjust"] is False


def test_closing_price_undoes_a_later_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A split after the valuation date is unwound from the price.

    yfinance restates history in today's share units regardless of
    auto_adjust, so a 25-for-1 split leaves the earlier close divided by 25.
    Callers pair this price with a holding counted in the units of the day.
    """
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeSplitTicker(100.0, {"2021-06-01": 25.0}),
    )

    date = datetime.date(2021, 5, 10)
    price = _historical_fetcher(date).get_closing_price("AAPL", date)

    assert price == Decimal(100) * Decimal(25) / Decimal("1.25")


def test_closing_price_ignores_earlier_splits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A split before the valuation date is already in the quoted price."""
    monkeypatch.setattr(
        "cgt_calc.current_price_fetcher.yf.Ticker",
        lambda symbol: FakeSplitTicker(100.0, {"2021-01-01": 25.0}),
    )

    date = datetime.date(2021, 5, 10)
    price = _historical_fetcher(date).get_closing_price("AAPL", date)

    assert price == Decimal(100) / Decimal("1.25")
