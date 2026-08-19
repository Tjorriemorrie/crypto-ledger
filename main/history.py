"""What the ledger held week by week, cached so it is not worked out twice.

The profit chart wants a figure per account per week over two years, which means running the ledger
forward from its very first transaction and pricing every account at every week's rates. A week
that has closed cannot move unless the ledger does — only today's rate is ever downloaded again —
so all of them go into Django's cache under a single key, and a boot or a page load works out the
week in progress, tops up any week that has turned over since, and takes the rest as they are.

The cache is a cache and nothing more. It is never the record of anything: every figure in it can
be worked out again from the transactions and the rates, so an entry that is missing or out of date
costs a recalculation and never a wrong number, and clearing it is always safe.

Out of date is worth being careful about, though, because any transaction here can be edited or
backdated. The weeks are stored beside a stamp of the accounts and entries they were read from, and
a stamp that no longer matches throws all of them away rather than only the recent ones — there is
no cheap way to tell which weeks a correction moved, and a chart drawn off a balance that has since
been corrected is worse than one worked out again.

Weeks are counted back from today in sevens rather than run off the calendar, so the last bar is
where the ledger stands now, every earlier one is the same weekday before it, and no bar is a part
week. A week is shown at its close: the latest day in it the ledger can price.
"""

import datetime as dt
import hashlib
import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

from main import rates
from main.models import GROUPS, ZERO, Account, Entry, group

logger = logging.getLogger(__name__)

WEEKS = 100
DAYS_PER_WEEK = 7

# The one key everything is kept under. Its name says what is stored there, so changing the shape
# of that means changing the name and letting the old entry fall away unread.
CACHE_KEY = "profit-history"

# A holding is rounded to the cent before it goes into a bar or into the cache. Valuing a quantity
# carrying eighteen decimal places at a rate carrying eighteen more leaves a figure with
# thirty-six, and a rand on a chart has never needed more than two.
CENTS = Decimal("0.01")


def profit_history(weeks=WEEKS):
    """What every account held at the close of each of the last `weeks` weeks, valued in ZAR.

    One bar of the profit chart per week, oldest first, each `{"date": date, "parts": [...]}` with
    every account in the same order: the money put in, then the stablecoins, then the crypto on
    top. Pricing a week at its own rates is what makes this a history rather than today's holdings
    drawn sideways.

    A week the ledger cannot price every account for is left out — the profit on it is not partly
    known, it is unknown. An account that is empty right across the window is left out too, since a
    flat nothing is a colour in the key that draws no bar.
    """
    closes = _weekly_closes(rates.priced_days(weeks * DAYS_PER_WEEK), weeks)
    if not closes:
        return []

    accounts = _stacking_order(Account.objects.all())
    entries = list(Entry.objects.select_related("account", "transaction"))
    ledger = _stamp(accounts, entries)
    cached = _cached_weeks(ledger)
    today = timezone.localdate()

    # The week in progress is always worked out again, since today's rate is the one that moves.
    # Everything else only needs its prices read if the cache is missing it, which on the usual
    # load is nothing at all.
    outstanding = [close for close in closes if close >= today or close not in cached]
    prices = rates.prices_on(outstanding) if outstanding else {}

    held_by_close = {}
    balances = dict.fromkeys(accounts, ZERO)
    position = 0
    for close in closes:
        # The balance has to be run forward through every week, cached or not, since a later week
        # that is not cached needs to start from the right place.
        while position < len(entries) and entries[position].transaction.occurred_on <= close:
            balances[entries[position].account] += entries[position].quantity
            position += 1
        held = cached.get(close) if close < today else None
        if held is None:
            held = _week_held(accounts, balances, prices[close])
        if held is not None:
            held_by_close[close] = held

    # A load that changed nothing leaves the cache alone rather than writing back what it read.
    if held_by_close != cached:
        cache.set(CACHE_KEY, {"ledger": ledger, "weeks": held_by_close})
    return _series(accounts, held_by_close)


def warm():
    """Work the weeks out as the server comes up, so the first chart load has them in hand.

    Called from `wsgi.py`, so it runs once per server start and never for a management command or
    a test run. A database that has not been migrated yet is a warning, not a crash.
    """
    try:
        profit_history()
    except DatabaseError:
        logger.warning("Skipped warming the profit cache: run migrate first.")


def _cached_weeks(ledger):
    """The weeks in the cache, keyed by their close, or nothing if they cannot be trusted.

    Nothing when the cache holds no entry, or when the ledger has changed since it was written — a
    corrected or backdated transaction can move any week, so none of them survives it. The window
    the entry was written for does not come into it: a week is keyed by the day it closed, so any
    week in there is still that week whether a hundred of them are being drawn or three.
    """
    entry = cache.get(CACHE_KEY)
    if not entry or entry.get("ledger") != ledger:
        return {}
    return entry.get("weeks", {})


def _stamp(accounts, entries):
    """A fingerprint of everything about the ledger a week's figures are read from.

    The account names are in it as well as the entries, since they are what the bars are labelled
    with. Both are already in hand for the balances, so this costs a hash and no query.
    """
    digest = hashlib.sha256()
    for account in accounts:
        digest.update(repr((account.pk, account.name, account.currency)).encode())
    for entry in entries:
        digest.update(
            repr((entry.account_id, entry.quantity, entry.transaction.occurred_on)).encode()
        )
    return digest.hexdigest()


def _weekly_closes(priced, weeks):
    """The day each of the last `weeks` weeks is shown at, oldest first.

    A week is taken at its latest day the ledger can price, which is the week's own close rather
    than an average of its seven days. A week with no such day is not shown at all.

    These are worked out from the days actually priced rather than read off the cache, so a week
    whose close moves — an old date downloaded for the first time — comes out as a week the cache
    does not hold, and is worked out again instead of quietly keeping the older day's figures.
    """
    today = timezone.localdate()
    closes = []
    for week in reversed(range(weeks)):
        end = today - dt.timedelta(days=week * DAYS_PER_WEEK)
        for offset in range(DAYS_PER_WEEK):
            day = end - dt.timedelta(days=offset)
            if day in priced:
                closes.append(day)
                break
    return closes


def _week_held(accounts, balances, prices):
    """Every account's holding valued at one week's prices, or None if one of them cannot be.

    All or nothing: a week missing a single account's value would draw a bar that is not the
    profit, which is worse on a chart than a week that is simply not there.
    """
    held = {}
    for account in accounts:
        value = rates.value_with(balances[account], account.currency, prices)
        if value is None:
            return None
        held[account.name] = value.quantize(CENTS)
    return held


def _stacking_order(accounts):
    """Accounts in the order they stack, from the axis outwards, `GROUPS` deciding the groups.

    The crypto ends up on top because it is the only holding whose price moves, so it is the
    segment that changes shape from one week to the next — under a block that does not move, its
    own movement would be impossible to follow.
    """
    return sorted(
        accounts, key=lambda account: (GROUPS.index(group(account.currency)), account.name)
    )


def _series(accounts, held_by_close):
    """The weeks as the chart takes them, with the accounts that never held anything dropped."""
    labels = [
        account.name
        for account in accounts
        if any(held.get(account.name) for held in held_by_close.values())
    ]
    return [
        {
            "date": close,
            "parts": [{"label": label, "value": held.get(label, ZERO)} for label in labels],
        }
        for close, held in held_by_close.items()
    ]
