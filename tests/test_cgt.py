"""Working out a disposal's base cost and gain."""

import datetime as dt
from decimal import Decimal

import pytest

from main import cgt
from main.matching import match_credit_fifo
from main.models import ExchangeRate, RatedAsset

pytestmark = pytest.mark.django_db


def test_trace_gives_the_gain_over_what_the_lot_cost(btc, zar, record):
    record(btc, zar, 2, day=0, counterpart_quantity=50000)
    sell = record(btc, zar, -2, day=1, counterpart_quantity=80000)
    match_credit_fifo(sell)

    result = cgt.trace(sell.transaction)

    assert result["proceeds"] == Decimal(80000)
    assert result["base_cost"] == Decimal(50000)
    assert result["gain"] == Decimal(30000)


def test_a_lot_swapped_out_of_another_crypto_costs_its_value_on_the_day(btc, usdt, zar, record):
    ExchangeRate.objects.create(
        date=dt.date(2026, 1, 2), asset=RatedAsset.USD, zar_per_unit=Decimal(25)
    )
    record(btc, zar, 1, day=0, counterpart_quantity=40000)
    swap = record(usdt, btc, 2000, day=1, counterpart_quantity=1)
    match_credit_fifo(swap.counterpart)
    sell = record(usdt, zar, -2000, day=2, counterpart_quantity=45000)
    match_credit_fifo(sell)

    result = cgt.trace(sell.transaction)

    # The USDT was swapped out of BTC, so it cost what it was worth the day it arrived —
    # 2 000 USDT at R25 — and not the R40 000 the BTC behind it was originally bought for.
    assert result["base_cost"] == Decimal(50000)
    assert [row["source"] for row in result["rows"]] == ["swap"]


def test_the_proceeds_are_split_across_the_lots_the_disposal_consumed(btc, zar, record):
    """Each lot has its own acquisition date, so each one goes on the return as its own line."""
    record(btc, zar, 1, day=0, counterpart_quantity=10000)
    record(btc, zar, 1, day=1, counterpart_quantity=20000)
    sell = record(btc, zar, -2, day=2, counterpart_quantity=90000)
    match_credit_fifo(sell)

    result = cgt.trace(sell.transaction)

    # Half the BTC came from each lot, so each lot earned half the proceeds.
    assert [row["proceeds"] for row in result["rows"]] == [Decimal("45000.00"), Decimal("45000.00")]


def test_report_lists_the_disposals_of_a_tax_year_and_totals_them(btc, zar, record):
    # The fixtures date from January 2026, which falls in the tax year ending February 2026.
    record(btc, zar, 2, day=0, counterpart_quantity=50000)
    sell = record(btc, zar, -2, day=1, counterpart_quantity=80000)
    match_credit_fifo(sell)

    result = cgt.report(2026)

    # The purchase is not a disposal, so only the sale is on the return.
    assert [row["transaction"] for row in result["rows"]] == [sell.transaction]
    assert result["proceeds"] == Decimal(80000)
    assert result["base_cost"] == Decimal(50000)
    assert result["gain"] == Decimal(30000)
