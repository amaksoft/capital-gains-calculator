"""Test Schwab Reverse Split (share consolidation) handling.

Schwab books a share consolidation as two rows on the same date: one removing
the old units and one adding the new, smaller number. The parser collapses them
into a single net transaction, and the calculator cancels the units without
touching the pool cost, since a consolidation is a reorganisation rather than a
disposal.

Real Schwab exports are newest-first, so the CSVs below follow that ordering.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from cgt_calc.exceptions import ParsingError
from cgt_calc.model import ActionType
from cgt_calc.parsers.schwab import SchwabParser


class TestReverseSplitParsing:
    """Test that the two Reverse Split rows are combined into one."""

    def test_reverse_split_rows_are_combined(self, tmp_path: Path) -> None:
        """Two Reverse Split rows become a single net transaction."""
        csv_file = tmp_path / "transactions.csv"
        csv_file.write_text(
            "Date,Action,Symbol,Description,Price,Quantity,Fees & Comm,Amount\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,80,,\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,-100.5,,\n"
        )

        transactions = SchwabParser().load_from_file(csv_file)

        assert len(transactions) == 1
        assert transactions[0].action == ActionType.STOCK_SPLIT
        assert transactions[0].symbol == "FOO"
        assert transactions[0].quantity == Decimal("-20.5")

    def test_reverse_splits_of_different_symbols_stay_separate(
        self, tmp_path: Path
    ) -> None:
        """Rows for different securities are not combined."""
        csv_file = tmp_path / "transactions.csv"
        csv_file.write_text(
            "Date,Action,Symbol,Description,Price,Quantity,Fees & Comm,Amount\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,80,,\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,-100.5,,\n"
            "06/12/2024,Reverse Split,BAR,BAR CORP,,10,,\n"
            "06/12/2024,Reverse Split,BAR,BAR CORP,,-50,,\n"
        )

        transactions = SchwabParser().load_from_file(csv_file)

        assert len(transactions) == 2
        assert {txn.symbol for txn in transactions} == {"FOO", "BAR"}

    def test_reverse_split_legs_on_different_dates_are_rejected(
        self, tmp_path: Path
    ) -> None:
        """A consolidation whose legs fall on different dates is rejected.

        Each date then nets one-sided. The replacement leg alone nets positive
        and would otherwise be booked as a free zero-cost acquisition, silently
        inflating the holding.
        """
        csv_file = tmp_path / "transactions.csv"
        csv_file.write_text(
            "Date,Action,Symbol,Description,Price,Quantity,Fees & Comm,Amount\n"
            "06/13/2024,Reverse Split,FOO,FOO CORP,,80,,\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,-100.5,,\n"
        )

        with pytest.raises(ParsingError, match="rows removing the old units"):
            SchwabParser().load_from_file(csv_file)

    def test_replacement_leg_alone_is_rejected(self, tmp_path: Path) -> None:
        """A lone positive Reverse Split row never becomes free units."""
        csv_file = tmp_path / "transactions.csv"
        csv_file.write_text(
            "Date,Action,Symbol,Description,Price,Quantity,Fees & Comm,Amount\n"
            "06/13/2024,Reverse Split,FOO,FOO CORP,,80,,\n"
        )

        with pytest.raises(ParsingError, match="must reduce the holding"):
            SchwabParser().load_from_file(csv_file)

    def test_reverse_split_without_quantity_is_rejected(self, tmp_path: Path) -> None:
        """A Reverse Split row missing its quantity is a parsing error."""
        csv_file = tmp_path / "transactions.csv"
        csv_file.write_text(
            "Date,Action,Symbol,Description,Price,Quantity,Fees & Comm,Amount\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,,,\n"
        )

        with pytest.raises(ParsingError, match="without a quantity"):
            SchwabParser().load_from_file(csv_file)

    def test_reverse_split_netting_to_zero_is_rejected(self, tmp_path: Path) -> None:
        """A Reverse Split that changes nothing is a parsing error."""
        csv_file = tmp_path / "transactions.csv"
        csv_file.write_text(
            "Date,Action,Symbol,Description,Price,Quantity,Fees & Comm,Amount\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,80,,\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,-80,,\n"
        )

        with pytest.raises(ParsingError, match="must reduce the holding"):
            SchwabParser().load_from_file(csv_file)

    def test_interleaved_reverse_splits_are_grouped_by_symbol(
        self, tmp_path: Path
    ) -> None:
        """Rows of one consolidation are combined even when interleaved.

        Two securities can consolidate on the same date, and the export need
        not keep each one's rows adjacent. Grouping only adjacent rows would
        leave one consolidation split in two: a standalone row cancelling more
        units than are held, and a bogus free acquisition.
        """
        csv_file = tmp_path / "transactions.csv"
        csv_file.write_text(
            "Date,Action,Symbol,Description,Price,Quantity,Fees & Comm,Amount\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,80,,\n"
            "06/12/2024,Reverse Split,BAR,BAR CORP,,-50,,\n"
            "06/12/2024,Reverse Split,FOO,FOO CORP,,-100.5,,\n"
            "06/12/2024,Reverse Split,BAR,BAR CORP,,40,,\n"
        )

        transactions = SchwabParser().load_from_file(csv_file)

        by_symbol = {txn.symbol: txn.quantity for txn in transactions}
        assert by_symbol == {
            "FOO": Decimal("-20.5"),
            "BAR": Decimal(-10),
        }
