"""Test Schwab Reinvestment Adj filtering.

Schwab reverses a dividend reinvestment booked at the wrong price with a
"Reinvestment Adj" row, then re-books it. The adjustment carries the same
symbol, quantity and price as the reinvestment it reverses, with the sign of
the amount flipped, so the pair cancels out and only the corrected
reinvestment should survive.

The shape a real export uses:

    03/11  Reinvest Shares   FOO  0.5000 @ $40.0000  -$20.00
    03/14  Reinvestment Adj  FOO  0.5000 @ $40.0000  +$20.00
    03/14  Reinvest Shares   FOO  0.4000 @ $50.0000  -$20.00

Files are newest-first, as real Schwab exports are.
"""

from collections import OrderedDict
import csv
from pathlib import Path

import pytest

from cgt_calc.exceptions import ParsingError
from cgt_calc.model import ActionType
from cgt_calc.parsers.schwab import AwardPrices, SchwabParser, SchwabTransaction

HEADER = "Date,Action,Symbol,Description,Price,Quantity,Fees & Comm,Amount\n"


def test_reinvestment_adj_removes_both_rows(tmp_path: Path) -> None:
    """The adjustment and the reinvestment it reverses both disappear."""
    csv_file = tmp_path / "transactions.csv"
    csv_file.write_text(
        HEADER
        + "03/14/2024,Reinvestment Adj,FOO,FOO CORP,$40.00,0.5,$0.00,$20.00\n"
        + "03/11/2024,Reinvest Shares,FOO,FOO CORP,$40.00,0.5,$0.00,-$20.00\n"
    )

    assert SchwabParser().load_from_file(csv_file) == []


def test_corrected_reinvestment_survives(tmp_path: Path) -> None:
    """Only the re-booked reinvestment is left, at its own price."""
    csv_file = tmp_path / "transactions.csv"
    csv_file.write_text(
        HEADER
        + "03/14/2024,Reinvest Shares,FOO,FOO CORP,$50.00,0.4,$0.00,-$20.00\n"
        + "03/14/2024,Reinvestment Adj,FOO,FOO CORP,$40.00,0.5,$0.00,$20.00\n"
        + "03/11/2024,Reinvest Shares,FOO,FOO CORP,$40.00,0.5,$0.00,-$20.00\n"
    )

    transactions = SchwabParser().load_from_file(csv_file)

    assert len(transactions) == 1
    assert transactions[0].action is ActionType.REINVEST_SHARES
    assert str(transactions[0].price) == "50.00"


def test_adjustment_does_not_claim_a_buy(tmp_path: Path) -> None:
    """A Reinvestment Adj reverses a reinvestment, never a purchase."""
    csv_file = tmp_path / "transactions.csv"
    csv_file.write_text(
        HEADER
        + "03/14/2024,Reinvestment Adj,FOO,FOO CORP,$40.00,0.5,$0.00,$20.00\n"
        + "03/11/2024,Buy,FOO,FOO CORP,$40.00,0.5,$0.00,-$20.00\n"
    )

    with pytest.raises(ParsingError, match="no Reinvest Shares to match it"):
        SchwabParser().load_from_file(csv_file)


def test_cancel_buy_does_not_claim_a_reinvestment(tmp_path: Path) -> None:
    """The reverse pairing is refused too."""
    csv_file = tmp_path / "transactions.csv"
    csv_file.write_text(
        HEADER
        + "03/14/2024,Cancel Buy,FOO,FOO CORP,$40.00,0.5,$0.00,$20.00\n"
        + "03/11/2024,Reinvest Shares,FOO,FOO CORP,$40.00,0.5,$0.00,-$20.00\n"
    )

    with pytest.raises(ParsingError, match="no Buy to match it"):
        SchwabParser().load_from_file(csv_file)


def test_unmatched_adjustment_is_refused(tmp_path: Path) -> None:
    """An adjustment with nothing to reverse stops the run."""
    csv_file = tmp_path / "transactions.csv"
    csv_file.write_text(
        HEADER + "03/14/2024,Reinvestment Adj,FOO,FOO CORP,$40.00,0.5,$0.00,$20.00\n"
    )

    with pytest.raises(ParsingError, match="no Reinvest Shares to match it"):
        SchwabParser().load_from_file(csv_file)


def test_adjustment_is_typed_as_a_cancellation(tmp_path: Path) -> None:
    """The row does not carry the action type of a reinvestment."""
    csv_file = tmp_path / "transactions.csv"
    csv_file.write_text(
        HEADER
        + "03/14/2024,Reinvestment Adj,FOO,FOO CORP,$40.00,0.5,$0.00,$20.00\n"
        + "03/11/2024,Reinvest Shares,FOO,FOO CORP,$40.00,0.5,$0.00,-$20.00\n"
    )

    # Reach past the filter to see how the row itself is typed.
    with csv_file.open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    adjustment = SchwabTransaction.create(
        OrderedDict(zip(header, rows[1], strict=True)), csv_file, AwardPrices({})
    )

    assert adjustment.raw_action == "Reinvestment Adj"
    assert adjustment.action is ActionType.CANCELLATION
