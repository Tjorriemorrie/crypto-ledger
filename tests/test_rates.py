"""Downloading exchange rates and valuing quantities with them."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from main import rates
from main.models import Currency, ExchangeRate, RatedAsset

pytestmark = pytest.mark.django_db

DATE = dt.date(2026, 1, 5)


def _midnight_ms(day):
    """A date as CoinGecko stamps its market chart points: midnight UTC, in milliseconds."""
    return dt.datetime.combine(day, dt.time(), tzinfo=dt.UTC).timestamp() * 1000


@pytest.fixture
def coingecko(monkeypatch, settings):
    """Answer every CoinGecko call with a BTC quote in both currencies, off the network.

    A market chart is quoted in one currency at a time, so that one answers by what it was asked
    for: a BTC at R1 000 000 and at $50 000, which puts the dollar at R20.
    """
    settings.RATES_DOWNLOAD = True
    today = timezone.localdate()
    payloads = {
        "/simple/price": {"bitcoin": {"zar": 2000000.0, "usd": 100000.0}},
        "/coins/bitcoin/history": {
            "market_data": {"current_price": {"zar": 1500000.0, "usd": 100000.0}}
        },
    }

    def answer(path, params):
        if path == "/coins/bitcoin/market_chart":
            close = 1000000.0 if params["vs_currency"] == rates.ZAR else 50000.0
            return {
                "prices": [
                    [_midnight_ms(today - dt.timedelta(days=offset)), close] for offset in (2, 1, 0)
                ]
            }
        return payloads[path]

    monkeypatch.setattr(rates, "_get_json", answer)


@pytest.fixture
def held():
    """A rate for each asset: a BTC at R1 500 000 and a dollar at R20."""
    ExchangeRate.objects.create(date=DATE, asset=RatedAsset.BTC, zar_per_unit=Decimal(1500000))
    ExchangeRate.objects.create(date=DATE, asset=RatedAsset.USD, zar_per_unit=Decimal(20))


def test_rates_for_date_downloads_and_stores_a_price_for_each_asset(coingecko):
    downloaded = rates.rates_for_date(DATE)

    assert downloaded[RatedAsset.BTC].zar_per_unit == Decimal(1500000)
    assert downloaded[RatedAsset.USD].zar_per_unit == Decimal(15)
    assert ExchangeRate.objects.filter(date=DATE).count() == 2


def test_refresh_current_rates_stores_todays_prices(coingecko):
    refreshed = rates.refresh_current_rates()

    assert refreshed[RatedAsset.BTC].zar_per_unit == Decimal(2000000)
    assert refreshed[RatedAsset.USD].zar_per_unit == Decimal(20)


def test_the_refresh_button_downloads_new_rates(client, coingecko):
    response = client.post(reverse("rate-refresh"))

    assert response.status_code == 302
    assert rates.latest_rate(RatedAsset.BTC).zar_per_unit == Decimal(2000000)


def test_btc_history_downloads_the_days_behind_the_chart(coingecko):
    today = timezone.localdate()

    window = rates.btc_history(days=3)

    assert [date for date, _ in window] == [
        today - dt.timedelta(days=2),
        today - dt.timedelta(days=1),
        today,
    ]
    assert ExchangeRate.objects.filter(asset=RatedAsset.BTC).count() == 3


def test_a_downloaded_window_prices_both_assets_on_every_day(coingecko):
    today = timezone.localdate()

    days = rates.priced_days(days=3)
    prices = rates.prices_on(days)

    assert days == {today - dt.timedelta(days=offset) for offset in (2, 1, 0)}
    assert {day[RatedAsset.USD] for day in prices.values()} == {Decimal(20)}


def test_value_with_prices_a_holding_off_the_rates_in_hand():
    prices = {RatedAsset.BTC: Decimal(1500000), RatedAsset.USD: Decimal(20)}

    assert rates.value_with(Decimal("0.5"), Currency.BTC, prices) == Decimal(750000)
    assert rates.value_with(Decimal(100), Currency.USDT, prices) == Decimal(2000)


def test_to_zar_values_each_currency_by_its_own_rate(held):
    assert rates.to_zar(Decimal("0.5"), Currency.BTC) == Decimal(750000)
    assert rates.to_zar(Decimal(100), Currency.USDT) == Decimal(2000)
    assert rates.to_zar(Decimal(100), Currency.USDC) == Decimal(2000)
    assert rates.to_zar(Decimal(120), Currency.ZAR) == Decimal(120)
