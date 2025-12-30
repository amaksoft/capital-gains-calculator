"""Initial stock prices."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import datetime
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Final

from cgt_calc.const import INITIAL_PRICES_RESOURCE
from cgt_calc.dates import is_date
from cgt_calc.exceptions import ExchangeRateMissingError, UnexpectedColumnCountError
from cgt_calc.resources import RESOURCES_PACKAGE

INITIAL_PRICES_COLUMNS_NUM: Final = 3


@dataclass
class InitialPricesEntry:
    """Entry from initial stock prices file."""

    date: datetime.date
    symbol: str
    price: Decimal

    def __init__(self, row: list[str], file: Path):
        """Create entry from CSV row."""
        if len(row) != INITIAL_PRICES_COLUMNS_NUM:
            raise UnexpectedColumnCountError(row, INITIAL_PRICES_COLUMNS_NUM, file)
        # date,symbol,price
        self.date = self._parse_date(row[0])
        self.symbol = row[1]
        self.price = Decimal(row[2])

    @staticmethod
    def _parse_date(date_str: str) -> datetime.date:
        """Parse date from string."""
        return datetime.datetime.strptime(date_str, "%b %d, %Y").date()

    def __str__(self) -> str:
        """Return string representation."""
        return f"date: {self.date}, symbol: {self.symbol}, price: {self.price}"


class InitialPrices:
    """Class to store initial stock prices.

    Supports an optional currency header comment in the CSV file:
    # Currency: USD

    If not specified, currency defaults to None (caller should decide default).
    """

    def __init__(self, initial_prices_file: Path | None = None) -> None:
        """Load data from an optional initial prices file or package resources."""
        self.initial_prices_file = initial_prices_file
        self.currency: str | None = None
        self.initial_prices = self._read_initial_prices()

    def get(self, date: datetime.date, symbol: str) -> Decimal:
        """Get initial stock price at given date."""
        assert is_date(date)
        if date not in self.initial_prices or symbol not in self.initial_prices[date]:
            raise ExchangeRateMissingError(symbol, date)
        return self.initial_prices[date][symbol]

    def _read_initial_prices(self) -> dict[datetime.date, dict[str, Decimal]]:
        """Read initial stock prices from CSV file.

        Also parses optional currency header comment: # Currency: USD
        """
        initial_prices: dict[datetime.date, dict[str, Decimal]] = {}
        if self.initial_prices_file is None:
            with (
                resources.files(RESOURCES_PACKAGE)
                .joinpath(INITIAL_PRICES_RESOURCE)
                .open(encoding="utf-8") as csv_file
            ):
                raw_lines = csv_file.readlines()
        else:
            with self.initial_prices_file.open(encoding="utf-8") as csv_file:
                raw_lines = csv_file.readlines()

        # Parse currency from comment header (if present)
        data_start_index = 0
        for i, line in enumerate(raw_lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                # Check for currency header: # Currency: USD
                if stripped.startswith("# Currency:"):
                    currency_value = stripped[len("# Currency:") :].strip()
                    if currency_value:
                        self.currency = currency_value
                # Skip comment lines
                continue
            # Found first non-comment line (should be CSV header)
            data_start_index = i
            break

        # Parse CSV data (skip header row)
        lines = list(csv.reader(raw_lines[data_start_index:]))
        if lines:
            lines = lines[1:]  # Skip header row

        for row in lines:
            if not row or all(not cell.strip() for cell in row):
                continue  # Skip empty rows
            entry = InitialPricesEntry(
                row,
                self.initial_prices_file or Path("resources") / INITIAL_PRICES_RESOURCE,
            )
            date_index = entry.date
            if date_index not in initial_prices:
                initial_prices[date_index] = {}
            initial_prices[date_index][entry.symbol] = entry.price
        return initial_prices
