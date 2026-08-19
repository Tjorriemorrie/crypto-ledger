# crypto-ledger

Manually keep track of your crypto transactions.

## What it is

A personal ledger for everything you hold, crypto and fiat alike. You create an **account**
for each wallet, exchange or bank account, and every account has a page listing its
transactions, reachable from the navbar at the top of every page. An account holds **ZAR**,
**BTC**, **USDT** or **USDC** — the list is fixed, because everything is reported in rands and
that only works for a currency there is a rate for. You can rename an account or reword its
note from its page; the currency it holds is settled when you create it and stays put.
**Backspace goes back** wherever you are — from a capital gain page to the account it came
from, from an account to the page before it — except while you are typing in a field, where it
still deletes.

Everything is **valued in ZAR**. Prices are downloaded from CoinGecko when the server starts,
and the rates in hand sit on the right of the navbar, with *Refresh rates* under the *Settings*
dropdown beside them for when they have gone stale. Two rates are kept, BTC and USD: the
stablecoins are not priced separately, since a USDT and a USDC are each held to be one dollar.
Each transaction is valued at the rate for the date it happened, downloaded the first time
that date is shown and kept from then on. CoinGecko's public API will not serve a chart of
prices older than a year, so a chart window reaching further back is filled a year deep and the
days behind that are whatever has already been downloaded. A date with no rate — nothing
downloaded yet, too far back, or no connection — shows a dash instead of a value rather than
failing.

The **accounts page** lists every account with its balance and what it is worth, and totals
those values three ways. **Investment** is the ZAR accounts: money spent on crypto leaves them
negative, so it is what you have put in. **Crypto assets** is everything else — split alongside
it into **crypto**, whose price can move, and **stablecoins**, the USDT and USDC held at a
dollar each. Add the two together and you have your **profit**, or your **loss** when it comes
out negative.

Between those totals and the list of accounts is a **chart of your profit**, one stacked bar a
week for the last 100 weeks, every account in it and priced at that week's rates. It is the profit
card drawn as two years of history rather than a single figure for today. Weeks are counted back
from today in sevens, so the last bar is where you stand now and none of them is a part week, and
each is shown at its **close** — the latest day in it there is a rate for.

The money you put in hangs below the axis and what it is holding stands above, the **crypto on top
of the stablecoins** because it is the only part whose price moves. The profit is what is left when
the two ends are added back together, and because that is not something you can read off two stacks
by eye, it is drawn over the bars as a **white line**, with a straight **trendline** through it for
which way the two years went. The trend is a reading of the bars already on the chart and nothing
more; nothing in the ledger acts on it. Hover any bar for the week it closes, what every account was
worth in it, and the profit or loss it came to. Each account has its own colour, listed in the key.

The weekly figures are cached on disk, all of them under one key, so opening the page works out the
week in progress and reads the rest back. It is only ever a cache: correct a transaction, however
far back, and the lot is thrown away and worked out again. Clear it whenever you like — the next
page load rebuilds it from your transactions and the rates.

Under the accounts is a **chart of the Bitcoin price**: the close in rands, one point a day for
the last 260 days, with a **26-day and a 260-day moving average** drawn over it and the price
labelled down both sides so the right-hand end reads as easily as the left. The close line is
**green where the 26-day average is above the 260-day** and **purple where it is below**, which
is a reading of the two lines already on the chart and nothing more — nothing in the ledger acts
on it. Hover any day to see its date and what a Bitcoin closed at. That is all it does — no zoom
and no ranges to pick.

Under the plot, on the same dates, is a **strip**: the close against where it stood **260 days**
earlier, the same span as the long average, with a zero line of its own. It is the one reading that
tracks whether **simply holding Bitcoin has been better than the investment plans** on the analysis
page — over the years priced, holding beat the best of them in most windows the price ended above
that line, and lost to them in most windows it ended below it. So when the strip has been under the
line a while, the plans have been the better thing to have done, and that is worth knowing.

