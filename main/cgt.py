"""Working out the capital gain on a disposal, for the tax return.

Every transaction that gives up a crypto is a disposal in its own right — sold for rands or
swapped for another crypto, it makes no difference — and each one is declared on its own. So a
disposal's base cost is what its lots cost on the days they were acquired, and the trail stops
there: the swap that acquired a lot was itself a disposal, declared at the time, and the
proceeds declared on it are this lot's cost. One rule, applied once per transaction, and the
figures tie together across the whole return.

There is deliberately no second way of arriving at a base cost. Chasing every swap back to the
rands that originally started it gives a different, equally arguable number, and handing a
return two answers to the same question is worse than either of them.

Nothing here writes to the database. It reads the matches `matching.py` made and prices them.
"""

import datetime as dt
from decimal import Decimal

from django.db.models import Max, Min
from django.utils import timezone

from main.models import BASE_CURRENCY, QUANTITY_DECIMAL_PLACES, ZERO, Transaction
from main.rates import rate_used, to_zar

ONE = Decimal(1)
SMALLEST_UNIT = Decimal(1).scaleb(-QUANTITY_DECIMAL_PLACES)
CENT = Decimal("0.01")

# SARS runs its tax year from 1 March to the end of February, and names it for the February it
# ends in: the 2026 year ran from 1 March 2025 to 28 February 2026.
TAX_YEAR_START_MONTH = 3

# Below this, a shortfall is not a disposal nobody accounted for, it is arithmetic. SQLite sums
# decimals as floats, so a fully matched credit can come back a hundredth of a satoshi short;
# a hand-kept ledger has nothing genuinely that small to report.
DUST = Decimal("0.000000000001")


def tax_year_dates(tax_year):
    """The first and last day of a tax year, named for the February it ends in."""
    return (
        dt.date(tax_year - 1, TAX_YEAR_START_MONTH, 1),
        dt.date(tax_year, TAX_YEAR_START_MONTH, 1) - dt.timedelta(days=1),
    )


def tax_year_of(day):
    """Which tax year a date falls in."""
    return day.year + 1 if day.month >= TAX_YEAR_START_MONTH else day.year


def latest_closed_tax_year():
    """The most recent tax year to have ended — the one there is a return to file for.

    That is what the report should open on. The year in progress is worth a look, but it is
    not the one being declared, and defaulting to it would show a half-finished figure.
    """
    return tax_year_of(timezone.localdate()) - 1


def tax_years():
    """The tax years worth offering, newest first: every year the ledger touches.

    Always including the one there is a return to file for, so the report has something to open
    on before a single transaction is recorded.
    """
    latest = latest_closed_tax_year()
    span = Transaction.objects.aggregate(first=Min("occurred_on"), last=Max("occurred_on"))
    if span["first"] is None:
        return [latest]
    first = min(tax_year_of(span["first"]), latest)
    last = max(tax_year_of(span["last"]), latest)
    return list(range(last, first - 1, -1))


