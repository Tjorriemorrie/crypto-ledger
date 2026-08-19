"""Turning Yahoo's two quotes into one daily Bitcoin price in rands."""

import datetime as dt
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone

from main import prices

DAY = dt.date(2026, 1, 1)


def test_the_price_is_bitcoin_in_dollars_times_the_dollar_in_rands():
    bitcoin = {DAY: 100000.0, DAY + dt.timedelta(days=1): 110000.0}
    # The currency market is shut on the second day, so its rate is carried forward.
    dollar = {DAY: 20.0}

    assert prices._combine(bitcoin, dollar) == [
        (DAY, 2000000.0),
        (DAY + dt.timedelta(days=1), 2200000.0),
    ]


def test_a_window_takes_the_last_years_of_the_history():
    series = [(DAY + dt.timedelta(days=day), float(day)) for day in range(1000)]

    window = prices.within(series, 1)

    # Counted back from the last day priced, so the window ends where the history does.
    assert window[-1] == series[-1]
    assert len(window) == 366


def test_the_lead_is_the_days_before_the_window_it_sits_behind():
    series = [(DAY + dt.timedelta(days=day), float(day)) for day in range(10)]
    cache.set(
        prices.CACHE_KEY,
        {"fetched_on": timezone.localdate(), "years": prices.YEARS, "series": series},
    )

    behind = prices.lead(DAY + dt.timedelta(days=8), 3)

    assert behind == [
        (DAY + dt.timedelta(days=5), Decimal("5.00")),
        (DAY + dt.timedelta(days=6), Decimal("6.00")),
        (DAY + dt.timedelta(days=7), Decimal("7.00")),
    ]
