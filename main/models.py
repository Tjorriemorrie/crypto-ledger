"""Ledger models: accounts, double-entry transactions, FIFO matches and exchange rates."""

from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

# Crypto quantities need far more precision than money does, so every quantity in the
# ledger uses the same wide decimal rather than a per-asset precision.
QUANTITY_MAX_DIGITS = 32
QUANTITY_DECIMAL_PLACES = 18

ZERO = Decimal(0)


class Currency(models.TextChoices):
    """What an account can hold.

    The list is deliberately closed: every balance is reported in ZAR, which is only possible
    for a currency there is a rate for. Adding one means giving it a rate to be priced by.
    """

    ZAR = "ZAR", "ZAR — South African rand"
    BTC = "BTC", "BTC — Bitcoin"
    USDT = "USDT", "USDT — Tether"
    USDC = "USDC", "USDC — USD Coin"


class RatedAsset(models.TextChoices):
    """What a downloaded rate prices.

    Not the same list as `Currency`: the stablecoins are each held at one US dollar, so they
    are priced by the dollar rate rather than one of their own.
    """

    BTC = "BTC", "Bitcoin"
    USD = "USD", "US dollar"


# What everything is valued in. ZAR accounts are worth their balance; the rest are converted.
BASE_CURRENCY = Currency.ZAR

# The currencies pegged to the dollar rather than held for what they might become. Split out
# from the rest of the crypto so the accounts page can show what is at risk of a price move
# separately from what is parked.
STABLECOINS = frozenset({Currency.USDT, Currency.USDC})


def quantity_field(**kwargs):
    """Return the decimal field every quantity in the ledger uses."""
    return models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        **kwargs,
    )


class Account(models.Model):
    """A wallet, exchange account or bank account holding one asset."""

    name = models.CharField(max_length=100, unique=True)
    currency = models.CharField(
        max_length=4,
        choices=Currency,
        default=Currency.ZAR,
        help_text="The asset this account holds.",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.currency})"

    def get_absolute_url(self):
        return reverse("account-detail", args=[self.pk])

    @property
    def balance(self):
        """The account's holding: debits less credits."""
        return self.entries.aggregate(total=Sum("quantity"))["total"] or ZERO


class Transaction(models.Model):
    """A movement of value, with one entry on each of two accounts.

    A transaction may also be one-sided, with a single entry: value that came from or went to
    somewhere the ledger does not keep an account for. The quantity on the account is known,
    the other side is not, and inventing an account to face it would only clutter the ledger
    with holdings that are not held.

    A transaction is dated to the day and no finer. Rates are per day, and a hand-kept ledger
    does not know the minute anyway; two transactions on the same date are ordered by the
    order they were entered.
    """

    occurred_on = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=200, blank=True)
    # Whether this transaction's credit takes part in FIFO matching. Stored rather than read
    # back off the matches, because a credit entered before the lot that covers it has no
    # matches yet and must still be told apart from one left open deliberately — otherwise the
    # backdated purchase that finally covers it would replay the account and skip it.
    match_fifo = models.BooleanField(
        default=True,
        help_text="Whether the credit on this transaction is matched against earlier debits.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_on", "-id"]

    def __str__(self):
        return self.description or f"Transaction {self.pk}"

    @property
    def is_one_sided(self):
        """Whether this transaction touches one account only, the other side being unknown."""
        return self.entries.count() == 1

    @property
    def is_last(self):
        """Whether nothing later has been entered on either account this transaction touches.

        Only a last transaction may be deleted. Removing an earlier one would leave the FIFO
        matching after it standing on lots that are no longer there.
        """
        for entry in self.entries.all():
            latest = entry.account.entries.order_by("transaction__occurred_on", "id").last()
            if latest is None or latest.pk != entry.pk:
                return False
        return True


class Entry(models.Model):
    """One side of a transaction: a signed quantity against a single account.

    A positive quantity is a debit (the account gains), a negative quantity is a credit
    (the account gives up). The two entries of a transaction do not have to be equal and
    opposite — buying BTC with ZAR credits one quantity and debits an entirely different one.
    A one-sided transaction has this entry and no other.
    """

    transaction = models.ForeignKey(Transaction, related_name="entries", on_delete=models.CASCADE)
    account = models.ForeignKey(Account, related_name="entries", on_delete=models.PROTECT)
    quantity = quantity_field(help_text="Positive debits the account, negative credits it.")

    class Meta:
        ordering = ["transaction__occurred_on", "id"]
        verbose_name_plural = "entries"
        constraints = [
            models.CheckConstraint(condition=~models.Q(quantity=0), name="entry_quantity_nonzero"),
        ]

    def __str__(self):
        side = "debit" if self.is_debit else "credit"
        return f"{side} {abs(self.quantity)} {self.account.currency} on {self.account.name}"

    @property
    def is_debit(self):
        return self.quantity > 0

    @property
    def is_credit(self):
        return self.quantity < 0

    @property
    def counterpart(self):
        """The entry on the other side of the same transaction, or None if it is one-sided."""
        for entry in self.transaction.entries.all():
            if entry.pk != self.pk:
                return entry
        return None

    @property
    def matched_quantity(self):
        """How much of this entry FIFO matching has already consumed."""
        matches = self.matches_as_debit if self.is_debit else self.matches_as_credit
        return matches.aggregate(total=Sum("quantity"))["total"] or ZERO

    @property
    def unmatched_quantity(self):
        """How much of this entry is still open to be matched."""
        return abs(self.quantity) - self.matched_quantity


class Match(models.Model):
    """A FIFO link consuming part of an earlier debit with part of a later credit."""

    debit = models.ForeignKey(Entry, related_name="matches_as_debit", on_delete=models.CASCADE)
    credit = models.ForeignKey(Entry, related_name="matches_as_credit", on_delete=models.CASCADE)
    quantity = quantity_field(help_text="Always positive: the quantity consumed on both sides.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["debit__transaction__occurred_on", "id"]
        verbose_name_plural = "matches"
        constraints = [
            models.UniqueConstraint(fields=["debit", "credit"], name="match_unique_pair"),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="match_quantity_positive"
            ),
        ]

    def __str__(self):
        return f"{self.quantity} matched from entry {self.debit_id} to entry {self.credit_id}"


class ExchangeRate(models.Model):
    """What one unit of an asset was worth in ZAR on a single date.

    One row per asset per date, downloaded once and kept: a past date's price does not change,
    and today's rows are overwritten whenever fresher prices are downloaded.
    """

    date = models.DateField()
    asset = models.CharField(max_length=3, choices=RatedAsset)
    zar_per_unit = quantity_field(help_text="The price of one unit of the asset in ZAR.")
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "asset"]
        constraints = [
            models.UniqueConstraint(fields=["date", "asset"], name="rate_unique_asset_per_date"),
        ]

    def __str__(self):
        return f"1 {self.asset} = {self.zar_per_unit} ZAR on {self.date}"
