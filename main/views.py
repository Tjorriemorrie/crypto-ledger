"""Views for browsing accounts and entering transactions."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from main.forms import AccountEditForm, AccountForm, TransactionForm
from main.matching import match_credit_fifo, matched_quantity_by_entry, unmatched_totals
from main.models import ZERO, Account, Entry, Transaction
from main.rates import latest_rates, refresh_current_rates, to_zar


def account_list(request):
    """The home page: every account, its balance, and what the lot is worth in ZAR."""
    rows = []
    total = ZERO
    for account in Account.objects.all():
        balance = account.balance
        value = to_zar(balance, account.currency)
        if value is not None:
            total += value
        rows.append({"account": account, "balance": balance, "value": value})
    return render(
        request,
        "main/account_list.html",
        {"rows": rows, "total": total, "rates": latest_rates()},
    )


@require_POST
def rate_refresh(request):
    """Download the rates again, for when the ones from startup have gone stale."""
    rates = refresh_current_rates()
    if rates:
        messages.success(request, "Downloaded " + ", ".join(str(rate) for rate in rates.values()))
    else:
        messages.error(request, "Could not download the rates.")
    return redirect("account-list")


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
        form.save()
        messages.success(request, "Transaction recorded.")
        return redirect(account)
    return render(request, "main/transaction_form.html", {"form": form, "account": account})


@require_POST
def transaction_delete(request, pk, transaction_pk):
    """Undo the last transaction on an account, both sides of it and any matches it made.

    Only the last one: deleting an earlier transaction would pull a lot out from under the
    FIFO matching that came after it.
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

    transaction.delete()
    messages.success(request, "Transaction deleted.")
    return redirect(account)


@require_POST
def entry_match(request, pk):
    """Run FIFO matching for a single credit that is still open."""
    entry = get_object_or_404(Entry.objects.select_related("transaction", "account"), pk=pk)
    if not entry.is_credit:
        messages.error(request, "Only credits are matched against earlier debits.")
        return redirect(entry.account)

    matches = match_credit_fifo(entry)
    if matches:
        matched = sum((match.quantity for match in matches), ZERO)
        messages.success(request, f"Matched {matched} {entry.account.currency} FIFO.")
    else:
        messages.info(request, "No open debits were available to match against.")
    return redirect(entry.account)


def _entry_rows(account):
    """Build the account's entry list, newest first, with running balances and match state.

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
    matched = matched_quantity_by_entry(account)

    rows = []
    balance = ZERO
    for entry in entries:
        balance += entry.quantity
        consumed = matched.get(entry.pk, ZERO)
        rows.append(
            {
                "entry": entry,
                "quantity": abs(entry.quantity),
                "balance": balance,
                "matched": consumed,
                "remaining": abs(entry.quantity) - consumed,
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
