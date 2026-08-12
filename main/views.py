"""Views for browsing accounts and entering transactions."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from main import cgt
from main.forms import AccountEditForm, AccountForm, TransactionForm
from main.matching import rebuild_account_matching, unmatched_totals
from main.models import BASE_CURRENCY, STABLECOINS, ZERO, Account, Entry, Transaction
from main.rates import refresh_current_rates, to_zar


def account_list(request):
    """The home page: every account, its balance, and what the lot is worth in ZAR.

    The values are also totalled three ways. The ZAR accounts are the investment — cash put in
    counts against the ledger, so the money spent on crypto sits there negative — and
    everything else is what that money is now holding, split into stablecoins and the crypto
    whose price can actually move. The whole lot summed is therefore the profit or the loss.
    """
    rows = []
    subtotals = dict.fromkeys(_BUCKETS, ZERO)
    for account in Account.objects.all():
        balance = account.balance
        value = to_zar(balance, account.currency)
        if value is not None:
            subtotals[_bucket(account.currency)] += value
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


_BUCKETS = ("investment", "crypto", "stablecoins")


def _bucket(currency):
    """Which of the accounts page's subtotals a currency's value belongs to."""
    if currency == BASE_CURRENCY:
        return "investment"
    if currency in STABLECOINS:
        return "stablecoins"
    return "crypto"


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

    Reached from the icon on every row of an account page. The account is in the URL only so
    the page knows where it was opened from — the gain itself is the same whichever side of
    the transaction you click.
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


def _back_to_row(account, transaction):
    """The account page, anchored on one transaction so it lands scrolled to and highlighted."""
    return redirect(f"{account.get_absolute_url()}#tx{transaction.pk}")


def _entry_rows(account):
    """Build the account's entry list, newest first, with running balances.

    Each entry is also valued in ZAR at the rate for the date it happened — what it was worth
    at the time, not what the same quantity would fetch today. Dates the ledger has no rate
    for are downloaded here, once each; a date that cannot be downloaded shows no value.
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
            }
        )
    # Only the newest row can offer a delete, and only while the other account it touches has
    # nothing after it either.
    if rows:
        rows[-1]["deletable"] = rows[-1]["entry"].transaction.is_last
    rows.reverse()
    return rows
