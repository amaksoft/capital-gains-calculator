"""Tests for share consolidations (reverse splits).

A consolidation replaces a holding with fewer units of the same security. It
is a reorganisation, not a disposal, so units are cancelled while the pool
cost carries over untouched. Ref: TCGA 1992 s127.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from cgt_calc.exceptions import InvalidTransactionError
from cgt_calc.model import (
    ActionType,
    BrokerTransaction,
    CurrencyCode,
    RuleType,
)

from .calc_test_data import GBP, split_transaction, transaction
from .test_calc import create_calculator, get_report


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


def test_consolidation_cancels_units_and_keeps_pool_cost() -> None:
    """Ten units costing £100 become four units still costing £100."""
    buy_day = datetime.date(2024, 6, 1)
    consolidation_day = datetime.date(2024, 6, 10)
    calculator = create_calculator(tax_year=2024, balance_check=False)

    get_report(
        calculator,
        [
            _buy(buy_day, "FOO", 10, 10),
            # 10 units in, 4 out: a 1-for-2.5 consolidation cancels 6.
            split_transaction(consolidation_day, "FOO", -6),
        ],
    )

    position = calculator.portfolio["FOO"]
    assert position.quantity == Decimal(4)
    assert position.amount == Decimal(100)


def test_consolidation_raises_no_gain() -> None:
    """No disposal occurs, so no chargeable gain arises."""
    buy_day = datetime.date(2024, 6, 1)
    calculator = create_calculator(tax_year=2024, balance_check=False)

    report = get_report(
        calculator,
        [
            _buy(buy_day, "FOO", 10, 10),
            split_transaction(datetime.date(2024, 6, 10), "FOO", -6),
        ],
    )

    assert report.total_gain() == Decimal(0)


def test_consolidation_is_logged_as_a_reorganisation() -> None:
    """The calculation log records the consolidation with its own rule type."""
    consolidation_day = datetime.date(2024, 6, 10)
    calculator = create_calculator(tax_year=2024, balance_check=False)

    report = get_report(
        calculator,
        [
            _buy(datetime.date(2024, 6, 1), "FOO", 10, 10),
            split_transaction(consolidation_day, "FOO", -6),
        ],
    )

    entries = report.calculation_log[consolidation_day]["consolidation$FOO"]
    assert len(entries) == 1
    assert entries[0].rule_type is RuleType.SHARE_CONSOLIDATION
    assert entries[0].quantity == Decimal(6)
    assert entries[0].new_quantity == Decimal(4)
    # The pool cost survives the reorganisation intact.
    assert entries[0].new_pool_cost == Decimal(100)


def test_disposal_after_consolidation_uses_the_new_unit_count() -> None:
    """A later sale apportions cost over the post-consolidation units.

    Selling 2 of the 4 remaining units is half the holding, so half of the
    £100 pool cost is allowable - not the fifth it would be if the cost were
    still spread over the original 10 units.
    """
    calculator = create_calculator(tax_year=2024, balance_check=False)

    report = get_report(
        calculator,
        [
            _buy(datetime.date(2024, 6, 1), "FOO", 10, 10),
            split_transaction(datetime.date(2024, 6, 10), "FOO", -6),
            transaction(
                datetime.date(2024, 6, 20),
                ActionType.SELL,
                "FOO",
                2,
                30,
                0,
                60,
                CurrencyCode(GBP),
            ),
        ],
    )

    # Proceeds £60 less allowable cost £50.
    assert report.total_gain() == Decimal(10)


def test_consolidation_of_an_unheld_symbol_is_refused() -> None:
    """Cancelling units of something not held cannot be computed."""
    calculator = create_calculator(tax_year=2024, balance_check=False)

    with pytest.raises(InvalidTransactionError, match="not held at that date"):
        get_report(
            calculator,
            [split_transaction(datetime.date(2024, 6, 10), "FOO", -6)],
        )


def test_consolidation_leaving_no_units_is_refused() -> None:
    """Cancelling the whole holding is a liquidation, treated differently."""
    calculator = create_calculator(tax_year=2024, balance_check=False)

    with pytest.raises(InvalidTransactionError, match="leaves no units"):
        get_report(
            calculator,
            [
                _buy(datetime.date(2024, 6, 1), "FOO", 10, 10),
                split_transaction(datetime.date(2024, 6, 10), "FOO", -10),
            ],
        )


def test_forward_split_still_adds_units() -> None:
    """The positive-quantity path is unchanged by the consolidation branch."""
    calculator = create_calculator(tax_year=2024, balance_check=False)

    get_report(
        calculator,
        [
            _buy(datetime.date(2024, 6, 1), "FOO", 10, 10),
            split_transaction(datetime.date(2024, 6, 10), "FOO", 10),
        ],
    )

    position = calculator.portfolio["FOO"]
    assert position.quantity == Decimal(20)
    assert position.amount == Decimal(100)
