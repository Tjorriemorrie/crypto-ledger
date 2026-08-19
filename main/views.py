"""Views for browsing accounts and entering transactions."""

import math

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from main import backtest, cgt, chart, history, preferences, prices, rates
from main.forms import (
    AccountEditForm,
    AccountForm,
    PlanForm,
    SweepForm,
    TransactionForm,
    grid_of,
)
from main.matching import rebuild_account_matching, unmatched_totals
from main.models import GROUPS, ZERO, Account, Entry, RatedAsset, Transaction, group
from main.rates import refresh_current_rates, to_zar

# How many requests a sweep takes, whatever size the grid is set to. Enough that results start
# landing straight away, few enough that the page is not re-treading the same ground all day.
SLICES = 12

# The analysis page has no prices of its own to fall back on, so a download that did not work out
# is said plainly rather than drawn as an empty chart.
NO_PRICES = (
    "Could not download the price history. The analysis is run over daily Bitcoin prices and none "
    "are held — try again once there is a connection."
)

# Every slice is read back through the form, so a hand-edited query string is turned away here.
BAD_GRID = "Those are not settings this page can sweep. Set the ranges again and press Run."


def account_list(request):
    """The home page: every account, its balance, and what the lot is worth in ZAR.

    The values are also totalled three ways. The ZAR accounts are the investment — cash put in
    counts against the ledger, so the money spent on crypto sits there negative — and
    everything else is what that money is now holding, split into stablecoins and the crypto
    whose price can actually move. The whole lot summed is therefore the profit or the loss.
    """
    rows = []
    subtotals = dict.fromkeys(GROUPS, ZERO)
    for account in Account.objects.all():
        balance = account.balance
        value = to_zar(balance, account.currency)
        if value is not None:
            subtotals[group(account.currency)] += value
        rows.append({"account": account, "balance": balance, "value": value})
    crypto_assets = subtotals["crypto"] + subtotals["stablecoins"]
    return render(
        request,
        "main/account_list.html",
        {
            "rows": rows,
            "total": subtotals["investment"] + crypto_assets,
            "investment": subtotals["investment"],
            "crypto_assets": crypto_assets,
            "crypto": subtotals["crypto"],
            "stablecoins": subtotals["stablecoins"],
        },
    )


def price_chart(request):
    """The BTC price chart under the accounts list, fetched by htmx once the page is up.

    It is its own request because filling the window in can mean a download, and the balances
    are the point of the page — they should not sit waiting on a price provider. The window is
    downloaded once and kept, so every later load reads it straight out of the database.

    The days drawn are the ledger's own rates and the lead behind them is the analysis page's
    longer history, since the moving averages and the strip both look back further than the year
    CoinGecko will serve and would otherwise begin part way across the window. The lead is never
    drawn and never stored — it only gives the lines a figure on the window's first day.
    """
    window = rates.btc_history(chart.DAYS)
    lead = prices.lead(window[0][0], chart.LEAD_DAYS) if window else []
    return render(
        request,
        "main/price_chart.html",
        {"chart": chart.price_chart(lead + window, RatedAsset.BTC), "days": chart.DAYS},
    )


def profit_chart(request):
    """The profit chart between the accounts page's totals and its list, fetched by htmx.

    Its own request for the same reason the price chart is: filling the window in can mean a
    download, and the balances are the point of the page. The weeks themselves come off the cache
    `history.py` keeps, so all this normally works out is the week in progress.
    """
    return render(
        request,
        "main/profit_chart.html",
        {"chart": chart.profit_chart(history.profit_history()), "weeks": history.WEEKS},
    )


@require_POST
def rate_refresh(request):
    """Download the rates again, for when the ones from startup have gone stale.

    The button is in the navbar, so it comes back to the page it was pressed on rather than
    dropping you at the accounts list from wherever you were.
    """
    rates = refresh_current_rates()
    if rates:
        messages.success(request, "Downloaded " + ", ".join(str(rate) for rate in rates.values()))
    else:
        messages.error(request, "Could not download the rates.")
    back = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts=None):
        back = reverse("account-list")
    return redirect(back)


