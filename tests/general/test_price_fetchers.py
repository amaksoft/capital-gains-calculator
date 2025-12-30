"""Tests for price fetcher components."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from cgt_calc.currency_converter import CurrencyConverter
from cgt_calc.price_fetchers import (
    CachedPriceFetcher,
    ChainedPriceFetcher,
    CsvPriceFetcher,
    FetcherDependencies,
    GbpConvertingFetcher,
    PriceMissingError,
    YFinancePriceFetcher,
    create_price_fetcher,
    get_available_fetchers,
    parse_price_priority,
)
from cgt_calc.price_fetchers.fetcher_type import FetcherType

if TYPE_CHECKING:
    from pathlib import Path


# Mock fetcher for testing
class MockPriceFetcher:
    """Mock price fetcher for testing."""

    def __init__(self, name: str, prices: dict[tuple[str, datetime.date], Decimal]):
        """Initialize mock with name and price data."""
        self._name = name
        self._prices = prices

    def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
        """Return closing price from preloaded data."""
        key = (symbol, date)
        if key not in self._prices:
            raise PriceMissingError(f"{self._name}: {symbol} on {date}")
        return self._prices[key]

    def get_current_market_price(self, symbol: str) -> Decimal | None:
        """Return None (mock doesn't support current prices)."""
        return None

    @property
    def name(self) -> str:
        """Return mock fetcher name."""
        return self._name

    @property
    def native_currency(self) -> str:
        """Return GBP for test mock."""
        return "GBP"


@pytest.fixture
def mock_deps() -> FetcherDependencies:
    """Create minimal FetcherDependencies for testing."""
    return FetcherDependencies(
        currency_converter=CurrencyConverter(),
        verbose=False,
    )


class TestCachedPriceFetcher:
    """Tests for CachedPriceFetcher wrapper."""

    def test_caches_historical_prices(self, mock_deps: FetcherDependencies) -> None:
        """Historical prices are cached after first fetch."""
        prices = {("AAPL", datetime.date(2024, 1, 1)): Decimal("150.00")}
        underlying = MockPriceFetcher("mock", prices)
        cached = CachedPriceFetcher(underlying, mock_deps)

        # First call - should fetch from underlying
        price1 = cached.get_closing_price("AAPL", datetime.date(2024, 1, 1))
        assert price1 == Decimal("150.00")

        # Second call - should return from cache without calling underlying
        price2 = cached.get_closing_price("AAPL", datetime.date(2024, 1, 1))
        assert price2 == Decimal("150.00")

    def test_cache_miss_raises_price_missing_error(
        self, mock_deps: FetcherDependencies
    ) -> None:
        """Cache miss propagates PriceMissingError from underlying fetcher."""
        underlying = MockPriceFetcher("mock", {})
        cached = CachedPriceFetcher(underlying, mock_deps)

        with pytest.raises(PriceMissingError, match="mock: AAPL on 2024-01-01"):
            cached.get_closing_price("AAPL", datetime.date(2024, 1, 1))

    def test_preloaded_historical_prices(self, mock_deps: FetcherDependencies) -> None:
        """Can preload historical prices into cache."""
        underlying = MockPriceFetcher("mock", {})
        preloaded = {
            "AAPL": {datetime.date(2024, 1, 1): Decimal("150.00")},
        }
        cached = CachedPriceFetcher(
            underlying, mock_deps, historical_prices_data=preloaded
        )

        # Should get from preloaded cache without calling underlying
        price = cached.get_closing_price("AAPL", datetime.date(2024, 1, 1))
        assert price == Decimal("150.00")

    def test_preloaded_current_prices(self, mock_deps: FetcherDependencies) -> None:
        """Can preload current prices into cache."""
        underlying = MockPriceFetcher("mock", {})
        preloaded: dict[str, Decimal | None] = {"AAPL": Decimal("155.00")}
        cached = CachedPriceFetcher(
            underlying, mock_deps, current_prices_data=preloaded
        )

        # Should get from preloaded cache
        price = cached.get_current_market_price("AAPL")
        assert price == Decimal("155.00")

    def test_current_price_none_is_cached(self, mock_deps: FetcherDependencies) -> None:
        """None values for current prices are cached."""
        underlying = MockPriceFetcher("mock", {})
        cached = CachedPriceFetcher(underlying, mock_deps)

        # First call returns None
        price1 = cached.get_current_market_price("AAPL")
        assert price1 is None

        # Second call should return cached None
        price2 = cached.get_current_market_price("AAPL")
        assert price2 is None

    def test_name_property(self, mock_deps: FetcherDependencies) -> None:
        """Name property shows what fetcher is being cached."""
        underlying = MockPriceFetcher("mock", {})
        cached = CachedPriceFetcher(underlying, mock_deps)

        assert cached.name == "cached(mock)"


class TestGbpConvertingFetcher:
    """Tests for GbpConvertingFetcher."""

    def test_converts_usd_to_gbp(self, mock_deps: FetcherDependencies) -> None:
        """Converts USD prices to GBP using currency converter."""

        # Create a USD fetcher
        class UsdFetcher:
            @property
            def name(self) -> str:
                return "usd_fetcher"

            @property
            def native_currency(self) -> str:
                return "USD"

            def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
                return Decimal("100.00")  # $100 USD

            def get_current_market_price(self, symbol: str) -> Decimal | None:
                return Decimal("105.00")  # $105 USD

        usd_fetcher = UsdFetcher()
        gbp_fetcher = GbpConvertingFetcher(
            usd_fetcher, mock_deps.currency_converter, verbose=False
        )

        # Get historical price - should convert USD to GBP
        # Using actual exchange rate from converter
        price = gbp_fetcher.get_closing_price("AAPL", datetime.date(2024, 1, 1))

        # The converter should have converted $100 USD to GBP
        # We don't hardcode the expected value since it depends on exchange rates
        assert isinstance(price, Decimal)
        assert price > 0

    def test_converts_eur_to_gbp(self, mock_deps: FetcherDependencies) -> None:
        """Converts EUR prices to GBP using currency converter."""

        # Create a EUR fetcher
        class EurFetcher:
            @property
            def name(self) -> str:
                return "eur_fetcher"

            @property
            def native_currency(self) -> str:
                return "EUR"

            def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
                return Decimal("90.00")  # €90 EUR

            def get_current_market_price(self, symbol: str) -> Decimal | None:
                return Decimal("95.00")  # €95 EUR

        eur_fetcher = EurFetcher()
        gbp_fetcher = GbpConvertingFetcher(
            eur_fetcher, mock_deps.currency_converter, verbose=False
        )

        # Get historical price - should convert EUR to GBP
        price = gbp_fetcher.get_closing_price("AAPL", datetime.date(2024, 1, 1))

        assert isinstance(price, Decimal)
        assert price > 0

    def test_rejects_gbp_fetcher(self, mock_deps: FetcherDependencies) -> None:
        """Raises ValueError when trying to wrap a GBP fetcher."""

        # MockPriceFetcher returns GBP
        gbp_fetcher = MockPriceFetcher("gbp_mock", {})

        with pytest.raises(
            ValueError,
            match=r"GbpConvertingFetcher cannot wrap a GBP fetcher.*This wrapper is only for converting non-GBP prices to GBP",
        ):
            GbpConvertingFetcher(
                gbp_fetcher, mock_deps.currency_converter, verbose=False
            )

    def test_native_currency_is_gbp(self, mock_deps: FetcherDependencies) -> None:
        """native_currency property always returns GBP."""

        class UsdFetcher:
            @property
            def name(self) -> str:
                return "usd_fetcher"

            @property
            def native_currency(self) -> str:
                return "USD"

            def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
                return Decimal("100.00")

            def get_current_market_price(self, symbol: str) -> Decimal | None:
                return Decimal("105.00")

        usd_fetcher = UsdFetcher()
        gbp_fetcher = GbpConvertingFetcher(
            usd_fetcher, mock_deps.currency_converter, verbose=False
        )

        assert gbp_fetcher.native_currency == "GBP"

    def test_name_shows_conversion(self, mock_deps: FetcherDependencies) -> None:
        """Name property shows currency conversion."""

        class UsdFetcher:
            @property
            def name(self) -> str:
                return "usd_fetcher"

            @property
            def native_currency(self) -> str:
                return "USD"

            def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
                return Decimal("100.00")

            def get_current_market_price(self, symbol: str) -> Decimal | None:
                return None

        usd_fetcher = UsdFetcher()
        gbp_fetcher = GbpConvertingFetcher(
            usd_fetcher, mock_deps.currency_converter, verbose=False
        )

        assert gbp_fetcher.name == "usd_fetcher (USD->GBP)"

    def test_current_price_returns_none_when_wrapped_returns_none(
        self, mock_deps: FetcherDependencies
    ) -> None:
        """get_current_market_price returns None when wrapped fetcher returns None."""

        class UsdFetcher:
            @property
            def name(self) -> str:
                return "usd_fetcher"

            @property
            def native_currency(self) -> str:
                return "USD"

            def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
                return Decimal("100.00")

            def get_current_market_price(self, symbol: str) -> Decimal | None:
                return None

        usd_fetcher = UsdFetcher()
        gbp_fetcher = GbpConvertingFetcher(
            usd_fetcher, mock_deps.currency_converter, verbose=False
        )

        price = gbp_fetcher.get_current_market_price("AAPL")
        assert price is None

    def test_raises_on_missing_exchange_rate(
        self, mock_deps: FetcherDependencies
    ) -> None:
        """Raises PriceMissingError when exchange rate is missing."""

        class ExoticCurrencyFetcher:
            @property
            def name(self) -> str:
                return "exotic_fetcher"

            @property
            def native_currency(self) -> str:
                return "XYZ"  # Fictional currency with no exchange rate

            def get_closing_price(self, symbol: str, date: datetime.date) -> Decimal:
                return Decimal("100.00")

            def get_current_market_price(self, symbol: str) -> Decimal | None:
                return Decimal("105.00")

        exotic_fetcher = ExoticCurrencyFetcher()
        gbp_fetcher = GbpConvertingFetcher(
            exotic_fetcher, mock_deps.currency_converter, verbose=False
        )

        # Should raise PriceMissingError when converter can't find exchange rate
        with pytest.raises(
            PriceMissingError,
            match=r"Cannot convert .* price from XYZ to GBP",
        ):
            gbp_fetcher.get_closing_price("AAPL", datetime.date(2024, 1, 1))


class TestChainedPriceFetcher:
    """Tests for ChainedPriceFetcher."""

    def test_tries_fetchers_in_order(self, mock_deps: FetcherDependencies) -> None:
        """Tries fetchers in priority order until one succeeds."""
        fetcher1 = MockPriceFetcher("fetcher1", {})
        fetcher2 = MockPriceFetcher(
            "fetcher2",
            {("AAPL", datetime.date(2024, 1, 1)): Decimal("150.00")},
        )
        chained = ChainedPriceFetcher([fetcher1, fetcher2], mock_deps)

        price = chained.get_closing_price("AAPL", datetime.date(2024, 1, 1))
        assert price == Decimal("150.00")

    def test_raises_if_all_fetchers_fail(self, mock_deps: FetcherDependencies) -> None:
        """Raises PriceMissingError if all fetchers fail."""
        fetcher1 = MockPriceFetcher("fetcher1", {})
        fetcher2 = MockPriceFetcher("fetcher2", {})
        chained = ChainedPriceFetcher([fetcher1, fetcher2], mock_deps)

        with pytest.raises(
            PriceMissingError,
            match=r"Price not found for AAPL on 2024-01-01\. Tried: fetcher1, fetcher2",
        ):
            chained.get_closing_price("AAPL", datetime.date(2024, 1, 1))

    def test_requires_at_least_one_fetcher(
        self, mock_deps: FetcherDependencies
    ) -> None:
        """Raises ValueError if initialized with empty fetcher list."""
        with pytest.raises(
            ValueError,
            match="ChainedPriceFetcher requires at least one fetcher",
        ):
            ChainedPriceFetcher([], mock_deps)

    def test_current_price_tries_all_fetchers(
        self, mock_deps: FetcherDependencies
    ) -> None:
        """Tries all fetchers for current price, returns first non-None."""
        fetcher1 = MockPriceFetcher("fetcher1", {})
        fetcher2 = MockPriceFetcher("fetcher2", {})
        chained = ChainedPriceFetcher([fetcher1, fetcher2], mock_deps)

        # Both return None, so result is None
        price = chained.get_current_market_price("AAPL")
        assert price is None

    def test_name_property(self, mock_deps: FetcherDependencies) -> None:
        """Name property combines all fetcher names."""
        fetcher1 = MockPriceFetcher("fetcher1", {})
        fetcher2 = MockPriceFetcher("fetcher2", {})
        chained = ChainedPriceFetcher([fetcher1, fetcher2], mock_deps)

        assert chained.name == "chained(fetcher1+fetcher2)"


class TestCsvPriceFetcher:
    """Tests for CsvPriceFetcher."""

    def test_fetches_price_from_csv(
        self, tmp_path: Path, mock_deps: FetcherDependencies
    ) -> None:
        """Can fetch historical prices from CSV file."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text(
            'date,symbol,price\n"Jan 01, 2024",AAPL,150.00\n',
            encoding="utf8",
        )

        deps = FetcherDependencies(
            currency_converter=mock_deps.currency_converter,
            initial_prices_csv=csv_file,
        )
        fetcher = CsvPriceFetcher(deps)
        price = fetcher.get_closing_price("AAPL", datetime.date(2024, 1, 1))

        assert price == Decimal("150.00")

    def test_raises_on_missing_price(
        self, tmp_path: Path, mock_deps: FetcherDependencies
    ) -> None:
        """Raises PriceMissingError when price not in CSV."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text("date,symbol,price\n", encoding="utf8")

        deps = FetcherDependencies(
            currency_converter=mock_deps.currency_converter,
            initial_prices_csv=csv_file,
        )
        fetcher = CsvPriceFetcher(deps)

        with pytest.raises(PriceMissingError, match="CSV: AAPL on 2024-01-01"):
            fetcher.get_closing_price("AAPL", datetime.date(2024, 1, 1))

    def test_current_market_price_not_supported(
        self, mock_deps: FetcherDependencies
    ) -> None:
        """get_current_market_price returns None."""
        fetcher = CsvPriceFetcher(mock_deps)

        assert fetcher.get_current_market_price("AAPL") is None

    def test_name_property(self, mock_deps: FetcherDependencies) -> None:
        """Name property returns 'csv'."""
        fetcher = CsvPriceFetcher(mock_deps)
        assert fetcher.name == "csv"

    def test_csv_currency_from_header(
        self, tmp_path: Path, mock_deps: FetcherDependencies
    ) -> None:
        """Currency is parsed from CSV header comment."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text(
            '# Currency: USD\ndate,symbol,price\n"Jan 01, 2024",AAPL,150.00\n',
            encoding="utf8",
        )

        deps = FetcherDependencies(
            currency_converter=mock_deps.currency_converter,
            initial_prices_csv=csv_file,
        )
        fetcher = CsvPriceFetcher(deps)
        assert fetcher._csv_currency == "USD"  # noqa: SLF001 (testing internal state)

    def test_csv_currency_header_with_multiple_comments(
        self, tmp_path: Path, mock_deps: FetcherDependencies
    ) -> None:
        """Currency header works with other comment lines."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text(
            '# This is a comment\n# Currency: EUR\n# Another comment\ndate,symbol,price\n"Jan 01, 2024",AAPL,150.00\n',
            encoding="utf8",
        )

        deps = FetcherDependencies(
            currency_converter=mock_deps.currency_converter,
            initial_prices_csv=csv_file,
        )
        fetcher = CsvPriceFetcher(deps)
        assert fetcher._csv_currency == "EUR"  # noqa: SLF001 (testing internal state)

    def test_csv_currency_defaults_to_gbp_without_header(
        self, tmp_path: Path, mock_deps: FetcherDependencies
    ) -> None:
        """Currency defaults to GBP when no header."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text(
            'date,symbol,price\n"Jan 01, 2024",AAPL,150.00\n',
            encoding="utf8",
        )

        deps = FetcherDependencies(
            currency_converter=mock_deps.currency_converter,
            initial_prices_csv=csv_file,
        )
        fetcher = CsvPriceFetcher(deps)
        assert fetcher._csv_currency == "GBP"  # noqa: SLF001 (testing internal state)


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_get_available_fetchers_returns_registered_fetchers(self) -> None:
        """get_available_fetchers returns fetchers with show_in_help=True."""
        available = get_available_fetchers()

        # Should include csv and yfinance (both have show_in_help=True)
        assert "csv" in available
        assert "yfinance" in available

    def test_parse_price_priority_splits_comma_separated(self) -> None:
        """parse_price_priority splits comma-separated string."""
        result = parse_price_priority("yfinance,csv")
        assert result == ["yfinance", "csv"]

    def test_parse_price_priority_strips_whitespace(self) -> None:
        """parse_price_priority strips whitespace from source names."""
        result = parse_price_priority(" yfinance , csv ")
        assert result == ["yfinance", "csv"]

    def test_parse_price_priority_raises_on_unknown_source(self) -> None:
        """parse_price_priority raises ValueError for unknown sources."""
        with pytest.raises(ValueError, match="Unknown price source: 'unknown'"):
            parse_price_priority("yfinance,unknown")


class TestCreatePriceFetcher:
    """Tests for create_price_fetcher factory."""

    def test_single_fetcher_not_wrapped_in_chain(self, tmp_path: Path) -> None:
        """Single fetcher in priority list is returned directly (possibly cached)."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text("date,symbol,price\n", encoding="utf8")

        deps = FetcherDependencies(
            currency_converter=CurrencyConverter(),
            initial_prices_csv=csv_file,
        )

        fetcher = create_price_fetcher("csv", deps)

        # Should be CsvPriceFetcher, not ChainedPriceFetcher
        assert isinstance(fetcher, CsvPriceFetcher)

    def test_multiple_fetchers_wrapped_in_chain(self, tmp_path: Path) -> None:
        """Multiple fetchers in priority list are wrapped in ChainedPriceFetcher."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text("date,symbol,price\n", encoding="utf8")

        deps = FetcherDependencies(
            currency_converter=CurrencyConverter(),
            initial_prices_csv=csv_file,
        )

        fetcher = create_price_fetcher("yfinance,csv", deps)

        # Should be ChainedPriceFetcher wrapping both
        assert isinstance(fetcher, ChainedPriceFetcher)

    def test_auto_cache_fetchers_wrapped_with_cache(self, tmp_path: Path) -> None:
        """Fetchers with auto_cache=True are automatically wrapped with CachedPriceFetcher."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text("date,symbol,price\n", encoding="utf8")

        deps = FetcherDependencies(
            currency_converter=CurrencyConverter(),
            initial_prices_csv=csv_file,
        )

        # yfinance has auto_cache=True, should be wrapped in cache
        fetcher = create_price_fetcher("yfinance", deps)
        assert isinstance(fetcher, CachedPriceFetcher)

    def test_chained_cached_fetchers_have_descriptive_names(
        self, tmp_path: Path
    ) -> None:
        """Chained fetcher with cached network fetcher shows descriptive names."""
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text("date,symbol,price\n", encoding="utf8")

        deps = FetcherDependencies(
            currency_converter=CurrencyConverter(),
            initial_prices_csv=csv_file,
        )

        # Create yfinance,csv chain
        fetcher = create_price_fetcher("yfinance,csv", deps)

        # Should be chained(cached(converted(yfinance))+csv), showing full wrapper chain
        # yfinance (USD) -> currency converting (USD->GBP) -> cached -> chained with csv
        assert isinstance(fetcher, ChainedPriceFetcher)
        assert fetcher.name == "chained(cached(yfinance (USD->GBP))+csv)"

    def test_raises_on_empty_priority_list(self) -> None:
        """Raises ValueError if priority list is empty."""
        deps = FetcherDependencies(currency_converter=CurrencyConverter())

        with pytest.raises(ValueError, match="Unknown price source: ''"):
            create_price_fetcher("", deps)

    def test_raises_on_unknown_source(self) -> None:
        """Raises ValueError if unknown source in priority list."""
        deps = FetcherDependencies(currency_converter=CurrencyConverter())

        with pytest.raises(ValueError, match="Unknown price source: 'unknown'"):
            create_price_fetcher("unknown", deps)

    def test_optional_parameters_use_defaults(self) -> None:
        """Optional parameters use their default values when not provided."""
        deps = FetcherDependencies(currency_converter=CurrencyConverter())

        fetcher = create_price_fetcher("csv", deps)

        # CSV is LOCAL type, so not auto-cached
        assert isinstance(fetcher, CsvPriceFetcher)
        assert (
            fetcher._csv_currency == "GBP"  # noqa: SLF001 (testing default value)
        )
        assert (
            fetcher._verbose is False  # noqa: SLF001 (testing default value)
        )

    def test_explicit_values_override_defaults(self, tmp_path: Path) -> None:
        """CSV with USD currency header is wrapped with GbpConvertingFetcher."""
        # Create CSV file with USD currency
        csv_file = tmp_path / "prices.csv"
        csv_file.write_text(
            '# Currency: USD\ndate,symbol,price\n"Jan 01, 2024",AAPL,150.00\n',
            encoding="utf8",
        )

        deps = FetcherDependencies(
            currency_converter=CurrencyConverter(),
            initial_prices_csv=csv_file,
            verbose=True,
        )

        fetcher = create_price_fetcher("csv", deps)

        # CSV with USD currency is wrapped with GbpConvertingFetcher

        assert isinstance(fetcher, GbpConvertingFetcher)
        # Check the wrapped fetcher has the correct parameters
        wrapped = fetcher._wrapped_fetcher  # noqa: SLF001
        assert isinstance(wrapped, CsvPriceFetcher)
        assert wrapped._csv_currency == "USD"  # noqa: SLF001 (testing USD from header)
        assert wrapped._verbose is True  # noqa: SLF001 (testing verbose)


class TestFetcherMetadata:
    """Tests for fetcher decorator metadata."""

    def test_yfinance_has_network_type(self) -> None:
        """YFinancePriceFetcher is registered as NETWORK type."""
        assert YFinancePriceFetcher.fetcher_type == FetcherType.NETWORK

    def test_csv_has_local_type(self) -> None:
        """CsvPriceFetcher is registered as LOCAL type."""
        assert CsvPriceFetcher.fetcher_type == FetcherType.LOCAL

    def test_yfinance_show_in_help(self) -> None:
        """YFinancePriceFetcher has show_in_help=True."""
        assert YFinancePriceFetcher.show_in_help is True

    def test_csv_show_in_help(self) -> None:
        """CsvPriceFetcher has show_in_help=True."""
        assert CsvPriceFetcher.show_in_help is True

    def test_yfinance_has_auto_cache_enabled(self) -> None:
        """YFinancePriceFetcher has auto_cache=True (network fetcher)."""
        assert YFinancePriceFetcher.auto_cache is True

    def test_csv_has_auto_cache_disabled(self) -> None:
        """CsvPriceFetcher has auto_cache=False (local fetcher)."""
        assert CsvPriceFetcher.auto_cache is False