It does **not** say what the next stretch will do, and the page says so. Trailing readings like it
were tested against the stretches that followed them and none of them carried: holding still came
out ahead of the plans in two thirds or more of every forward stretch measured, including the ones
beginning after the lowest readings on the strip. Like the crossings above it, it describes the
line already drawn, and nothing in the ledger acts on it.
BTC is the only holding whose price moves: rands are what everything is measured in, and a USDT
and a USDC are a dollar each. Every point drawn is the ledger's own rate, and enough extra days
sit behind the window to have both averages and the strip running from the left edge of the
chart rather than starting part way across it. Those extra days reach back further than
CoinGecko will serve, so they come from the same longer history the analysis page is run over —
they are never drawn, never labelled and never written into the ledger's rates, and all they do
is give the lines their days behind them. The chart loads into the page a moment after the
balances do, so a download never holds the page up.

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

A transaction row that gives up a crypto has a second icon on the right, through to its
**capital gain** page, which is what the matching is for. That is the disposal's own row on the
wallet the crypto left, and the row facing it on the rand account it was sold into — both open
the same page, on the wallet. Rows that give up no crypto have no icon: buying a crypto, or an
asset arriving with its details lost, creates a base cost but gives nothing up, so there is
nothing on it to declare. The disposal is the credit side — the asset that left — and the
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
The lots are folded away behind *Lots consumed* so the three figures read first; open it when you
want the workings.

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

The same dropdown holds a link to the **Analysis** page, which is the one place in the app that
looks forward rather than back — and it does that only by reading the past. It asks
what a simple weekly investment plan would have come to. Every week **R 1 000 arrives from
outside** and goes into a rand wallet or a Bitcoin wallet; it is money contributed, never money
taken out of the rand wallet, so every plan on the page is handed exactly the same amount and only
what it did with it separates them. Where it goes is decided by two moving averages of the Bitcoin
price, a short one and a long one, the long being the short times a multiplier. Two plans read
them, and they are the same reading taken the two ways round:

- **Bitcoin on a rise** — the short average above the long buys Bitcoin and sells rands; the short
  below it does the reverse.
- **Bitcoin on a fall** — the opposite throughout: above sells Bitcoin into rands, below buys.

One average is always above the other, so there is always a reading and neither plan ever sits a
week out. Neither one is the sensible one and the other the perverse one; which way round the
history rewarded is the question, and it is answered by running both.

On the same reading, each week also moves a **percentage of one wallet into the other**: an up
reading spends that share of the rand wallet on Bitcoin, a down reading sells that share of the
Bitcoin wallet into rands. The share always comes out of the wallet it leaves, so neither can be
spent past empty. A **fee** is charged on everything that crosses between the wallets — the move
both ways, and the contribution too on the weeks it buys Bitcoin rather than landing as rands. A
week that only puts rands in the rand wallet converts nothing, so it pays nothing.

**You set the ranges** with a pair of sliders each — the weekly move, the short average and the
multiplier — and press **Run**. Nothing is worked out until you do, so widening the weekly move and
running again is the ordinary way to use the page. The first time, it opens on 1–5%, a 20–30 day
short average and a multiplier of 5–10, which is 660 combinations; after that it **opens on the
last sweep you ran**, every slider back where you left it, and that survives restarting the app.
Both plans are always run, and the grid is held to
10 000 combinations: **widen one slider and the widest of the others gives way**, a step at a time
until it fits again, so you can never ask for a sweep that will not finish.

The **fee is a single slider**, not a range, and every combination in the sweep pays it. What your
exchange charges is a fact about where your money is held rather than something to search for the
best value of — so to see what a dearer one costs you, move it and run again.

**Years of history** is a single slider too, from one year to fifteen, and it is how far back the
sweep runs, counted off the last day priced. It is not swept for the same reason the fee is not: a
plan run over a different stretch of history is a different question rather than a better answer to
this one. The prices begin in September 2014, so asking for more years than there are gives you the
whole of them — the dates a sweep actually covered are printed above its results.

The page then **sweeps the whole grid** and ranks the combinations by what they finished with. It
runs in slices and fetches the next slice itself, so the results fill in as they are worked out: a
progress bar, a **mark per combination** placed across the plot by its place in the grid and up it
by its profit with the best so far ringed, and the leading plan's history drawn as **stacked bars
week by week** — the same picture the accounts page draws, over a plan that was never run. If the
winner sits at the end of one of your ranges, widen that range and run it again: the best setting
is probably outside it.

