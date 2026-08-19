"""Forms for creating accounts and double-entry transactions, and for the analysis page's grid."""

from decimal import Decimal

from django import forms
from django.db import transaction as db_transaction
from django.utils import timezone

from main import backtest, preferences
from main.matching import rebuild_account_matching
from main.models import Account, Entry, Transaction

DIRECTION_IN = "in"
DIRECTION_OUT = "out"
DIRECTION_CHOICES = [
    (DIRECTION_IN, "In — debit this account"),
    (DIRECTION_OUT, "Out — credit this account"),
]


LOW, HIGH = 0, 1

# The window a sweep is run over. Named because it travels with the settings on every form and
# every link but is not one of them — it says which prices, not what to do with them.
WINDOW = "years"

# What each swept setting is called on the page, and the unit that makes the figure mean something.
SETTING_LABELS = {
    "percent": "Weekly move (%)",
    "short": "Short average (days)",
    "multiplier": "Multiplier (times the short)",
    "fee": "Fee on every conversion (%)",
    "years": "Years of history",
}


class RangeInput(forms.NumberInput):
    """A slider. There are enough settings on the sweep now that they are dragged, not typed."""

    input_type = "range"


def grid_of(values):
    """The three ranges out of a set of field values, as `backtest` takes them.

    Written once because the settings arrive two ways — cleaned off a form that has just been
    submitted, and read back out of the last sweep remembered — and both have to come to the
    same grid.
    """
    return {
        setting: (values[f"{setting}_min"], values[f"{setting}_max"])
        for setting in backtest.DEFAULTS
    }


def _setting(setting, widget=None, **kwargs):
    """One of the swept settings, held inside the bounds a sweep will accept it in."""
    low, high = backtest.BOUNDS[setting]
    return forms.IntegerField(
        min_value=low,
        max_value=high,
        widget=widget or forms.NumberInput(attrs={"step": 1}),
        **kwargs,
    )


def _edge(setting, edge):
    """One end of one of the sweep's ranges, opening on the default and held inside the bounds."""
    return _setting(
        setting,
        widget=RangeInput(attrs={"step": 1, "data-setting": setting, "data-edge": edge}),
        label=SETTING_LABELS[setting],
        initial=backtest.DEFAULTS[setting][edge],
    )


class SweepForm(forms.Form):
    """The grid the analysis page sweeps: a lowest and a highest for each of its three settings.

    Both plans are always run — comparing them is what the page is for — so the only thing set
    here is how wide each range goes. The form is what decides whether a sweep happens at all: an
    unbound one draws the ranges and waits, and nothing is worked out until Run is pressed.

    It is also what the sweep's own requests are read back through, since each slice arrives as a
    fresh request carrying the grid in its query string. A hand-edited URL is therefore checked
    exactly as the form was, rather than trusted for having come from us.
    """

    percent_min = _edge("percent", LOW)
    percent_max = _edge("percent", HIGH)
    short_min = _edge("short", LOW)
    short_max = _edge("short", HIGH)
    multiplier_min = _edge("multiplier", LOW)
    multiplier_max = _edge("multiplier", HIGH)
    # One fee for the whole sweep, so one slider. What an exchange charges is a fact about where
    # the money is held, not a setting worth searching for the best value of.
    fee = _setting(
        "fee",
        widget=RangeInput(attrs={"step": 1, "data-setting": "fee"}),
        label=SETTING_LABELS["fee"],
        initial=backtest.FEE_DEFAULT,
    )
    # And one window, for the same reason: how far back to look is a question asked of the sweep,
    # not a setting for it to go looking for the best value of.
    years = _setting(
        "years",
        widget=RangeInput(attrs={"step": 1, "data-setting": "years"}),
        label=SETTING_LABELS["years"],
        initial=backtest.YEARS_DEFAULT,
    )

    def clean(self):
        """Each range has to run upwards, and the grid they come to has to be one that finishes."""
        data = super().clean()
        for setting in backtest.DEFAULTS:
            low = data.get(f"{setting}_min")
            high = data.get(f"{setting}_max")
            if low is not None and high is not None and low > high:
                self.add_error(f"{setting}_max", "This cannot be below the figure beside it.")
        if self.errors:
            return data
        total = backtest.count(self.grid())
        # The fee is not swept, so it is no part of the count — one fee runs every combination.
        if total > backtest.MAX_COMBINATIONS:
            msg = (
                f"Those ranges come to {total:,} combinations, and {backtest.MAX_COMBINATIONS:,} "
                f"is the most one sweep will run. Narrow one of them."
            )
            raise forms.ValidationError(msg)
        return data

    @classmethod
    def opening(cls):
        """The settings the page opens on: the last sweep run, or None for the defaults.

        Read back through the form that wrote them, exactly as a slice of a sweep is, so
        settings kept before a bound or a cap changed are turned away rather than drawing the
        page outside what a sweep will now run. Anything turned away costs the defaults.
        """
        kept = preferences.remembered()
        if not kept:
            return None
        form = cls(kept)
        return form.cleaned_data if form.is_valid() else None

    def sliders(self):
        """The fields two at a time, a lowest and a highest, for the page to lay out as ranges."""
        return [
            {
                "setting": setting,
                "label": SETTING_LABELS[setting],
                "min": self[f"{setting}_min"],
                "max": self[f"{setting}_max"],
                "floor": backtest.BOUNDS[setting][LOW],
                "ceiling": backtest.BOUNDS[setting][HIGH],
            }
            for setting in backtest.DEFAULTS
        ]

    def grid(self):
        """The ranges as `backtest` takes them, once the form has been found valid."""
        return grid_of(self.cleaned_data)

    def query(self):
        """The grid as a query string, for the slices of the sweep to carry it in."""
        params = {f"{setting}_min": low for setting, (low, _) in self.grid().items()}
        params |= {f"{setting}_max": high for setting, (_, high) in self.grid().items()}
        return params | {
            "fee": self.cleaned_data["fee"],
            "years": self.cleaned_data["years"],
            "run": 1,
        }


class PlanForm(forms.Form):
    """One combination out of a sweep, named in a query string so its own page can run it again.

    A plan is four numbers, so the page that lists its weeks needs nothing else handed to it: the
    row's button carries them and the page works the run out afresh. That is why there is nothing
    to keep between the sweep and this page — a combination is fully described by what names it.
    """

    strategy = forms.ChoiceField(choices=list(backtest.PLANS.items()))
    percent = _setting("percent")
    short = _setting("short")
    multiplier = _setting("multiplier")
    fee = _setting("fee")
    years = _setting("years")

    def combination(self):
        """The plan as `backtest` takes it, once the form has been found valid.

        The window is left out: it is what the plan is run over rather than a setting of the plan,
        and the same four numbers describe the same plan whichever stretch of history they meet.
        """
        return backtest.combination(
            **{name: value for name, value in self.cleaned_data.items() if name != WINDOW}
        )


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