def account_create(request):
    form = AccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = form.save()
        messages.success(request, f"Created {account}.")
        return redirect(account)
    return render(request, "main/account_form.html", {"form": form})


def account_edit(request, pk):
    """Rename an account or reword its note. The currency it holds cannot be changed."""
    account = get_object_or_404(Account, pk=pk)
    form = AccountEditForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        account = form.save()
        messages.success(request, f"Saved {account}.")
        return redirect(account)
    return render(request, "main/account_form.html", {"form": form, "account": account})


def account_detail(request, pk):
    account = get_object_or_404(Account, pk=pk)
    balance = account.balance
    return render(
        request,
        "main/account_detail.html",
        {
            "account": account,
            "rows": _entry_rows(account),
            "balance": balance,
            "value": to_zar(balance, account.currency),
            "unmatched": unmatched_totals(account),
        },
    )


def transaction_create(request, pk):
    account = get_object_or_404(Account, pk=pk)
    form = TransactionForm(request.POST or None, account=account)
    if request.method == "POST" and form.is_valid():
        transaction = form.save()
        messages.success(request, "Transaction recorded.")
        return _back_to_row(account, transaction)
    return render(request, "main/transaction_form.html", {"form": form, "account": account})


def transaction_edit(request, pk, transaction_pk):
    """Correct a transaction: its date, its quantities, the account facing it, its matching.

    Any of those can change which lots FIFO should have consumed, so saving replays the
    matching on every account the transaction touches — unlike deleting, which is barred for
    anything but the last transaction because it leaves the later matching with nothing to
    stand on.
    """
    account = get_object_or_404(Account, pk=pk)
    transaction = get_object_or_404(Transaction, pk=transaction_pk, entries__account=account)
    form = TransactionForm(request.POST or None, account=account, instance=transaction)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Transaction updated.")
        return _back_to_row(account, transaction)
    return render(
        request,
        "main/transaction_form.html",
        {"form": form, "account": account, "transaction": transaction},
    )


@require_POST
def transaction_delete(request, pk, transaction_pk):
    """Undo the last transaction on an account, every side of it and any matches it made.

    Only the last one: deleting an earlier transaction would pull a lot out from under the
    FIFO matching that came after it.

    Even the last one can take a lot with it, though. Transactions dated the same day are
    matched in the order they were entered, so a credit can have consumed a debit recorded
    after it; deleting that debit cascades the match away and would leave the credit short. So
    the accounts it touched are replayed once it has gone.
    """
    account = get_object_or_404(Account, pk=pk)
    transaction = get_object_or_404(Transaction, pk=transaction_pk, entries__account=account)
    if not transaction.is_last:
        messages.error(
            request,
            "Only the last transaction can be deleted — an earlier one is already matched "
            "against by the transactions after it.",
        )
        return redirect(account)

    touched = [entry.account for entry in transaction.entries.select_related("account")]
    transaction.delete()
    for touched_account in touched:
        rebuild_account_matching(touched_account)
    messages.success(request, "Transaction deleted.")
    return redirect(account)


def transaction_cgt(request, pk, transaction_pk):
    """The capital gain on one transaction, and the flow of transactions it was traced through.

    Reached from the icon on the rows that give up a crypto — the disposal itself, and the rand
    row facing it on a sale, which comes here to the wallet the crypto left rather than to the
    bank it was read from. The account is in the URL only so the page knows where to go back to;
    the gain itself is the same whichever side of the transaction you click.
    """
    account = get_object_or_404(Account, pk=pk)
    transaction = get_object_or_404(Transaction, pk=transaction_pk, entries__account=account)
    result = cgt.trace(transaction)
    return render(
        request,
        "main/transaction_cgt.html",
        {"account": account, "transaction": transaction, **result},
    )


def cgt_report(request):
    """Every disposal in one tax year, with the totals to put on the return.

    The year comes off the navbar's dropdown as `?year=`, and defaults to the last one to have
    ended — the one there is actually a return to file for.
    """
    tax_year = cgt.selected_tax_year(request.GET.get("year"))
    return render(request, "main/cgt_report.html", cgt.report(tax_year))


