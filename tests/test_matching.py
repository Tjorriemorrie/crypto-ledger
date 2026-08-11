"""FIFO matching behaviour."""

from decimal import Decimal

import pytest

from main.matching import match_credit_fifo, unmatched_totals
from main.models import Account, Currency, Match

pytestmark = pytest.mark.django_db


def test_credit_fully_consumes_a_single_earlier_debit(btc, zar, record):
    buy = record(btc, zar, 2, day=0, counterpart_quantity=50000)
    sell = record(btc, zar, -2, day=5, counterpart_quantity=-60000)

    matches = match_credit_fifo(sell)

    assert len(matches) == 1
    assert matches[0].debit_id == buy.pk
    assert matches[0].quantity == Decimal(2)
    assert buy.unmatched_quantity == 0
    assert sell.unmatched_quantity == 0


def test_credit_consumes_oldest_debits_first(btc, zar, record):
    first = record(btc, zar, 1, day=0)
    second = record(btc, zar, 3, day=1)
    third = record(btc, zar, 5, day=2)
    sell = record(btc, zar, -3, day=9)

    matches = match_credit_fifo(sell)

    assert [(m.debit_id, m.quantity) for m in matches] == [
        (first.pk, Decimal(1)),
        (second.pk, Decimal(2)),
    ]
    assert first.unmatched_quantity == 0
    assert second.unmatched_quantity == Decimal(1)
    assert third.unmatched_quantity == Decimal(5)


def test_credit_beyond_the_open_debits_stays_partly_unmatched(btc, zar, record):
    buy = record(btc, zar, 1, day=0)
    sell = record(btc, zar, -4, day=1)

    match_credit_fifo(sell)

    assert buy.unmatched_quantity == 0
    assert sell.unmatched_quantity == Decimal(3)


def test_debits_after_the_credit_are_not_eligible(btc, zar, record):
    record(btc, zar, 5, day=8)
    sell = record(btc, zar, -5, day=2)

    assert match_credit_fifo(sell) == []
    assert sell.unmatched_quantity == Decimal(5)


def test_rerunning_matching_changes_nothing(btc, zar, record):
    record(btc, zar, 2, day=0)
    sell = record(btc, zar, -2, day=1)

    match_credit_fifo(sell)
    assert match_credit_fifo(sell) == []
    assert Match.objects.count() == 1
    assert sell.unmatched_quantity == 0


def test_a_backdated_debit_extends_an_existing_partial_match(btc, zar, record):
    buy = record(btc, zar, 1, day=1)
    sell = record(btc, zar, -3, day=5)
    match_credit_fifo(sell)
    assert sell.unmatched_quantity == Decimal(2)

    record(btc, zar, 2, day=0)
    match_credit_fifo(sell)

    assert sell.unmatched_quantity == 0
    assert buy.unmatched_quantity == 0
    assert Match.objects.count() == 2


def test_matching_is_per_account(btc, zar, record):
    """A credit only ever looks at debits on its own account, so holdings never cross."""
    cold = Account.objects.create(name="Cold BTC", currency=Currency.BTC)
    record(cold, zar, 10, day=0)
    sell = record(btc, zar, -1, day=1)

    assert match_credit_fifo(sell) == []


def test_matching_a_debit_is_rejected(btc, zar, record):
    buy = record(btc, zar, 1, day=0)

    with pytest.raises(ValueError, match="not a credit"):
        match_credit_fifo(buy)


def test_fractional_quantities_match_exactly(btc, zar, record):
    record(btc, zar, "0.30000000", day=0)
    record(btc, zar, "0.00000001", day=1)
    sell = record(btc, zar, "-0.30000001", day=2)

    match_credit_fifo(sell)

    assert sell.unmatched_quantity == 0


def test_unmatched_totals_reports_both_sides(btc, zar, record):
    record(btc, zar, 5, day=0)
    sell = record(btc, zar, -8, day=1)
    match_credit_fifo(sell)

    assert unmatched_totals(btc) == {"debit": Decimal(0), "credit": Decimal(3)}


def test_balance_is_debits_less_credits(btc, zar, record):
    record(btc, zar, 3, day=0)
    record(btc, zar, -1, day=1)

    assert btc.balance == Decimal(2)
    assert zar.balance == Decimal(-2)
