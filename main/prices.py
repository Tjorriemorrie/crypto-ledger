"""The long BTC price history the analysis page is run over, and the price chart's lead.

This is not the ledger's rates. `rates.py` holds those: CoinGecko's ZAR prices, one row per asset
per date, and they are what values a transaction on a return. CoinGecko's public API refuses
anything older than a year, though, and the analysis wants a decade — so it is downloaded from
Yahoo instead, kept in the cache, and deliberately never written into `ExchangeRate`. A figure on
a SARS return has to be traceable to one source, and two providers quoting the same day a shade
apart is exactly the doubt that must not get into the ledger.

The price chart's lead, `lead`, is the second thing read out of it. The chart's long average and
its change strip both look back further than the year CoinGecko will serve, so without a longer
history they begin part way across the window instead of at its first day. The lead is only ever
the days *behind* the window: every point drawn, every price on the axis and every figure a hover
shows is still the ledger's own rate, and nothing here is written to one.

Yahoo quotes Bitcoin in dollars and the dollar in rands, so multiplying the two gives the ZAR
price — the mirror of the division `rates.py` does to work its dollar rate out of a BTC quote. The
two series do not run on the same days: Bitcoin trades every day and the currency market does not,
so the dollar rate is carried forward over weekends and holidays.

Like the profit chart's weeks, this is a cache and never a record. Everything in it can be
downloaded again, so an entry that is missing or stale costs a download and never a wrong number,
and clearing it is always safe.
"""

import datetime as dt
import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

API_ROOT = "https://query1.finance.yahoo.com/v8/finance/chart"
BITCOIN = "BTC-USD"
DOLLAR = "ZAR=X"
# Everything there is, downloaded once. The analysis page runs over a window of the last few years
# and lets that window be set, so it trims what is held rather than fetching a different history
# each time it moves — the same prices answer every window, and one download covers the lot.
# Yahoo's Bitcoin quotes begin in September 2014 whatever is asked for, so this is a ceiling and
# not a promise; what a window actually covers is the dates the page prints.
YEARS = 15
# What a year is worth in days when a window is counted back off the end of the history. The
# quarter day tells over fifteen of them, and a window is a stretch of prices rather than a date on
# a return, so an average year is the honest length for it.
DAYS_PER_YEAR = 365.25
TIMEOUT_SECONDS = 20

# Yahoo turns away a request that does not look like a browser, and this endpoint is not one it
# documents. The download is best-effort either way: a failure leaves the page saying so.
HEADERS = {"User-Agent": "Mozilla/5.0"}

# The one key the history is kept under. Its name says what is stored there, so changing the shape
# of that means changing the name and letting the old entry fall away unread.
CACHE_KEY = "btc-zar-history"

# What a price becomes on its way to a chart, which has never needed more than two places. The
# history is floats, being a reading of the past rather than a rand on a return; the chart works
# in `Decimal`, so this is where the one turns into the other.
CENTS = Decimal("0.01")


def daily_zar(years=YEARS):
    """The daily BTC price in ZAR over the last `years`, oldest first, as `(date, float)`.

    Downloaded once a day and held: the closes behind today cannot move, and the analysis is a
    reading of the past rather than of this minute. A download that does not work out falls back on
    whatever is cached, and returns nothing at all if there is nothing cached either — the page
    then says the history could not be downloaded rather than drawing an empty chart.
    """
    held = cache.get(CACHE_KEY)
    today = timezone.localdate()
    if held and held.get("fetched_on") == today and held.get("years") == years:
        return held["series"]

    series = _download(years)
    if not series:
        return held["series"] if held else []
    cache.set(CACHE_KEY, {"fetched_on": today, "years": years, "series": series})
    return series


def lead(day, days):
    """The `days` daily closes ending the day before `day`, oldest first, as `(date, Decimal)`.

    What sits behind the price chart's window so that its long average and its change strip have a
    figure on the window's very first day rather than starting part way across it. It is a
    different provider from the window itself, which is the price of reaching back past the year
    CoinGecko serves — one source over the whole lead and one seam where the two meet, rather than
    the two alternating day by day.

    Nothing at all when the history cannot reach that far back: a short lead would put the very
    thing back that this is here to remove, so the average and the strip are left off the chart
    instead of drawn starting late.
    """
    earlier = [(date, price) for date, price in daily_zar() if date < day]
    if len(earlier) < days:
        return []
    return [(date, Decimal(price).quantize(CENTS)) for date, price in earlier[-days:]]


def within(series, years):
    """The last `years` of a series, counted back from its final day.

    The window the analysis is run over. Asking for more years than the history holds gives the
    whole of it rather than an error — the page prints the dates it actually covered, which is the
    honest answer to how long a window really was.
    """
    if not series:
        return []
    cutoff = series[-1][0] - dt.timedelta(days=round(years * DAYS_PER_YEAR))
    return [(day, price) for day, price in series if day >= cutoff]


def _download(years):
    """Both quotes, combined into one price. Either one missing leaves nothing to combine."""
    bitcoin = _closes(BITCOIN, years)
    dollar = _closes(DOLLAR, years)
    if not bitcoin or not dollar:
        return []
    return _combine(bitcoin, dollar)


def _combine(bitcoin, dollar):
    """A dollar price of Bitcoin times a rand price of the dollar, day by day.

    The dollar rate is carried forward across the days the currency market is shut, since Bitcoin
    has a close on every one of them. Bitcoin days before the first rate held are dropped: a price
    with nothing to convert it is not a price in rands.
    """
    series = []
    zar_per_usd = None
    for day in sorted(set(bitcoin) | set(dollar)):
        zar_per_usd = dollar.get(day, zar_per_usd)
        usd_per_btc = bitcoin.get(day)
        if usd_per_btc is not None and zar_per_usd is not None:
            series.append((day, usd_per_btc * zar_per_usd))
    return series


def _closes(symbol, years):
    """The daily close of one symbol, keyed by date. A day quoted as null is simply not a day."""
    payload = _get_json(symbol, years)
    if not payload:
        return {}
    result = payload.get("chart", {}).get("result") or [{}]
    quote = result[0]
    stamps = quote.get("timestamp") or []
    quoted = (quote.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    return {
        dt.datetime.fromtimestamp(stamp, tz=dt.UTC).date(): float(close)
        for stamp, close in zip(stamps, quoted, strict=False)
        if close is not None
    }


def _get_json(symbol, years):
    """GET a Yahoo chart, returning None when the download does not work out.

    Swallowed and logged the way a missing rate is: the analysis page is a reading of history, and
    a provider having a bad day is worth a message on the page rather than an error at whoever
    opened it. `RATES_DOWNLOAD` switches this off with everything else, which is how tests run.
    """
    if not settings.RATES_DOWNLOAD:
        return None
    try:
        response = requests.get(
            f"{API_ROOT}/{symbol}",
            params={"range": f"{years}y", "interval": "1d"},
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        logger.warning("Could not download %s from Yahoo", symbol, exc_info=True)
        return None