Beside the winner is a **baseline**: the same R 1 000 a week put straight into Bitcoin and never
sold, over the same weeks and paying the same fee. It is the thing to judge a plan against — a plan
that cannot beat leaving the money alone was not worth running — so it is also drawn as a line
across the results chart, with every combination that beat it above the line. Be warned what it
tells you: over the whole history downloaded, **no combination beats it**, and the sweep is really
ranking plans by how much less than holding they returned.

Under that is the sweep read back **one setting at a time** rather than as a list of winners, in
three tabs: **Plan**, **Weekly move** and **Multiplier**. Each lists every value that setting was
swept over against the best result found at it, **ranked by profit**, so the order down a table is
that setting's own answer — the Plan tab is two rows, and whichever is on top is the way round that
worked. A combination that leads more than one setting appears in each of their tables, so the
overall best is normally the top row of all three. The short average is swept like everything else
and shows in every row, but has no tab of its own; with up to two hundred values it would be a
table nobody could read.

Every row has a **Weeks** button through to that plan's own page, which runs it again and lists
every single week: the Bitcoin price and both averages, which way the plan read them, how much was
moved between the wallets, the fee it paid, what each wallet then held, what had been contributed
by then and the running profit. Nothing about a run is stored — the page works it out afresh from
the numbers in its URL each time you open it.

Its prices come from Yahoo rather than CoinGecko, whose public API goes back only a year: Bitcoin's
daily close in dollars times the daily rand price of the dollar. They are cached like the profit
chart's weeks, downloaded once a day, and **deliberately never written into the ledger's own
rates** — a rand on a return has to be traceable to one source. The page reads no account and
records nothing. It is a reading of what has already happened, swept over with nothing held back,
so the best combination on it is the one that fitted the past. It is not a recommendation, and
nothing in the ledger acts on it.

That is the whole of it. This is not accounting software — there is no chart of accounts, no
journals and no reports beyond the tax year's capital gains, and there is no plan to add any.

## Tech stack

- Python 3.13.1
- Django 6.1 — web framework (project package `crypto_ledger`, app `main`)
- SQLite — default database (`db.sqlite3`)
- Django's file-based cache (`cache/`) holding the profit chart's weekly figures and the long
  price history, a single key each — caches only, safe to clear, and git-ignored
- requests — the price downloads
- [CoinGecko](https://www.coingecko.com/en/api) — the public price API behind the ledger's rates,
  no key needed
- [Yahoo Finance](https://finance.yahoo.com/) — the years of daily prices the analysis page is
  swept over and the price chart's extra days sit on, no key needed; never written into the
  ledger's own rates, and CoinGecko's public API goes back only a year
- [htmx](https://htmx.org/) 2 — loads the charts into the accounts page and runs the analysis
  sweep in slices; vendored in the repo rather than fetched from a CDN, so nothing on a page comes
  off the internet
- [uv](https://docs.astral.sh/uv/) — dependency and environment management
- pytest + pytest-django — tests, in the top-level `tests/` package
- ruff — lint and format
- pre-commit — git hooks running ruff, django-upgrade and file checks

## Layout

- `crypto_ledger/` — Django project settings, URLs, WSGI/ASGI entrypoints. `wsgi.py` also
  kicks off the rate download as the server comes up
- `main/` — the main app: `models.py` (`Account`, `Transaction`, `Entry`, `Match`,
  `ExchangeRate`), `matching.py` (FIFO), `cgt.py` (base cost and gain), `rates.py` (the ledger's
  prices), `history.py` (the profit chart's weeks and their cache file), `prices.py` (the
  analysis page's years of prices), `backtest.py` (the investment plans and the sweep),
  `chart.py` (every chart's SVG coordinates), `forms.py`, `views.py`, templates and
  `static/`
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
entirely — it covers the analysis page's downloads as well as the ledger's rates, and the app then
values quantities only at rates already stored. The tests run that way. `CACHES` in the same file
is where the profit chart's weekly figures and the analysis page's price history are kept.