def selected_tax_year(raw):
    """The tax year a page was asked for, falling back to the one being declared."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return latest_closed_tax_year()


def report(tax_year):
    """Every disposal in one tax year, priced, with the totals to declare.

    Only disposals: buying crypto with rands and an asset simply arriving create a base cost
    but give up nothing, so there is no gain on them to return. Each row is the same
    calculation `trace` shows in full on its own page, so the two can never disagree.
    """
    start, end = tax_year_dates(tax_year)
    transactions = (
        Transaction.objects.filter(occurred_on__range=(start, end))
        .prefetch_related("entries__account")
        .order_by("occurred_on", "id")
    )

    rows = []
    proceeds = ZERO
    base_cost = ZERO
    gain = ZERO
    complete = True
    for transaction in transactions:
        result = trace(transaction)
        if result["kind"] != "disposal":
            continue
        rows.append({"transaction": transaction, **result})
        proceeds += result["proceeds"] or ZERO
        base_cost += result["base_cost"] or ZERO
        gain += result["gain"] or ZERO
        complete = complete and result["complete"] and result["gain"] is not None

    return {
        "tax_year": tax_year,
        "start": start,
        "end": end,
        "rows": rows,
        "proceeds": proceeds,
        "base_cost": base_cost,
        "gain": gain,
        "complete": complete,
    }


def trace(transaction):
    """Work out a transaction's proceeds, base cost and gain, and the lots behind them.

    The disposal is the credit side: the asset that left. A transaction crediting rands is not
    a disposal at all — it is spending the base currency to buy a lot — and one with no credit
    at all is an asset arriving from outside the ledger. Both still have a base cost worth
    seeing, so they get a page too, just without a gain on it.
    """
    entries = list(transaction.entries.select_related("account", "transaction").all())
    disposal = next((entry for entry in entries if entry.is_credit), None)
    acquired = next((entry for entry in entries if entry.is_debit), None)

    if disposal is None:
        return _arrival(acquired)
    if disposal.account.currency == BASE_CURRENCY:
        return _purchase(disposal, acquired)

    lots = _lots(disposal)
    base_cost, complete = _cost_of(lots)
    proceeds = _proceeds(disposal, acquired)
    _apportion(lots, proceeds, -disposal.quantity)
    return _result(
        kind="disposal",
        disposal=disposal,
        acquired=acquired,
        quantity=-disposal.quantity,
        proceeds=proceeds,
        base_cost=base_cost,
        gain=None if proceeds is None else proceeds - base_cost,
        complete=complete,
        rows=lots,
        rate=_proceeds_rate(disposal, acquired),
    )


def _purchase(disposal, acquired):
    """Rands going out: not a disposal, since the base currency cannot gain against itself.

    What left the bank is the base cost of whatever it bought, whether or not the ledger keeps
    an account for the other side.
    """
    return _result(
        kind="purchase",
        disposal=disposal,
        acquired=acquired,
        quantity=-disposal.quantity,
        base_cost=-disposal.quantity,
    )


def _arrival(acquired):
    """An asset arriving with no other side: its base cost is what it was worth that day."""
    on = acquired.transaction.occurred_on
    cost = to_zar(acquired.quantity, acquired.account.currency, on=on)
    return _result(
        kind="arrival",
        acquired=acquired,
        quantity=acquired.quantity,
        base_cost=cost,
        complete=cost is not None,
        rate=rate_used(acquired.account.currency, on),
    )


def _result(**fields):
    """One shape for every kind of page, so the template never has to test for a missing key."""
    return {
        "kind": "disposal",
        "disposal": None,
        "acquired": None,
        "quantity": ZERO,
        "proceeds": None,
        "base_cost": None,
        "gain": None,
        "complete": True,
        "rows": [],
        # What the rand figures were worked out from: the question a return asks that the
        # amounts alone do not answer.
        "rate": None,
        **fields,
    }


def _proceeds_rate(disposal, acquired):
    """The rate the proceeds were valued at, or None when rands made one unnecessary."""
    on = disposal.transaction.occurred_on
    if acquired is None:
        return rate_used(disposal.account.currency, on)
    if acquired.account.currency == BASE_CURRENCY:
        return None
    return rate_used(acquired.account.currency, on)


def _apportion(lots, proceeds, quantity):
    """Give every lot its share of the proceeds, so each one is a whole line for the return.

    A return wants a date acquired against a disposal, and a disposal that consumed three lots
    has three of them — so it goes on as three lines, each with the share of the proceeds that
    lot earned. The split is pro rata by quantity and rounded to the cent, with the last lot
    taking the rounding so the lines still add up to the proceeds exactly.
    """
    if proceeds is None or not quantity:
        return
    remaining = proceeds.quantize(CENT)
    for index, lot in enumerate(lots):
        last = index == len(lots) - 1
        share = remaining if last else (proceeds * _share(lot["quantity"], quantity)).quantize(CENT)
        remaining -= share
        lot["proceeds"] = share
        lot["gain"] = None if lot["cost"] is None else share - lot["cost"]


def _proceeds(disposal, acquired):
    """What came in for the disposal, in rands, on the day it happened.

    Rands received are the proceeds exactly; anything else is valued at that date's rate. This
    is the same measure a lot's base cost uses, which is what makes the two sides of a swap
    agree: the proceeds declared here are the cost of the lot that came out of it.
    """
    on = disposal.transaction.occurred_on
    if acquired is None:
        return to_zar(-disposal.quantity, disposal.account.currency, on=on)
    if acquired.account.currency == BASE_CURRENCY:
        return acquired.quantity
    return to_zar(acquired.quantity, acquired.account.currency, on=on)


def _lots(credit):
    """The acquisitions FIFO consumed for `credit`, oldest first, each with what it cost.

    Whatever the matches do not cover comes back as an unmatched row — a disposal with no
    acquisition behind it has no base cost to put against it, and saying so beats guessing.
    """
    matches = (
        credit.matches_as_credit.select_related("debit__account", "debit__transaction")
        .prefetch_related("debit__transaction__entries__account")
        .order_by("debit__transaction__occurred_on", "debit_id")
    )

    lots = []
    used = ZERO
    for match in matches:
        used += match.quantity
        lots.append(_lot(match.debit, match.quantity))

    short = -credit.quantity - used
    if short > DUST:
        lots.append(_unmatched(credit, short))
    return lots


def _lot(debit, quantity):
    """One acquisition, the share of it this disposal used, and what that share cost.

    Bought with rands, a lot cost exactly what left the bank — there is no rate involved and
    none is wanted. Bought with another crypto, that swap was a disposal of its own, and the
    lot cost what it was worth on the day it arrived, which is the very figure declared as the
    proceeds of that swap. Arriving from outside the ledger, the same day's value is all there
    is to go on.
    """
    on = debit.transaction.occurred_on
    lot = _row(
        entry=debit,
        account=debit.account,
        quantity=quantity,
        occurred_on=on,
        cost=to_zar(quantity, debit.account.currency, on=on),
        rate=rate_used(debit.account.currency, on),
    )

    paid = debit.counterpart
    if paid is None or not paid.is_credit:
        lot["source"] = "outside"
    else:
        lot["paid"] = paid
        lot["paid_quantity"] = _round(-paid.quantity * _share(quantity, debit.quantity))
        if paid.account.currency == BASE_CURRENCY:
            lot["source"] = "cash"
            lot["cost"] = lot["paid_quantity"]
            # Rands are the cost exactly. Showing the day's rate beside them would suggest the
            # figure came off a price, and a return should say where a number actually came from.
            lot["rate"] = None
        else:
            lot["source"] = "swap"

    lot["complete"] = lot["cost"] is not None
    return lot


def _unmatched(credit, quantity):
    """The part of a disposal FIFO found nothing to match, and so can put no cost against."""
    return _row(
        entry=credit,
        account=credit.account,
        quantity=quantity,
        occurred_on=credit.transaction.occurred_on,
        source="unmatched",
        complete=False,
    )


def _row(**fields):
    """One shape for every line of the lot table."""
    return {
        "source": "outside",
        "cost": None,
        "complete": True,
        "paid": None,
        "paid_quantity": None,
        # The share of the proceeds this lot earned and the gain on it, so the lot is a line
        # for the return on its own. Filled in by `_apportion` once the proceeds are known.
        "proceeds": None,
        "gain": None,
        "rate": None,
        **fields,
    }


def _cost_of(lots):
    """Add up what the lots cost, and say whether every one of them could be priced."""
    total = ZERO
    complete = True
    for lot in lots:
        if lot["cost"] is None:
            complete = False
        else:
            total += lot["cost"]
        complete = complete and lot["complete"]
    return total, complete


def _share(part, whole):
    """How much of `whole` is `part`, exactly 1 when the whole of it was used."""
    if not whole:
        return ZERO
    if part == whole:
        return ONE
    return part / whole


def _round(quantity):
    """Hold a scaled quantity to the ledger's own precision, not the division's 28 digits."""
    return quantity.quantize(SMALLEST_UNIT)
