"""Context made available to every template."""

from main.models import Account


def accounts(request):
    """The accounts the navbar links to, in name order."""
    return {"nav_accounts": Account.objects.all()}
