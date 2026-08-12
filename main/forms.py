"""Forms for creating accounts and double-entry transactions."""

from decimal import Decimal

from django import forms
from django.db import transaction as db_transaction
from django.utils import timezone

from main.matching import rebuild_account_matching
from main.models import Account, Entry, Transaction

DIRECTION_IN = "in"
DIRECTION_OUT = "out"
DIRECTION_CHOICES = [
    (DIRECTION_IN, "In — debit this account"),
    (DIRECTION_OUT, "Out — credit this account"),
]


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "currency", "note"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ledger BTC"}),
            "note": forms.Textarea(attrs={"rows": 2}),
        }


class AccountEditForm(AccountForm):
    """Rename an account or reword its note.

    The currency is left out on purpose: entries are already recorded in it, and changing it
    would revalue every past transaction on the account without touching a single quantity.
    """

    class Meta(AccountForm.Meta):
        fields = ["name", "note"]


def _initial_from(transaction, account):
    """Fill the form in from a transaction already recorded, seen from `account`.

    Which way round it reads depends on the account the edit was opened from: the same
    transaction is money in on one side and money out on the other.
    """
    entry = transaction.entries.get(account=account)
    other = entry.counterpart
    return {
        "occurred_on": transaction.occurred_on,
        "direction": DIRECTION_IN if entry.is_debit else DIRECTION_OUT,
        "quantity": abs(entry.quantity),
        "one_sided": other is None,
        "counterpart": other.account if other else None,
        "counterpart_quantity": abs(other.quantity) if other else None,
        "description": transaction.description,
        "match_fifo": transaction.match_fifo,
    }


def _write_entry(transaction, entry, account, quantity):
    """Create the entry, or move the row already there onto this account and quantity."""
    if entry is None:
        return Entry.objects.create(transaction=transaction, account=account, quantity=quantity)
    entry.account = account
    entry.quantity = quantity
    entry.save(update_fields=["account", "quantity"])
    return entry


class TransactionForm(forms.Form):
    """Enter a transaction from one account's page, picking the account on the other side.

    Or no account at all: tick one-sided and only this account's entry is written, for value
    that came from or went somewhere the ledger does not track.

    Pass `instance` to correct a transaction already recorded: the same form, filled in from
    the transaction as this account sees it, writing over the rows it already has.
    """

    occurred_on = forms.DateField(
        initial=timezone.localdate,
        label="Date",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    direction = forms.ChoiceField(choices=DIRECTION_CHOICES, initial=DIRECTION_IN)
    quantity = forms.DecimalField(min_value=Decimal(0), label="Quantity")
    one_sided = forms.BooleanField(
        required=False,
        label="One-sided — the details of the other side are lost",
        help_text="Tick when there is no account to put the other side on, and leave the "
        "fields below blank.",
    )
    counterpart = forms.ModelChoiceField(
        queryset=Account.objects.none(), required=False, label="Other account"
    )
    counterpart_quantity = forms.DecimalField(
        required=False,
        min_value=Decimal(0),
        label="Quantity on the other account",
        help_text="Leave blank to move the same quantity, e.g. for a transfer.",
    )
    description = forms.CharField(max_length=200, required=False)
    match_fifo = forms.BooleanField(
        required=False,
        initial=True,
        label="Match FIFO against earlier transactions",
    )

    def __init__(self, *args, account, instance=None, **kwargs):
        self.account = account
        self.instance = instance
        if instance is not None:
            kwargs["initial"] = _initial_from(instance, account) | kwargs.get("initial", {})
        super().__init__(*args, **kwargs)
        self.fields["counterpart"].queryset = Account.objects.exclude(pk=account.pk)
        self.fields["quantity"].label = f"Quantity ({account.currency})"

    def clean_quantity(self):
        return self._clean_positive("quantity")

    def clean_counterpart_quantity(self):
        quantity = self.cleaned_data.get("counterpart_quantity")
        if quantity is None:
            return None
        return self._clean_positive("counterpart_quantity")

    def _clean_positive(self, field):
        quantity = self.cleaned_data[field]
        if quantity <= 0:
            msg = "Enter a quantity greater than zero."
            raise forms.ValidationError(msg)
        return quantity

    def clean(self):
        """A transaction faces another account or nothing at all, and must say which.

        Ticking one-sided is the deliberate choice, so it wins over an account left sitting in
        the picker; picking neither is the one thing that cannot be resolved.
        """
        data = super().clean()
        if data.get("one_sided"):
            data["counterpart"] = None
            data["counterpart_quantity"] = None
        elif not data.get("counterpart"):
            self.add_error(
                "counterpart",
                "Pick the account on the other side, or tick one-sided if there is none.",
            )
        return data

    @db_transaction.atomic
    def save(self):
        """Write the transaction and its entries, then replay the matching they disturb.

        A one-sided transaction gets the one entry; there is no second account to write to.
        An edit writes over the rows already there rather than adding more.

        Either way the accounts touched are replayed afterwards — the accounts touched before
        the edit as well, since the other side can be moved to a different account. A new
        transaction needs this as much as a corrected one does: entering a purchase you had
        forgotten hands the sales already recorded after it a lot they should have consumed,
        and only replaying the account picks that up.
        """
        data = self.cleaned_data
        editing = self.instance is not None

        transaction = self.instance or Transaction()
        existing = list(transaction.entries.all()) if editing else []
        touched = {entry.account_id: entry.account for entry in existing}

        transaction.occurred_on = data["occurred_on"]
        transaction.description = data["description"]
        transaction.match_fifo = bool(data.get("match_fifo"))
        transaction.save()

        quantity = data["quantity"]
        incoming = data["direction"] == DIRECTION_IN
        counterpart = data["counterpart"]
        mine = next((entry for entry in existing if entry.account_id == self.account.pk), None)
        other = next((entry for entry in existing if entry.account_id != self.account.pk), None)

        _write_entry(transaction, mine, self.account, quantity if incoming else -quantity)
        touched[self.account.pk] = self.account
        if counterpart:
            counterpart_quantity = data.get("counterpart_quantity") or quantity
            _write_entry(
                transaction,
                other,
                counterpart,
                -counterpart_quantity if incoming else counterpart_quantity,
            )
            touched[counterpart.pk] = counterpart
        elif other is not None:
            other.delete()

        for account in touched.values():
            rebuild_account_matching(account)
        return transaction