def analysis(request):
    """Two weekly investment plans swept over a decade of Bitcoin prices, to see what each came to.

    The page opens on the ranges to sweep and waits: nothing is worked out until Run is pressed,
    since a grid the size of this one is worth choosing rather than being handed. Pressing it puts
    the ranges in the query string, and the sweep then arrives in slices from `analysis_sweep`, so
    the results can be watched filling in rather than sat in front of a blank page until the whole
    grid is done. The settings behind a sweep that ran are kept, so the page opens where it was
    left rather than back at the defaults every time the server comes up. Nothing here touches an
    account — it is a reading of history, and the ledger records nothing of it.
    """
    running = "run" in request.GET
    opening = SweepForm.opening()
    form = SweepForm(request.GET) if running else SweepForm(initial=opening)
    ran = running and form.is_valid()
    if ran:
        # The page opens on the last sweep that ran, so it is kept the moment one does.
        preferences.remember(form.cleaned_data)
    # The note beside the button counts the grid the sliders are actually drawn at, which is
    # the sweep being run, or the one remembered, or the defaults behind both.
    opened = form.grid() if ran else grid_of(opening) if opening else None
    return render(
        request,
        "main/analysis.html",
        {
            "form": form,
            "query": urlencode(form.query()) if ran else None,
            "default": backtest.count(opened),
            "most": backtest.MAX_COMBINATIONS,
            # The sliders work the grid's size out as they are dragged, and both plans are always
            # in it, so they need to know how many that is.
            "plans": len(backtest.PLANS),
        },
    )


def analysis_sweep(request):
    """One slice of the sweep, and the results of every slice up to it.

    Fetched by htmx, and it asks for the next slice itself until the grid is done, so the page
    fills in on its own. The grid and `?done=` are the whole of the state: the grid is a fixed list
    run in a fixed order, so a slice is just a stretch of it and the whole prefix can be worked out
    again from the query string alone — no run to keep hold of, nothing to go stale between
    requests, and a slice that is asked for twice gives the same answer both times.
    """
    form = SweepForm(request.GET)
    if not form.is_valid():
        return render(request, "main/analysis_sweep.html", {"finished": True, "problem": BAD_GRID})

    grid = form.grid()
    total = backtest.count(grid)
    done = min(max(_whole(request.GET.get("done")), 0) + _batch(total), total)
    years = form.cleaned_data["years"]
    # The whole history is downloaded once and the window trims it, so moving the window costs a
    # slice of a list rather than another download.
    series = prices.within(prices.daily_zar(), years)
    if not series:
        return render(request, "main/analysis_sweep.html", {"finished": True, "problem": NO_PRICES})

    days = [day for day, _ in series]
    closes = [price for _, price in series]
    fee = form.cleaned_data["fee"]
    results = backtest.search(closes, done, grid, fee)
    if not results:
        return render(
            request, "main/analysis_sweep.html", {"finished": True, "problem": _too_short(years)}
        )
    leader = backtest.best(results)
    # The sweep keeps no weeks, so the leader's are run again for the chart — one walk through the
    # history, against the hundreds of megabytes keeping every combination's would have cost.
    run = backtest.replay(closes, leader) if leader else None
    # The baseline runs from the leader's own first week, so the two were handed the same money over
    # the same weeks and the difference between them is only what the plan did with it.
    baseline = backtest.hold(closes, fee, leader["long"] - 1) if leader else None
    return render(
        request,
        "main/analysis_sweep.html",
        {
            "done": done,
            "total": total,
            "progress": round(done / total * 100),
            "finished": done >= total,
            "query": urlencode(form.query()),
            "years": years,
            "results": results,
            "best": leader,
            "baseline": baseline,
            "against_baseline": leader["profit"] - baseline["profit"] if baseline else None,
            "report": backtest.report(results),
            # The chart names its own series, so it is handed labels rather than the plans
            # themselves — it has no business knowing what a strategy is.
            "sweep": chart.results_chart(
                [{"label": result["plan"], "profit": result["profit"]} for result in results],
                total,
                baseline["profit"] if baseline else None,
            ),
            "equity": chart.profit_chart(backtest.equity_weeks(run, days)) if run else None,
            "first": days[0],
            "last": days[-1],
        },
    )


