"""Forms for creating accounts and double-entry transactions."""

from decimal import Decimal

from django import forms
from django.db import transaction as db_transaction
from django.utils import timezone

from main.matching import match_credit_fifo
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


class TransactionForm(forms.Form):
    """Enter a transaction from one account's page, picking the account on the other side."""

    occurred_on = forms.DateField(
        initial=timezone.localdate,
        label="Date",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    direction = forms.ChoiceField(choices=DIRECTION_CHOICES, initial=DIRECTION_IN)
    quantity = forms.DecimalField(min_value=Decimal(0), label="Quantity")
    counterpart = forms.ModelChoiceField(queryset=Account.objects.none(), label="Other account")
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

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
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

    @db_transaction.atomic
    def save(self):
        """Write the transaction, both entries, and any FIFO matches they trigger."""
        data = self.cleaned_data
        quantity = data["quantity"]
        counterpart_quantity = data.get("counterpart_quantity") or quantity
        incoming = data["direction"] == DIRECTION_IN

        transaction = Transaction.objects.create(
            occurred_on=data["occurred_on"], description=data["description"]
        )
        this_entry = Entry.objects.create(
            transaction=transaction,
            account=self.account,
            quantity=quantity if incoming else -quantity,
        )
        other_entry = Entry.objects.create(
            transaction=transaction,
            account=data["counterpart"],
            quantity=-counterpart_quantity if incoming else counterpart_quantity,
        )

        if data.get("match_fifo"):
            for entry in (this_entry, other_entry):
                if entry.is_credit:
                    match_credit_fifo(entry)
        return transaction
