"""The account pages and the transaction form."""

import datetime as dt
from decimal import Decimal

import pytest
from django.db.utils import IntegrityError
from django.urls import reverse

from main.models import Account, Entry, ExchangeRate, Match, RatedAsset, Transaction

pytestmark = pytest.mark.django_db


def test_account_list_shows_accounts_and_balances(client, btc, zar, record):
    record(btc, zar, 2, day=0, counterpart_quantity=50000)

    response = client.get(reverse("account-list"))

    assert response.status_code == 200
    assert "Ledger BTC" in response.content.decode()


def test_account_list_totals_every_account_in_zar(client, btc, zar, record):
    record(btc, zar, 2, day=0, counterpart_quantity=1000000)
    ExchangeRate.objects.create(
        date=dt.date(2026, 1, 1), asset=RatedAsset.BTC, zar_per_unit=Decimal(1500000)
    )

    response = client.get(reverse("account-list"))

    # 2 BTC at R1 500 000 each, less the R1 000 000 that left the bank account.
    assert response.context["total"] == Decimal(2000000)


def test_creating_an_account(client):
    response = client.post(
        reverse("account-create"),
        {"name": "Kraken BTC", "currency": "BTC", "note": ""},
        follow=True,
    )

    assert response.status_code == 200
    assert Account.objects.get(name="Kraken BTC").currency == "BTC"


def test_editing_an_account_name_and_note(client, btc):
    client.post(
        reverse("account-edit", args=[btc.pk]),
        {"name": "Ledger Nano BTC", "note": "Hardware wallet"},
    )

    btc.refresh_from_db()
    assert btc.name == "Ledger Nano BTC"
    assert btc.note == "Hardware wallet"


def test_transaction_form_writes_both_sides(client, btc, zar):
    response = client.post(
        reverse("transaction-create", args=[btc.pk]),
        {
            "occurred_on": "2026-01-01",
            "direction": "in",
            "quantity": "1.5",
            "counterpart": zar.pk,
            "counterpart_quantity": "45000",
            "description": "Bought BTC",
            "match_fifo": "on",
        },
    )

    assert response.status_code == 302
    transaction = Transaction.objects.get()
    assert transaction.description == "Bought BTC"
    assert transaction.entries.get(account=btc).quantity == Decimal("1.5")
    assert transaction.entries.get(account=zar).quantity == Decimal(-45000)


def test_transaction_form_defaults_the_other_quantity_for_a_transfer(client, btc, zar):
    cold = Account.objects.create(name="Cold BTC", currency="BTC")
    client.post(
        reverse("transaction-create", args=[btc.pk]),
        {
            "occurred_on": "2026-01-01",
            "direction": "out",
            "quantity": "0.25",
            "counterpart": cold.pk,
            "counterpart_quantity": "",
            "description": "To cold storage",
        },
    )

    assert btc.balance == Decimal("-0.25")
    assert cold.balance == Decimal("0.25")


def test_transaction_form_matches_fifo_when_asked(client, btc, zar, record):
    buy = record(btc, zar, 2, day=0, counterpart_quantity=50000)

    client.post(
        reverse("transaction-create", args=[btc.pk]),
        {
            "occurred_on": "2026-01-05",
            "direction": "out",
            "quantity": "2",
            "counterpart": zar.pk,
            "counterpart_quantity": "60000",
            "match_fifo": "on",
            "description": "",
        },
    )

    assert Match.objects.count() == 1
    assert buy.unmatched_quantity == 0


def test_transaction_form_leaves_it_unmatched_when_not_asked(client, btc, zar, record):
    buy = record(btc, zar, 2, day=0, counterpart_quantity=50000)

    client.post(
        reverse("transaction-create", args=[btc.pk]),
        {
            "occurred_on": "2026-01-05",
            "direction": "out",
            "quantity": "2",
            "counterpart": zar.pk,
            "counterpart_quantity": "60000",
            "description": "",
        },
    )

    assert Match.objects.count() == 0
    assert buy.unmatched_quantity == Decimal(2)


def test_the_account_itself_is_not_offered_as_the_other_side(client, btc, zar):
    response = client.get(reverse("transaction-create", args=[btc.pk]))

    choices = response.context["form"].fields["counterpart"].queryset
    assert btc not in choices
    assert zar in choices


def test_zero_quantities_are_rejected(client, btc, zar):
    response = client.post(
        reverse("transaction-create", args=[btc.pk]),
        {
            "occurred_on": "2026-01-01",
            "direction": "in",
            "quantity": "0",
            "counterpart": zar.pk,
            "description": "",
        },
    )

    assert response.status_code == 200
    assert "greater than zero" in response.content.decode()
    assert not Transaction.objects.exists()


def test_matching_an_open_credit_from_the_account_page(client, btc, zar, record):
    record(btc, zar, 2, day=0)
    sell = record(btc, zar, -2, day=1)

    response = client.post(reverse("entry-match", args=[sell.pk]), follow=True)

    assert response.status_code == 200
    assert sell.unmatched_quantity == 0


def test_matching_a_debit_from_the_account_page_is_refused(client, btc, zar, record):
    buy = record(btc, zar, 2, day=0)

    client.post(reverse("entry-match", args=[buy.pk]), follow=True)

    assert not Match.objects.exists()


def test_deleting_the_last_transaction(client, btc, zar, record):
    record(btc, zar, 2, day=0)
    sell = record(btc, zar, -2, day=1)

    client.post(reverse("transaction-delete", args=[btc.pk, sell.transaction.pk]), follow=True)

    assert Transaction.objects.count() == 1
    assert btc.balance == Decimal(2)


def test_deleting_an_earlier_transaction_is_refused(client, btc, zar, record):
    buy = record(btc, zar, 2, day=0)
    record(btc, zar, -2, day=1)

    client.post(reverse("transaction-delete", args=[btc.pk, buy.transaction.pk]), follow=True)

    assert Transaction.objects.count() == 2


def test_account_detail_lists_entries_with_running_balance(client, btc, zar, record):
    record(btc, zar, 3, day=0)
    record(btc, zar, -1, day=1)

    response = client.get(btc.get_absolute_url())
    rows = response.context["rows"]

    assert [row["balance"] for row in rows] == [Decimal(2), Decimal(3)]
    assert response.context["balance"] == Decimal(2)


def test_account_detail_shows_the_other_side_of_each_transaction(client, btc, zar, record):
    record(btc, zar, 1, day=0, counterpart_quantity=30000)

    response = client.get(btc.get_absolute_url())
    entry = response.context["rows"][0]["entry"]

    assert entry.counterpart.account == zar
    assert entry.counterpart.quantity == Decimal(-30000)


def test_entries_cannot_be_zero(btc, zar, record):
    transaction = Transaction.objects.create()
    with pytest.raises(IntegrityError):
        Entry.objects.create(transaction=transaction, account=btc, quantity=0)
