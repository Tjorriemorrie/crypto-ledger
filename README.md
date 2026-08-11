# crypto-ledger

Manually keep track of your crypto transactions.

## What it is

A personal ledger for everything you hold, crypto and fiat alike. You create an **account**
for each wallet, exchange or bank account, and every account has a page listing its
transactions, reachable from the navbar at the top of every page. An account holds **ZAR**,
**BTC**, **USDT** or **USDC** — the list is fixed, because everything is reported in rands and
that only works for a currency there is a rate for. You can rename an account or reword its
note from its page; the currency it holds is settled when you create it and stays put.

Everything is **valued in ZAR**. Prices are downloaded from CoinGecko when the server starts,
and the accounts page shows what each account is worth along with the total across the lot;
there is a *Refresh* button when they have gone stale. Two rates are kept, BTC and USD: the
stablecoins are not priced separately, since a USDT and a USDC are each held to be one dollar.
Each transaction is valued at the rate for the date it happened, downloaded the first time
that date is shown and kept from then on. A date with no rate — nothing downloaded yet, or no
connection — shows a dash instead of a value rather than failing.

Transactions are **double entry**: one transaction always has two sides, moving value out of
one account and into another. You enter it from one account's page and pick the account on
the other side. A debit increases an account, a credit decreases it. Transactions are dated to
the day — there is no time of day to fill in — and two on the same date keep the order you
entered them in. A transaction can be **deleted** while it is still the last one on both
accounts it touches, which takes both sides and any matches it made with it. Anything earlier
has no delete button: pulling a lot out from under the matching that came after it would leave
the FIFO wrong.

Transactions can be **matched FIFO**. Buying BTC leaves a debit on the BTC account with an
unmatched quantity. Selling later creates a credit, which is matched against those earlier
debits oldest first, consuming each one fully before moving on, until the credit is covered
or nothing is left to match. It is always FIFO.

Matching is optional — there is a tick box on the transaction form, and a *Match FIFO* button
next to any credit still left open — and it can be partial. Only debits dated on or before the
credit are eligible, since you cannot dispose of something you had not yet acquired; enter a
backdated purchase later and re-running the match picks up where it left off. Each account
page shows, per transaction, what is still unmatched: on a debit the part you still hold, on a
credit the part nothing accounts for yet.

That is the whole of it. This is not accounting software — there is no chart of accounts, no
journals, no periods and no reports, and there is no plan to add any.

## Tech stack

- Python 3.13.1
- Django 6.1 — web framework (project package `crypto_ledger`, app `main`)
- SQLite — default database (`db.sqlite3`)
- requests — the rate downloads
- [CoinGecko](https://www.coingecko.com/en/api) — the public price API, no key needed
- [uv](https://docs.astral.sh/uv/) — dependency and environment management
- pytest + pytest-django — tests, in the top-level `tests/` package
- ruff — lint and format
- pre-commit — git hooks running ruff, django-upgrade and file checks

## Layout

- `crypto_ledger/` — Django project settings, URLs, WSGI/ASGI entrypoints. `wsgi.py` also
  kicks off the rate download as the server comes up
- `main/` — the main app: `models.py` (`Account`, `Transaction`, `Entry`, `Match`,
  `ExchangeRate`), `matching.py` (FIFO), `rates.py` (prices), `forms.py`, `views.py`,
  templates
- `tests/` — the pytest suite
- `manage.py` — Django CLI entrypoint

## Getting started

```bash
uv sync
uv run pre-commit install
uv run python manage.py migrate
uv run python manage.py runserver
```

Run the tests with `uv run pytest`, and the hooks over the whole repo with
`uv run pre-commit run --all-files`.

Set `RATES_DOWNLOAD = False` in `crypto_ledger/settings.py` to keep the app off the network
entirely; it then values quantities only at rates already stored. The tests run that way.
