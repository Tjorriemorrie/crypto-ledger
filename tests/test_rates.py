"""Downloading exchange rates and valuing quantities with them."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from main import rates
from main.models import Currency, ExchangeRate, RatedAsset

pytestmark = pytest.mark.django_db

DATE = dt.date(2026, 1, 5)


@pytest.fixture
def coingecko(monkeypatch, settings):
    """Answer every CoinGecko call with a BTC quote in both currencies, off the network."""
    settings.RATES_DOWNLOAD = True
    payloads = {
        "/simple/price": {"bitcoin": {"zar": 2000000.0, "usd": 100000.0}},
        "/coins/bitcoin/history": {
            "market_data": {"current_price": {"zar": 1500000.0, "usd": 100000.0}}
        },
    }
    monkeypatch.setattr(rates, "_get_json", lambda path, params: payloads[path])


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


def test_to_zar_values_each_currency_by_its_own_rate(held):
    assert rates.to_zar(Decimal("0.5"), Currency.BTC) == Decimal(750000)
    assert rates.to_zar(Decimal(100), Currency.USDT) == Decimal(2000)
    assert rates.to_zar(Decimal(100), Currency.USDC) == Decimal(2000)
    assert rates.to_zar(Decimal(120), Currency.ZAR) == Decimal(120)
