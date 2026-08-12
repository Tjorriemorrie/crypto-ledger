"""Context made available to every template."""

from main import cgt
from main.models import Account
from main.rates import latest_rates


def navbar(request):
    """What the navbar shows on every page: accounts, the tax year report, and the rates."""
    return {
        "nav_accounts": Account.objects.all(),
        "nav_tax_years": cgt.tax_years(),
        "nav_tax_year": cgt.selected_tax_year(request.GET.get("year")),
        "nav_rates": latest_rates(),
    }
