"""Exchange rates: downloading them from CoinGecko and keeping one per asset per date.

Everything in the ledger is reported in ZAR, so anything that is not ZAR has to be priced. A
quantity that moved on a given date is valued at that date's rate, and a balance is valued at
the latest rate held. Each date is downloaded once and stored — a past price cannot change,
and the ledger stays usable offline once a date has been fetched.

Two rates are kept, and one download gets both: CoinGecko quotes BTC in ZAR and in USD at the
same time, and dividing the one by the other is the dollar rate. The stablecoins are not
priced separately — a USDT and a USDC are each held to be one dollar.
"""

import datetime as dt
import logging
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone

from main.models import (
    BASE_CURRENCY,
    QUANTITY_DECIMAL_PLACES,
    Currency,
    ExchangeRate,
    RatedAsset,
)

logger = logging.getLogger(__name__)

API_ROOT = "https://api.coingecko.com/api/v3"
COIN = "bitcoin"
ZAR = "zar"
USD = "usd"
TIMEOUT_SECONDS = 10

# Which rate values a currency. The stablecoins are pegged to the dollar, so they are all
# valued off the one USD/ZAR rate; ZAR is absent because ZAR needs no converting.
ASSET_FOR_CURRENCY = {
    Currency.BTC: RatedAsset.BTC,
    Currency.USDT: RatedAsset.USD,
    Currency.USDC: RatedAsset.USD,
}

# The dev server restarts on every edit, so a boot only downloads prices when the rates held
# for today are older than this. Crypto moves, but not enough to justify a call per reload.
STARTUP_MAX_AGE = dt.timedelta(minutes=15)

SMALLEST_UNIT = Decimal(1).scaleb(-QUANTITY_DECIMAL_PLACES)


def latest_rate(asset):
    """The most recently dated rate held for `asset`, or None if none has been downloaded."""
    return ExchangeRate.objects.filter(asset=asset).first()


def latest_rates():
    """The most recent rate held for each asset, newest first, for showing what is in hand."""
    return [rate for rate in map(latest_rate, RatedAsset) if rate is not None]


def refresh_current_rates(max_age=None):
    """Download the prices as they stand now and store them against today.

    Called when the server starts, and from the refresh button on the accounts page, so the
    totals are current without every page view reaching for the network. Pass `max_age` to
    leave recently downloaded prices alone and get them back untouched.
    """
    today = timezone.localdate()
    held = _rates_held_for(today)
    if max_age is not None and _is_fresh(held, max_age):
        return held

    prices = _spot_prices()
    if not prices:
        return held
    return _store(today, prices)


def refresh_at_startup():
    """Refresh the rates as the server comes up, without anything stopping it booting.

    Called from `wsgi.py`, so it runs once per server start and never for a management command
    or a test run. A database that has not been migrated yet is a warning, not a crash.
    """
    try:
        return refresh_current_rates(max_age=STARTUP_MAX_AGE)
    except DatabaseError:
        logger.warning("Skipped the startup rate download: run migrate first.")
        return {}


def rates_for_date(day):
    """Every rate for `day`, downloading the date the first time it is asked for.

    Returns whatever is held — possibly nothing — when the date cannot be downloaded.
    """
    held = _rates_held_for(day)
    if len(held) == len(RatedAsset):
        return held
    prices = _historical_prices(day)
    if not prices:
        return held
    return _store(day, prices)


def rate_used(currency, on):
    """The rate a quantity of `currency` was valued at on a date, for showing the working.

    None when rands need no rate, or when the date could not be priced. The stablecoins come
    back with the dollar rate, since that is genuinely what valued them.
    """
    if currency == BASE_CURRENCY:
        return None
    asset = ASSET_FOR_CURRENCY.get(currency)
    if asset is None:
        return None
    return rates_for_date(on).get(asset)


def to_zar(quantity, currency, on=None):
    """Value `quantity` of `currency` in ZAR, or None when no rate is available.

    `on` prices the quantity at that date's rate — what a transaction was worth when it
    happened. Without it the latest rate held is used, which is what a balance is worth now.

    A currency with nothing to price it by — one the ledger no longer offers, say — is worth
    None rather than being valued off some other asset's rate.
    """
    if currency == BASE_CURRENCY:
        return quantity
    asset = ASSET_FOR_CURRENCY.get(currency)
    if asset is None:
        return None
    rate = rates_for_date(on).get(asset) if on else latest_rate(asset)
    if rate is None:
        return None
    return quantity * rate.zar_per_unit


def _rates_held_for(day):
    """The rates already stored for a date, keyed by asset."""
    return {rate.asset: rate for rate in ExchangeRate.objects.filter(date=day)}


def _is_fresh(held, max_age):
    """True when every asset has a rate for the date and none of them is older than max_age."""
    if len(held) < len(RatedAsset):
        return False
    cutoff = timezone.now() - max_age
    return all(rate.fetched_at > cutoff for rate in held.values())


def _store(day, prices):
    stored = {}
    for asset, price in prices.items():
        rate, _ = ExchangeRate.objects.update_or_create(
            date=day, asset=asset, defaults={"zar_per_unit": price}
        )
        stored[asset] = rate
    return stored


def _spot_prices():
    """The rates as they stand now."""
    payload = _get_json("/simple/price", {"ids": COIN, "vs_currencies": f"{ZAR},{USD}"})
    if not payload:
        return {}
    quotes = payload.get(COIN, {})
    return _prices_from(quotes.get(ZAR), quotes.get(USD))


def _historical_prices(day):
    """The rates on a given date. CoinGecko wants the date as DD-MM-YYYY."""
    payload = _get_json(
        f"/coins/{COIN}/history",
        {"date": day.strftime("%d-%m-%Y"), "localization": "false"},
    )
    if not payload:
        return {}
    quotes = payload.get("market_data", {}).get("current_price", {})
    return _prices_from(quotes.get(ZAR), quotes.get(USD))


def _prices_from(zar_per_btc, usd_per_btc):
    """Turn one BTC quote in two currencies into a rate per asset.

    A BTC costing R2 000 000 and $100 000 puts the dollar at R20, which is what the stablecoin
    accounts are valued with. Without both quotes there is no dollar rate to work out.
    """
    zar_per_btc = _to_decimal(zar_per_btc)
    usd_per_btc = _to_decimal(usd_per_btc)
    if zar_per_btc is None or not usd_per_btc:
        return {}
    return {
        RatedAsset.BTC: zar_per_btc,
        RatedAsset.USD: (zar_per_btc / usd_per_btc).quantize(SMALLEST_UNIT),
    }


def _get_json(path, params):
    """GET a CoinGecko endpoint, returning None when the download does not work out.

    A missing rate is never fatal — the page shows a dash instead of a value — so every
    failure is logged and swallowed rather than raised at whoever asked for a price.
    """
    if not settings.RATES_DOWNLOAD:
        return None
    try:
        response = requests.get(f"{API_ROOT}{path}", params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        logger.warning("Could not download %s from CoinGecko", path, exc_info=True)
        return None


def _to_decimal(price):
    """CoinGecko sends prices as JSON floats; go via the string to keep the digits shown."""
    if price is None:
        return None
    try:
        return Decimal(str(price))
    except InvalidOperation:
        logger.warning("CoinGecko returned an unusable price: %r", price)
        return None
