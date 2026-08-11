"""FIFO matching of credits against earlier debits on the same account.

Selling BTC does not just lower a balance — it consumes the specific earlier purchases that
put the BTC there. That consumption is always first-in-first-out: the oldest open debit is
used up entirely before the next one is touched.
"""

from django.db import models
from django.db import transaction as db_transaction
from django.db.models.functions import Coalesce

from main.models import (
    QUANTITY_DECIMAL_PLACES,
    QUANTITY_MAX_DIGITS,
    ZERO,
    Entry,
    Match,
)


def open_debits(credit):
    """Return the debits a credit may consume, oldest first, each with its matched total.

    Only debits dated on or before the credit are eligible — you cannot dispose of something
    you had not yet acquired. Transactions are dated to the day, so a debit entered on the same
    date as the credit does count, and same-date debits are consumed in the order entered.
    """
    quantity_output = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS, decimal_places=QUANTITY_DECIMAL_PLACES
    )
    return (
        Entry.objects.filter(
            account_id=credit.account_id,
            quantity__gt=0,
            transaction__occurred_on__lte=credit.transaction.occurred_on,
        )
        .annotate(
            matched=Coalesce(
                models.Sum("matches_as_debit__quantity"),
                models.Value(ZERO),
                output_field=quantity_output,
            )
        )
        .filter(quantity__gt=models.F("matched"))
        .order_by("transaction__occurred_on", "id")
    )


@db_transaction.atomic
def match_credit_fifo(credit):
    """Consume the oldest open debits with `credit`, and return the matches written.

    Matching is best effort: if the open debits do not cover the credit, whatever can be
    matched is matched and the rest of the credit stays open. Running this again later — once
    an earlier debit exists — picks up where it left off, so it is safe to call repeatedly.
    """
    if not credit.is_credit:
        msg = f"Entry {credit.pk} is not a credit, so it cannot be matched against debits."
        raise ValueError(msg)

    remaining = credit.unmatched_quantity
    if remaining <= ZERO:
        return []

    matches = []
    for debit in open_debits(credit):
        if remaining <= ZERO:
            break
        available = debit.quantity - debit.matched
        taken = min(remaining, available)
        matches.append(_consume(debit, credit, taken))
        remaining -= taken
    return matches


def _consume(debit, credit, quantity):
    """Record `quantity` moving from `debit` to `credit`, extending any existing match.

    A credit can come back to a debit it has already partly consumed — a backdated purchase
    reopens matching for a credit that was left short — and the pair is unique, so the
    existing row grows rather than a second one appearing beside it.
    """
    match, created = Match.objects.get_or_create(
        debit=debit, credit=credit, defaults={"quantity": quantity}
    )
    if not created:
        match.quantity += quantity
        match.save(update_fields=["quantity"])
    return match


def unmatched_totals(account):
    """Return the still-open debit and credit quantities on an account.

    The open debits are what is still held under FIFO; the open credits are disposals with
    nothing yet to account for them.
    """
    open_debit = ZERO
    open_credit = ZERO
    for entry in Entry.objects.filter(account=account).prefetch_related(
        "matches_as_debit", "matches_as_credit"
    ):
        remaining = entry.unmatched_quantity
        if entry.is_debit:
            open_debit += remaining
        else:
            open_credit += remaining
    return {"debit": open_debit, "credit": open_credit}


def matched_quantity_by_entry(account):
    """Return `{entry_id: matched quantity}` for every entry on `account` in one query."""
    totals = {}
    rows = Match.objects.filter(
        models.Q(debit__account=account) | models.Q(credit__account=account)
    ).values_list("debit_id", "credit_id", "quantity")
    for debit_id, credit_id, quantity in rows:
        totals[debit_id] = totals.get(debit_id, ZERO) + quantity
        totals[credit_id] = totals.get(credit_id, ZERO) + quantity
    return totals
