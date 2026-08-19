"""Reading the ledger back week by week, and keeping those weeks on disk."""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from main import history
from main.models import ExchangeRate, RatedAsset

pytestmark = pytest.mark.django_db

WEEKS = 3


@pytest.fixture
def priced():
    """A rate for every asset on every day the three-week window covers."""
    today = timezone.localdate()
    for offset in range(WEEKS * history.DAYS_PER_WEEK):
        day = today - dt.timedelta(days=offset)
        ExchangeRate.objects.create(date=day, asset=RatedAsset.BTC, zar_per_unit=Decimal(1500000))
        ExchangeRate.objects.create(date=day, asset=RatedAsset.USD, zar_per_unit=Decimal(18))


def test_profit_history_stacks_the_investment_under_the_crypto(priced, btc, usdt, zar, record):
    record(btc, zar, 2, day=0, counterpart_quantity=1000000)
    record(usdt, zar, 500, day=0, counterpart_quantity=9000)

    weeks = history.profit_history(WEEKS)

    assert len(weeks) == WEEKS
    # The money put in first, so it stacks below the axis, then the stablecoins with the crypto
    # over them — 2 BTC at R1 500 000 and 500 USDT at R18.
    assert weeks[-1]["parts"] == [
        {"label": "Bank ZAR", "value": Decimal(-1009000)},
        {"label": "Exchange USDT", "value": Decimal(9000)},
        {"label": "Ledger BTC", "value": Decimal(3000000)},
    ]


def test_a_settled_week_comes_back_off_the_cache(priced, btc, zar, record):
    record(btc, zar, 2, day=0, counterpart_quantity=1000000)
    before = history.profit_history(WEEKS)

    # Move the rate a week that has already closed was valued at. Only that week's own figures
    # could show it, and they are cached, so the bar does not budge — which is what proves it came
    # off the cache. Nothing in the app rewrites a past rate; only today's is downloaded again.
    ExchangeRate.objects.filter(date=before[0]["date"], asset=RatedAsset.BTC).update(
        zar_per_unit=Decimal(9000000)
    )

    assert history.profit_history(WEEKS)[0]["parts"] == before[0]["parts"]


def test_recording_a_transaction_throws_the_cache_away(priced, btc, zar, record):
    record(btc, zar, 2, day=0, counterpart_quantity=1000000)
    history.profit_history(WEEKS)

    record(btc, zar, 1, day=1, counterpart_quantity=600000)
    weeks = history.profit_history(WEEKS)

    # 3 BTC now, not 2 — a backdated transaction moves weeks that were already worked out.
    assert weeks[-1]["parts"][-1]["value"] == Decimal(4500000)