def analysis_plan(request):
    """One combination out of a sweep, week by week, so its every move can be read.

    The sweep keeps only what each combination came to, so this runs the plan again from the four
    numbers naming it in the query string. That is cheaper than it sounds — one walk through the
    history — and it means a row's button needs nothing kept for it between the two pages.
    """
    form = PlanForm(request.GET)
    if not form.is_valid():
        return render(request, "main/analysis_plan.html", {"form": form})

    combo = form.combination()
    years = form.cleaned_data["years"]
    series = prices.within(prices.daily_zar(), years)
    result = backtest.replay([price for _, price in series], combo) if series else None
    if result is None:
        problem = _too_short(years) if series else NO_PRICES
        return render(
            request, "main/analysis_plan.html", {"form": form, "combo": combo, "problem": problem}
        )

    days = [day for day, _ in series]
    closes = [price for _, price in series]
    # From this plan's own first week, so the two were handed the same money over the same weeks.
    baseline = backtest.hold(closes, combo["fee"], combo["long"] - 1)
    return render(
        request,
        "main/analysis_plan.html",
        {
            "form": form,
            "combo": combo,
            "years": years,
            "result": result,
            "baseline": baseline,
            "against_baseline": result["profit"] - baseline["profit"] if baseline else None,
            "weeks": [week | {"date": days[week["day"]]} for week in reversed(result["weeks"])],
            "equity": chart.profit_chart(backtest.equity_weeks(result, days)),
            "first": days[0],
            "last": days[-1],
        },
    )


def _too_short(years):
    """What to say when the window holds fewer weeks than the averages asked of it need."""
    return (
        f"A {years}-year window is too short for the averages set: no combination has enough "
        f"weeks behind it to read. Widen the window or shorten the averages."
    )


def _batch(total):
    """How many combinations one request works through, so any grid is about `SLICES` of them.

    Scaled to the grid rather than fixed, since a request works out every combination up to its own
    end: a fixed batch would deliver a small grid in one lump, and a large one in hundreds of
    requests each re-treading everything the one before it had already done.
    """
    return max(math.ceil(total / SLICES), 1)


def _whole(value):
    """A count out of a query string, and 0 for anything that is not one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _back_to_row(account, transaction):
    """The account page, anchored on one transaction so it lands scrolled to and highlighted."""
    return redirect(f"{account.get_absolute_url()}#tx{transaction.pk}")


def _entry_rows(account):
    """Build the account's entry list, newest first, with running balances.

    Each entry is also valued in ZAR at the rate for the date it happened — what it was worth
    at the time, not what the same quantity would fetch today. Dates the ledger has no rate
    for are downloaded here, once each; a date that cannot be downloaded shows no value.

    Each row also carries the account whose capital gain page it reaches, which is nothing at
    all on the rows that give up no crypto.
    """
    entries = list(
        Entry.objects.filter(account=account)
        .select_related("transaction")
        .prefetch_related("transaction__entries__account")
        .order_by("transaction__occurred_on", "id")
    )

    rows = []
    balance = ZERO
    for entry in entries:
        balance += entry.quantity
        rows.append(
            {
                "entry": entry,
                "quantity": abs(entry.quantity),
                "balance": balance,
                "value": to_zar(
                    abs(entry.quantity), account.currency, on=entry.transaction.occurred_on
                ),
                "deletable": False,
                # Which account's capital gain page this row reaches, if any: only the rows
                # that give up a crypto have a gain to declare.
                "cgt_account": cgt.disposal_account(entry),
            }
        )
    # Only the newest row can offer a delete, and only while the other account it touches has
    # nothing after it either.
    if rows:
        rows[-1]["deletable"] = rows[-1]["entry"].transaction.is_last
    rows.reverse()
    return rows
