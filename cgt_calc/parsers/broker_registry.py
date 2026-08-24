"""Registry for all broker parsers."""

from __future__ import annotations

from collections import defaultdict
import datetime
from decimal import Decimal
import logging
from typing import TYPE_CHECKING, ClassVar

from cgt_calc.model import ActionType
from cgt_calc.parsers.eri.raw import ERIRawParser
from cgt_calc.parsers.freetrade import FreetradeParser
from cgt_calc.parsers.hl import HargreavesLansdownParser
from cgt_calc.parsers.interactive_brokers import InteractiveBrokersParser
from cgt_calc.parsers.mssb import MSSBParser
from cgt_calc.parsers.raw import RawParser
from cgt_calc.parsers.schwab import SchwabParser
from cgt_calc.parsers.schwab_equity_award_json import SchwabEquityAwardsJSONParser
from cgt_calc.parsers.sharesight import SharesightParser
from cgt_calc.parsers.trading212 import Trading212Parser
from cgt_calc.parsers.vanguard import VanguardParser

if TYPE_CHECKING:
    import argparse

    from cgt_calc.isin_converter import IsinConverter
    from cgt_calc.model import BrokerTransaction

    from .base_parsers import BaseParser

LOGGER = logging.getLogger(__name__)


class BrokerRegistry:
    """Registry for all broker parsers."""

    _BROKERS: ClassVar[list[type[BaseParser]]] = [
        FreetradeParser,
        RawParser,
        SchwabParser,
        SchwabEquityAwardsJSONParser,
        SharesightParser,
        Trading212Parser,
        MSSBParser,
        VanguardParser,
        InteractiveBrokersParser,
        HargreavesLansdownParser,
        # Add new brokers here
    ]

    @staticmethod
    def register_all_arguments(broker_group: argparse._ArgumentGroup) -> None:
        """Register arguments for all brokers."""
        for broker_class in BrokerRegistry._BROKERS:
            broker_class.register_arguments(broker_group)

        # ERI Raw is not a broker but is close enough to one to be here
        ERIRawParser.register_arguments(broker_group)

    @staticmethod
    def load_all_transactions(
        args: argparse.Namespace, isin_converter: IsinConverter
    ) -> list[BrokerTransaction]:
        """Load transactions from all brokers."""
        all_transactions: list[BrokerTransaction] = []
        for broker_class in BrokerRegistry._BROKERS:
            transactions = broker_class.load_from_args(args)
            if transactions:
                LOGGER.info(
                    "Loaded %d transactions from %s",
                    len(transactions),
                    broker_class.__name__,
                )
                all_transactions += transactions

        if len(all_transactions) == 0:
            LOGGER.warning("Found 0 broker transactions")
        else:
            print(f"Found {len(all_transactions)} broker transactions")

        # ERI Raw is not a broker but is close enough to one to be here
        # Only add ERI for funds that show up in the portfolio
        isin_map = isin_converter.get_symbol_to_isin_map()
        isins = {trx.isin or isin_map.get(trx.symbol or "") for trx in all_transactions}
        eri_transactions = ERIRawParser.load_from_args(args)
        all_transactions += [trx for trx in eri_transactions if trx.isin in isins]

        BrokerRegistry._warn_about_missing_eri(
            eri_transactions, all_transactions, isins, isin_map, args
        )

        all_transactions.sort(key=lambda k: k.date)
        return all_transactions

    @staticmethod
    def _closed_out_symbols(transactions: list[BrokerTransaction]) -> set[str]:
        """Return symbols that were traded and ended on a nil position.

        A rough running total, used only to keep the ERI warning quiet about
        funds that were sold out years ago. It deliberately reports a symbol as
        closed only when the arithmetic works out to exactly zero, so anything
        it cannot follow is treated as still held.
        """
        net: dict[str, Decimal] = defaultdict(Decimal)
        seen: set[str] = set()

        for transaction in transactions:
            symbol = transaction.symbol
            if symbol is None or transaction.quantity is None:
                continue
            if transaction.action in [
                ActionType.BUY,
                ActionType.REINVEST_SHARES,
                ActionType.STOCK_ACTIVITY,
                ActionType.SPIN_OFF,
                ActionType.STOCK_SPLIT,
            ]:
                net[symbol] += transaction.quantity
                seen.add(symbol)
            elif transaction.action in [
                ActionType.SELL,
                ActionType.CASH_MERGER,
                ActionType.FULL_REDEMPTION,
            ]:
                net[symbol] -= transaction.quantity
                seen.add(symbol)

        return {symbol for symbol in seen if net[symbol] == 0}

    @staticmethod
    def _warn_about_missing_eri(
        eri_transactions: list[BrokerTransaction],
        all_transactions: list[BrokerTransaction],
        held_isins: set[str | None],
        isin_map: dict[str, str],
        args: argparse.Namespace,
    ) -> None:
        """Warn when a held reporting fund has no ERI figure for the tax year.

        Excess Reported Income is deemed to arise six months after the fund's
        reporting period end, so the tax year picks up periods ending between
        6 October of the previous year and 5 October of the tax year. A fund
        that has reported in the past but has nothing in that window usually
        means its figures have not been imported yet, not that it reported
        nothing. Without this warning that is indistinguishable from a genuine
        nil return, since both show up as zero in the report.
        """
        year = getattr(args, "year", None)
        if year is None:
            return

        window_start = datetime.date(year - 1, 10, 6)
        window_end = datetime.date(year, 10, 5)

        periods_by_isin: dict[str, set[datetime.date]] = defaultdict(set)
        for transaction in eri_transactions:
            if transaction.isin:
                periods_by_isin[transaction.isin].add(transaction.date)

        # Build this from the symbols actually transacted, not from the bundled
        # ISIN table. That table lists every ticker an ISIN has ever traded
        # under - "IE00B3XXRP09,VUSA,VUSD" - so a user who only ever held VUSA
        # would never satisfy a check over all of them, and an ISIN absent from
        # the table would yield no symbols at all.
        isin_to_symbols: dict[str, set[str]] = defaultdict(set)
        for transaction in all_transactions:
            if transaction.symbol is None:
                continue
            isin = transaction.isin or isin_map.get(transaction.symbol)
            if isin:
                isin_to_symbols[isin].add(transaction.symbol)

        closed = BrokerRegistry._closed_out_symbols(all_transactions)

        for isin in sorted(i for i in held_isins if i):
            periods = periods_by_isin.get(isin)
            if not periods:
                # No history at all: either not a reporting fund, or unknown to
                # the bundled data. Nothing to infer from.
                continue
            if any(window_start <= period <= window_end for period in periods):
                continue

            symbols = isin_to_symbols.get(isin, [])
            # Stay quiet only when every symbol for this fund is provably sold
            # out. Anything we cannot account for still warns: a fund can be
            # held all year without transacting, and missing an ERI charge is
            # worse than an unnecessary warning.
            if symbols and all(symbol in closed for symbol in symbols):
                continue

            known_as = ", ".join(sorted(isin_to_symbols.get(isin, []))) or isin
            LOGGER.warning(
                "No Excess Reported Income figure for %s (%s) covering a fund "
                "reporting period ending between %s and %s, which is what tax "
                "year %d/%02d picks up. The most recent period on file is %s. "
                "ERI is taxable whether or not it was distributed, so check the "
                "fund's reporting data rather than assuming nil.",
                known_as,
                isin,
                window_start,
                window_end,
                year,
                (year + 1) % 100,
                max(periods),
            )
