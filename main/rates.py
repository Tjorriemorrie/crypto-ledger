"""Exchange rates: downloading them from CoinGecko and keeping one per asset per date.

Everything in the ledger is reported in ZAR, so anything that is not ZAR has to be priced. A
quantity that moved on a given date is valued at that date's rate, and a balance is valued at
the latest rate held. Each date is downloaded once and stored — a past price cannot change,
and the ledger stays usable offline once a date has been fetched.

Two rates are kept, and every download works both out the same way: CoinGecko quotes BTC in ZAR
and in USD, and dividing the one by the other is the dollar rate. The stablecoins are not
priced separately — a USDT and a USDC are each held to be one dollar. A single date gets both
quotes in one call; a whole window takes two, since a market chart is quoted in one currency.
"""

import datetime as dt
import logging
from collections import Counter
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

# The most days one market chart will serve. CoinGecko's public API refuses anything older than a
# year outright, so a longer window is filled a year deep and the days behind that are whatever is
# already held — asking for more only ever gets a 401, on every boot and every page load.
MAX_WINDOW_DAYS = 365

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


def fill_window(days):
    """Make sure the last `days` days have been downloaded, and say which day they start from.

    Only the two ends are looked at — the oldest day that can be downloaded and yesterday — so this
    is a couple of rows read rather than a window's worth. A download fills everything between them
    at once, so a window holding both ends has already been fetched, and one missing an end has
    either never been fetched or has gone a day stale.

    A window longer than `MAX_WINDOW_DAYS` is filled to that depth and no further, since a market
    chart older than a year is not something the public API will serve at any price. The days
    behind that are whatever the ledger already holds, and the day a window starts from is still
    the day asked for — a rate downloaded a year ago is a rate like any other, and a day with none
    is a day left out rather than an error.

    Everything downloaded is kept, like any other rate, and a date already held is left as it was:
    a past price does not change, and today's spot price is fresher than the last point of a chart.
    """
    start = timezone.localdate() - dt.timedelta(days=days - 1)
    depth = min(days, MAX_WINDOW_DAYS)
    oldest = timezone.localdate() - dt.timedelta(days=depth - 1)
    if not _window_covered(oldest):
        _download_window(depth, oldest)
    return start


def priced_days(days):
    """Which of the last `days` days hold a rate for every asset, as a set of dates.

    The dates and nothing else. Whether a day can be valued at all is a question about coverage,
    and a two-year window is fourteen hundred rows — reading a price out of each one to answer it
    costs several times what counting them does.
    """
    start = fill_window(days)
    held = Counter(ExchangeRate.objects.filter(date__gte=start).values_list("date", flat=True))
    return {date for date, assets in held.items() if assets == len(RatedAsset)}


def prices_on(dates):
    """What one unit of each asset cost in ZAR on each of `dates`, keyed by date then by asset.

    Prices rather than `ExchangeRate` rows: whatever values a great many days at once wants the
    figures, and building a model instance per row costs more than the arithmetic does.
    """
    prices = {}
    rows = ExchangeRate.objects.filter(date__in=dates).values_list("date", "asset", "zar_per_unit")
    for date, asset, zar_per_unit in rows:
        prices.setdefault(date, {})[asset] = zar_per_unit
    return prices


def btc_history(days):
    """The daily BTC closes held over the last `days` days, oldest first, as `(date, price)`.

    BTC because it is the asset whose price moves — a chart of the dollar rate would be a
    chart of the rand, and the stablecoins are a dollar each by definition. The date comes with
    the price because the chart labels each point with the day it was downloaded for.

    This is the window the price chart draws, and every point on it is the ledger's own rate. The
    days behind the window are a different question and are answered elsewhere: `days` here is
    asked for within the year CoinGecko will serve, so it is one download and no gaps.
    """
    start = fill_window(days)
    return list(
        ExchangeRate.objects.filter(asset=RatedAsset.BTC, date__gte=start)
        .order_by("date")
        .values_list("date", "zar_per_unit")
    )


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


def value_with(quantity, currency, prices):
    """Value `quantity` of `currency` against `prices`, one ZAR price per asset.

    For a page pricing many dates at once: the profit chart values every account at the close of
    every week in its window, which is far too many dates to look each one up as it goes. A day's
    prices are read once and everything on that day is valued against them.
    """
    if currency == BASE_CURRENCY:
        return quantity
    price = prices.get(ASSET_FOR_CURRENCY.get(currency))
    return None if price is None else quantity * price


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


def _window_covered(start):
    """Whether a chart window needs no download: both its ends hold a rate for every asset."""
    ends = {start, timezone.localdate() - dt.timedelta(days=1)}
    return ExchangeRate.objects.filter(date__in=ends).count() == len(RatedAsset) * len(ends)


def _download_window(days, start):
    """Download the window and keep every day of it the ledger does not already hold.

    One statement rather than a row at a time: a cold two-year window is fourteen hundred rows,
    and the dates already held are left exactly as they were by letting their unique constraint
    turn them away.
    """
    ExchangeRate.objects.bulk_create(
        [
            ExchangeRate(date=day, asset=asset, zar_per_unit=price)
            for day, prices in _downloaded_prices(days).items()
            if day >= start
            for asset, price in prices.items()
        ],
        ignore_conflicts=True,
    )


def _downloaded_prices(days):
    """The rate of every asset for each of the last `days` days, keyed by date.

    Two downloads rather than one: a market chart is quoted in a single currency, unlike the
    spot and single-date endpoints, so the BTC close is fetched in rands and again in dollars
    and dividing the one by the other gives that day's dollar rate — the same working as
    everywhere else here. A day the dollar quote is missing still keeps its BTC close.
    """
    in_zar = _daily_closes(days, ZAR)
    in_usd = _daily_closes(days, USD)
    return {
        day: _prices_from(zar_per_btc, in_usd.get(day)) or {RatedAsset.BTC: zar_per_btc}
        for day, zar_per_btc in in_zar.items()
    }


def _daily_closes(days, vs):
    """The BTC close in `vs` for each of the last `days` days, keyed by date.

    CoinGecko's market chart sends one point a day for any window past 90 days, stamped
    midnight UTC — the same moment the single-date endpoint prices, so a day downloaded either
    way holds the same figure.
    """
    payload = _get_json(f"/coins/{COIN}/market_chart", {"vs_currency": vs, "days": days})
    if not payload:
        return {}
    closes = {}
    for stamp, quoted in payload.get("prices", []):
        price = _to_decimal(quoted)
        if price is not None:
            closes[dt.datetime.fromtimestamp(stamp / 1000, tz=dt.UTC).date()] = price
    return closes


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
