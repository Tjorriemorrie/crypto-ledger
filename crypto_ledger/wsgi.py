"""
WSGI config for crypto_ledger project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crypto_ledger.settings")

application = get_wsgi_application()

# Pages value balances from rates already in the database, so the current prices are
# downloaded once here, as the server comes up. The weeks behind the profit chart are then
# worked out off those prices, so the first load of the accounts page has them in hand. Both
# imports have to wait for the line above: nothing can touch the models until Django has loaded
# the apps.
from main.history import warm
from main.rates import refresh_at_startup

refresh_at_startup()
warm()
