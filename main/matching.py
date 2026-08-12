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
        if available <= ZERO:
            # SQLite sums decimals as floats, so a debit that is exactly used up can still
            # pass the query's filter by a rounding epsilon. Decimal arithmetic here has the
            # last word — matching one would write a zero-quantity match.
            continue
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


@db_transaction.atomic
def rebuild_account_matching(account):
    """Throw away an account's matches and replay FIFO over its credits, oldest first.

    Every write to the ledger runs this on the accounts it touched, because almost anything can
    change which lots the credits should have consumed: a backdated purchase gives an earlier
    sale something to eat, a corrected date or quantity changes how far a lot goes, and a
    deletion takes a lot away altogether. Patching the matches around each case would need a
    rule per case; replaying needs none, because FIFO is deterministic — the result is the
    matching the ledger would have reached had it always read this way.

    Credits on a transaction with matching turned off are passed over, so a disposal left open
    on purpose stays open however often the account is replayed.
    """
    Match.objects.filter(debit__account=account).delete()
    open_credits = Entry.objects.filter(
        account=account, quantity__lt=0, transaction__match_fifo=True
    ).order_by("transaction__occurred_on", "id")
    for credit in open_credits:
        match_credit_fifo(credit)


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
