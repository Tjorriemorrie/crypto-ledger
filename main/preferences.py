"""The settings the analysis page was last run with, so it opens where it was left.

A sweep is chosen rather than handed: the ranges, the fee and the window are dragged into place
before Run is pressed, and the answer to one grid is usually a reason to try another. Coming back
to the defaults every time the server restarts means setting all of that up again, so the settings
behind the last sweep that ran are kept in Django's cache under one key and the page opens on them.

They are kept here rather than in the browser because the page is rendered on the server: the
sliders come back already in place, rather than starting at the defaults and jumping once a script
has run. It is also where the ledger keeps everything else it remembers between boots.

This is a convenience and never a record. Settings that are missing, unreadable or left over from
an older shape of the page cost the defaults and never a wrong figure, so clearing the cache is
always safe — and they are read back through the same form that wrote them before the page is
drawn with them, so an entry from a wider grid than the sweep will now run cannot get in that way.
"""

from django.core.cache import cache

# The one key the settings are kept under. Its name says what is stored there, so changing the
# shape of that means changing the name and letting the old entry fall away unread.
CACHE_KEY = "analysis-settings"


def remember(values):
    """Keep the settings a sweep was just run with, in place of whatever was there before.

    Only the last sweep is worth keeping: the page opens on one set of settings, and a history of
    the ones before it is a list nothing would ever read.
    """
    cache.set(CACHE_KEY, dict(values))


def remembered():
    """The settings last kept, or None when nothing has been run or the cache has been cleared."""
    return cache.get(CACHE_KEY)
