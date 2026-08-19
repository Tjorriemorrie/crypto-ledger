"""Shared fixtures: two accounts and a shorthand for recording transactions."""

import datetime as dt
import shutil
import tempfile
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.cache import cache

from main.models import Account, Currency, Entry, Transaction

DAY = dt.timedelta(days=1)
START = dt.date(2026, 1, 1)


def pytest_configure():
    """Cache into a scratch directory, so no test run writes into the working tree.

    Here rather than in a fixture because pytest-django builds every cache the settings name while
    it sets the test database up, which happens before any fixture can override them. The real
    backend, not a stand-in: what is cached has to survive being written and read back, and one
    test turns on it doing exactly that.
    """
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": tempfile.mkdtemp(prefix="crypto-ledger-cache-"),
            "TIMEOUT": None,
        }
    }


def pytest_unconfigure():
    shutil.rmtree(settings.CACHES["default"]["LOCATION"], ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_downloads(settings):
    """No test reaches CoinGecko; the ones that need a rate store or fake one themselves."""
    settings.RATES_DOWNLOAD = False


@pytest.fixture(autouse=True)
def _empty_cache():
    """Every test starts with an empty cache, so none of them inherits another's weeks."""
    cache.clear()


@pytest.fixture
def btc():
    return Account.objects.create(name="Ledger BTC", currency=Currency.BTC)


@pytest.fixture
def usdt():
    return Account.objects.create(name="Exchange USDT", currency=Currency.USDT)


@pytest.fixture
def zar():
    return Account.objects.create(name="Bank ZAR", currency=Currency.ZAR)


@pytest.fixture
def record():
    """Record a transaction moving `quantity` of the asset into or out of `account`.

    The counterpart always takes the opposite side, so a negative `quantity` is a sale: the
    asset leaves `account` and the proceeds land on `counterpart` as a debit. Both quantities
    are given as magnitudes; only the sign of `quantity` decides the direction.
    """

    def _record(account, counterpart, quantity, *, day, counterpart_quantity=None):
        quantity = Decimal(quantity)
        other = abs(Decimal(counterpart_quantity if counterpart_quantity is not None else quantity))
        transaction = Transaction.objects.create(occurred_on=START + day * DAY)
        entry = Entry.objects.create(transaction=transaction, account=account, quantity=quantity)
        Entry.objects.create(
            transaction=transaction,
            account=counterpart,
            quantity=-other if quantity > 0 else other,
        )
        return entry

    return _record
