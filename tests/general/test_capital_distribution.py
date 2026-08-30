"""Tests for small capital distributions (cash in lieu).

Cash received on a reorganisation - most often in lieu of a fractional share
left over by a spin-off, split or consolidation - is strictly a part disposal.
Where the sum is small, HMRC allows it to be deducted from the allowable cost
instead, so no gain arises now and the receipt is picked up when the holding is
sold. Ref: TCGA 1992 s122, HMRC CG57835.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import logging
from typing import TYPE_CHECKING

from cgt_calc.model import ActionType, BrokerTransaction, CurrencyCode, RuleType

from .calc_test_data import GBP, transaction
from .test_calc import create_calculator, get_report

if TYPE_CHECKING:
    import pytest


def _buy(
    day: datetime.date, symbol: str, quantity: int, price: int
) -> BrokerTransaction:
    """Buy `quantity` units at `price`, settled in GBP."""
    return transaction(
        day,
        ActionType.BUY,
        symbol,
        quantity,
        price,
        0,
        -quantity * price,
        CurrencyCode(GBP),
    )


def _cash_in_lieu(
    day: datetime.date, symbol: str | None, amount: float
) -> BrokerTransaction:
    """Cash received in lieu of a fractional share."""
    return BrokerTransaction(
        day,
        ActionType.CAPITAL_DISTRIBUTION,
        symbol,
        "Cash in lieu of fractional share",
        quantity=None,
        price=None,
        fees=Decimal(0),
        amount=Decimal(str(amount)),
        currency=CurrencyCode(GBP),
        broker="Testing",
    )


def test_distribution_reduces_pool_cost_without_a_gain() -> None:
    """£10 received on a £100 holding leaves 10 units costing £90."""
    calculator = create_calculator(tax_year=2024, balance_check=False)

    report = get_report(
        calculator,
        [
            _buy(datetime.date(2024, 6, 1), "FOO", 10, 10),
            _cash_in_lieu(datetime.date(2024, 6, 10), "FOO", 10),
        ],
    )

    position = calculator.portfolio["FOO"]
    assert position.quantity == Decimal(10)
    assert position.amount == Decimal(90)
    assert report.total_gain() == Decimal(0)


def test_distribution_is_logged_with_its_own_rule_type() -> None:
    """The calculation log records the deduction against the holding."""
    distribution_day = datetime.date(2024, 6, 10)
    calculator = create_calculator(tax_year=2024, balance_check=False)

    report = get_report(
        calculator,
        [
            _buy(datetime.date(2024, 6, 1), "FOO", 10, 10),
            _cash_in_lieu(distribution_day, "FOO", 10),
        ],
    )

    entries = report.calculation_log[distribution_day]["distribution$FOO"]
    assert len(entries) == 1
    assert entries[0].rule_type is RuleType.CAPITAL_DISTRIBUTION
    assert entries[0].amount == Decimal(10)
    assert entries[0].allowable_cost == Decimal(10)
    assert entries[0].new_pool_cost == Decimal(90)


def test_distribution_applies_after_the_same_day_acquisitions() -> None:
    """Cash arriving on a purchase date is deducted from the combined pool."""
    day = datetime.date(2024, 6, 1)
    calculator = create_calculator(tax_year=2024, balance_check=False)

    get_report(
        calculator,
        [
            _buy(day, "FOO", 10, 10),
            _cash_in_lieu(day, "FOO", 20),
        ],
    )

    assert calculator.portfolio["FOO"].amount == Decimal(80)


def test_distribution_for_an_unheld_symbol_warns_and_stays_cash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing to deduct from, so the receipt is left as cash with a warning."""
    calculator = create_calculator(tax_year=2024, balance_check=False)

    with caplog.at_level(logging.WARNING):
        report = get_report(
            calculator,
            [_cash_in_lieu(datetime.date(2024, 6, 10), "FOO", 10)],
        )

    assert "not held at that date" in caplog.text
    # No phantom 0-unit line is left behind in the portfolio.
    assert "FOO" not in calculator.portfolio
    assert report.total_gain() == Decimal(0)


def test_distribution_without_a_symbol_is_booked_as_cash() -> None:
    """Schwab leaves the symbol blank on some rows; that must not abort a run."""
    calculator = create_calculator(tax_year=2024, balance_check=False)

    report = get_report(
        calculator,
        [
            _buy(datetime.date(2024, 6, 1), "FOO", 10, 10),
            _cash_in_lieu(datetime.date(2024, 6, 10), None, 10),
        ],
    )

    # The pool is untouched, because there is no way to know what it relates to.
    assert calculator.portfolio["FOO"].amount == Decimal(100)
    assert report.total_gain() == Decimal(0)


def test_distribution_exceeding_the_pool_cost_is_capped() -> None:
    """Deduction stops at nil; the excess is flagged, not silently negative."""
    calculator = create_calculator(tax_year=2024, balance_check=False)

    get_report(
        calculator,
        [
            _buy(datetime.date(2024, 6, 1), "FOO", 10, 1),
            _cash_in_lieu(datetime.date(2024, 6, 10), "FOO", 25),
        ],
    )

    assert calculator.portfolio["FOO"].amount == Decimal(0)


def test_later_disposal_uses_the_reduced_cost() -> None:
    """The deducted cash resurfaces as extra gain when the holding is sold."""
    calculator = create_calculator(tax_year=2024, balance_check=False)

    report = get_report(
        calculator,
        [
            _buy(datetime.date(2024, 6, 1), "FOO", 10, 10),
            _cash_in_lieu(datetime.date(2024, 6, 10), "FOO", 10),
            transaction(
                datetime.date(2024, 6, 20),
                ActionType.SELL,
                "FOO",
                10,
                10,
                0,
                100,
                CurrencyCode(GBP),
            ),
        ],
    )

    # Proceeds £100 against a pool cost reduced to £90.
    assert report.total_gain() == Decimal(10)
