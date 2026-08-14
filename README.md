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
and the rates in hand sit on the right of the navbar, with *Refresh rates* under the *Settings*
dropdown beside them for when they have gone stale. Two rates are kept, BTC and USD: the
stablecoins are not priced separately, since a USDT and a USDC are each held to be one dollar.
Each transaction is valued at the rate for the date it happened, downloaded the first time
that date is shown and kept from then on. A date with no rate — nothing downloaded yet, or no
connection — shows a dash instead of a value rather than failing.

The **accounts page** lists every account with its balance and what it is worth, and totals
those values three ways. **Investment** is the ZAR accounts: money spent on crypto leaves them
negative, so it is what you have put in. **Crypto assets** is everything else — split alongside
it into **crypto**, whose price can move, and **stablecoins**, the USDT and USDC held at a
dollar each. Add the two together and you have your **profit**, or your **loss** when it comes
out negative.

Transactions are **double entry**: one transaction has two sides, moving value out of one
account and into another. You enter it from one account's page and pick the account on the
other side. A debit increases an account, a credit decreases it. Transactions are dated to
the day — there is no time of day to fill in — and two on the same date keep the order you
entered them in. A transaction can be **deleted** while it is still the last one on every
account it touches, which takes every side and any matches it made with it. Anything earlier
has no delete button: pulling a lot out from under the matching that came after it would leave
the FIFO wrong.

Any transaction can be **edited**, however far back it is — the pencil on its row opens the
same form filled in from what you recorded. Change the date, either quantity, the description,
the account on the other side, or whether it matches at all; tick *one-sided* and the other
side is dropped. Saving takes you back to the account page, scrolled to the row and briefly
highlighted so you can see what you changed.

A transaction can also be **one-sided**. Tick *one-sided* on the form and you do not pick an
other account at all: only this account's entry is written, for value that came from or went
to somewhere you keep no account for. The account page shows *Details lost* where the
other side would be. One-sided transactions match FIFO like any other — a one-sided credit
still consumes the earlier debits on its account.

Transactions are **matched FIFO**. Buying BTC leaves a debit on the BTC account with an
unmatched quantity. Selling later creates a credit, which is matched against those earlier
debits oldest first, consuming each one fully before moving on, until the credit is covered
or nothing is left to match. It is always FIFO. Only debits dated on or before the credit are
eligible, since you cannot dispose of something you had not yet acquired. Each account page
totals what is still unmatched in the footer of its transaction table: on the debit side what
you still hold, on the credit side disposals with nothing behind them to account for.

**You never match anything by hand.** Recording, editing or deleting a transaction redoes the
matching from scratch on every account it touches, replaying it oldest first — so the lots
always line up with the ledger as it now reads. That is what makes a backdated entry safe:
remember a purchase from three months ago, enter it today, and the sales you had already
recorded after it pick up the lot they should have eaten, without you going back over them.

The one control you have is the *Match FIFO* tick box on the transaction form. Leave it
ticked, which is the default, and the transaction takes part. Untick it and its disposal is
left open on purpose, and stays open no matter how often the account is replayed afterwards —
until you edit the transaction and tick it again. Matching can also be partial: a sale larger
than the lots open under it matches what it can and shows the rest as unmatched.

Every transaction row has a second icon on the right, through to its **capital gain** page, which is
what the matching is for. The disposal is the credit side — the asset that left — and the
**proceeds** are what came in for it. Rands received are the proceeds exactly; a crypto received
is valued at the rate for the day. The **base cost** is what the lots FIFO consumed cost on the
days *they* were acquired: a lot bought with rands cost what left the bank, and a lot swapped
out of another crypto cost what it was worth the day it arrived. The **gain** is the difference,
shown as a loss when it comes out negative.

**Every crypto-to-crypto swap is a disposal in its own right**, declared on its own page, and
the trail stops at the lots — there is no chasing a swap back to the rands that started it years
ago. That keeps the figures tying together: the cost of a lot that came out of a swap is the
same number declared as the proceeds of that swap, so the two sides always agree. Declare each
swap from its own row on the account it happened on; clicking a lot on this page takes you
straight there, scrolled to that transaction and briefly highlighted. The page ends with the
whole method written out — what a disposal is, how FIFO picks the lots, and the three ways a
lot can be priced.

The page is built to be filed from. Every rand figure says where it came from: the proceeds name
the rate they were valued at with its date and source, each lot shows the rate behind its own
cost, and a lot bought with rands shows no rate at all because the cash is the cost exactly.
Where a disposal consumed several lots the proceeds are split across them pro rata, so each lot
is a complete line with its own date acquired and the lines still add to the totals. The method
at the bottom sets out that the holdings are a long-term capital investment and the disposals
are small balancing moves between them, declared in full even though nothing was cashed out.
The lots are folded away behind *Lots consumed* so the three figures read first; open it when
you want the workings, and it prints the way you left it. There is a *Print* button, and printing
drops the navbar and puts the page on paper in black.

Nothing is stored: the page reads the matches and prices them, so it always reflects the
matching as it stands, and a disposal you unticked *Match FIFO* on shows no base cost until you
tick it again.
A transaction that credits rands is a purchase, not a disposal, and one with no credit at all is
an asset arriving with its details lost; both get a page showing the base cost they create and
no gain.

The **Settings** dropdown at the end of the navbar holds a tax year and a **CGT report** button,
which lists every disposal in that year with its proceeds, base cost and gain, and totals the
three — the figures for the return. SARS runs its year from 1 March to the end of February and names it for the February it
ends in, so the *2026 tax year* is 1 March 2025 to 28 February 2026, and the report opens on the
last year to have ended, the one there is actually a return to file for. Only disposals are
listed: buying crypto with rands and an asset simply arriving create a base cost but give up
nothing. Each row is the same calculation its own page shows in full, so click one to see the
lots behind it. Nothing is stored here either — correct a transaction and the report changes the
moment you save.

That is the whole of it. This is not accounting software — there is no chart of accounts, no
journals and no reports beyond the tax year's capital gains, and there is no plan to add any.

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
  `ExchangeRate`), `matching.py` (FIFO), `cgt.py` (base cost and gain), `rates.py` (prices),
  `forms.py`, `views.py`, templates
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
