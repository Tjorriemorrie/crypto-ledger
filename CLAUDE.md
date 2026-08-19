# crypto-ledger

Manually keep track of your crypto transactions.

## Domain

A personal ledger for crypto and fiat holdings. Deliberately simplistic — it borrows
double-entry bookkeeping's one useful idea and nothing else. It is not accounting software:
no chart of accounts, no journals, no trial balance, and the only report and the only period
are the tax year's capital gains, which exist because SARS asks for them. If a feature only
makes sense to a bookkeeper, it does not belong here.

- **Accounts** are wallets or holdings — one per place value sits (an exchange wallet, a
  hardware wallet, a bank account). Fiat accounts are accounts like any other. The currency is
  picked from a fixed list, `Currency` in `models.py`: ZAR, BTC, USDT and USDC. It is closed
  on purpose — everything is reported in ZAR, which is only possible for a currency there is a
  rate for, so adding one means giving it something to be priced by. The name and note can be
  edited afterwards; the currency cannot, since entries are already recorded in it and changing
  it would revalue every past transaction without touching a single quantity.
- **Everything is valued in ZAR.** ZAR is the base currency; every other currency is converted
  at a rate. A balance uses the latest rate held, a transaction the rate for the date it
  happened. A quantity with no rate to value it shows a dash — a missing rate never breaks a
  page.
- **Exchange rates** are ZAR prices from CoinGecko, one row per asset per date, downloaded
  once and kept. The same rows are what both charts are drawn from, and a window is filled in
  one go rather than a day at a time. Only two assets are priced, `RatedAsset`: BTC and USD. The stablecoins are
  not priced separately — a USDT and a USDC are each held to be one dollar, so both are valued
  off the USD rate. Every download works both assets out the same way: CoinGecko quotes BTC in
  ZAR and USD, and dividing the one by the other gives the dollar rate. A single date takes one
  call for that; a whole window takes two, since a market chart is quoted in one currency at a
  time and both quotes are still needed. A window is judged covered by its two ends alone — the
  oldest day that can be downloaded and yesterday — because a download fills everything between
  them. **A window is filled no deeper than a year**, `MAX_WINDOW_DAYS`: CoinGecko's public API
  refuses a market chart older than that outright, so asking for more only ever earns a 401 on
  every boot and every page load. The days behind a year are whatever the ledger already holds,
  and a day with no rate is a day left out rather than an error. The current prices are
  downloaded when the server starts (from `wsgi.py`, so management commands and tests stay off
  the network) and from the refresh in the navbar's settings dropdown; a past date is downloaded the
  first time something needs it. `RATES_DOWNLOAD = False` in settings switches all downloading
  off, which is how the tests run.
- **The accounts page totals** the values three ways. The ZAR accounts are the *investment* —
  cash paid for crypto leaves them negative, so their total is what has been put in — and
  everything else is *crypto assets*, split into *crypto* (whose price moves, in practice BTC)
  and *stablecoins* (`STABLECOINS` in `models.py`: USDT and USDC, a dollar each). Summing the
  lot therefore gives a *profit*, labelled *loss* when it is negative. The rates in hand live in
  the navbar, on every page. Everything that is not an account — refreshing the rates, the tax year
  report, the analysis page — lives behind a single *Settings* dropdown at the end of the navbar, so
  the navbar itself stays a list of accounts and the rates. **Backspace goes back** on every page, the way
  browsers used to do it, since the ledger is read by drilling in and stepping out again — but
  never while a field has focus, where it must still delete.
- **The price chart** sits under the accounts list: the BTC close in ZAR, one point a day for
  the last 260 days, with a 26-day and a 260-day moving average over it. BTC because it is the
  only holding whose price moves — a chart of the dollar rate would be a chart of the rand, and
  the stablecoins are a dollar each by definition. It is drawn as plain SVG with every
  coordinate worked out in `chart.py`, so there is no charting library and the browser is
  handed nothing to calculate. **More days are handed over than are drawn**, `LEAD_DAYS` of
  them, so that both averages and the strip have a figure on the window's very first day rather
  than starting part way across it. The lead reaches back further than the year CoinGecko will
  serve, so it comes from `prices.py` — the analysis page's longer history — while the days
  drawn are the ledger's own rates, `rates.btc_history`, asked for inside that year so they are
  one download and no gaps. The lead is never drawn, never labelled and never stored: every
  point on the line, every price on the axis and every figure a hover shows is still the
  ledger's own rate, and the lead only gives the lines their days behind them. One provider
  across the whole lead and one seam where the two meet, rather than the two alternating day by
  day; a history that cannot reach that far back gives no lead at all, and the long average and
  the strip are left off rather than drawn starting late. **The close is coloured by the averages**: green on the days the
  26-day is above the 260-day and purple on the days it is below, drawn as runs that share the
  point they turn on so the line has no gap at a crossing. It is a reading of the two lines
  already on the chart and nothing more — no signal, no advice, and nothing anywhere in the
  ledger acts on it. The lines are named in a legend, the close by what its colour means, and
  every pair of colours holds apart for a colour-blind reader as well, which is what rules out
  the obvious blue, red and violet. The price is labelled down both sides of the plot, being the same scale twice so that
  the right-hand end of a long window can be read without tracking back across it; the
  gridlines fall on round figures, since a line exists to be read off, and it is their number
  that gives rather than the gap between them. There is no zoom and no range picker — hovering
  a day shows its date and close, and that is the whole of the interaction. The lines carry no
  fill, because the axis does not start at zero and a filled area reads as a quantity measured
  from a baseline that is not there. **Under the plot, on the same dates, is a strip**: the close
  against where it stood `CHANGE_SPAN` days before — the long average's span, which is also the
  furthest back the chart already downloads — over a zero line of its own, and filled to it, the
  baseline here being real and the whole reading. It is **the one figure that tracks whether holding
  has beaten the analysis page's plans**: over the history priced, holding beat the best of them in
  most windows the price ended above that line and lost to them in most windows it ended below it,
  a correlation of about 0.95 and the reason the strip exists. It is **not** a signal and must never
  become one — trailing readings were tested against the stretches that followed them and none
  carried, holding still coming out ahead in two thirds or more of every forward stretch measured,
  including those beginning at the lowest readings. Do not add a threshold, an alert or a
  recommendation to it; it has exactly the standing the crossings have. It is deliberately drawn in
  the text colour rather than a pair of its own, since the close above it is already coloured for a
  different reading and two colour pairs on one picture read as one statement. The chart is loaded
  into the page by htmx after it renders: the first load of a window has to download it, and the
  balances are what the page is for.
- **The profit chart** sits between the accounts page's totals and its list of accounts: one
  stacked bar a week for the last 100 weeks, every account in it, priced at that week's rates. It
  is the *profit* card drawn as a history — the same figures the cards show, across two years
  rather than only today, which is the one thing the totals cannot say. Weeks rather than days
  because two years of daily bars is a smear: a week is the shortest bar a holding this slow
  actually changes over. **Weeks are counted back from today in sevens** rather than run off the
  calendar, so the last bar is where the ledger stands now, every earlier one is the same weekday
  before it, and no bar is a part week; each is shown at its **close**, the latest day in it the
  ledger can price, which is a real day's figures rather than an average of the seven. The stack
  straddles the axis: the money put in hangs below it and what that money is holding stands above,
  the two signs running away from the axis rather than cancelling, so the profit is what is left
  when the two ends are added back together. **The crypto stacks on top**, above the stablecoins,
  because it is the only holding whose price moves and so the only segment that changes shape —
  under a block that does not move its own movement could not be followed. `GROUPS` in `models.py`
  is that order, and the accounts page's three subtotals are the same three groups. The
  difference between two stacks cannot be read by eye, so **the profit is drawn over the bars as a
  white line**, with a straight least-squares **trendline** through it. The trend says which way
  the window went and nothing else — like the price chart's crossings it is a reading of what is
  already on the plot, and nothing in the ledger acts on it. Hovering a bar names the week it
  closes, every account's value in it, and the net named the way the accounts page names it: a
  profit, or a *loss* when it is negative. Accounts take a colour each from a fixed list cycled if
  there are more accounts than colours, holding apart for a colour-blind reader for the same
  reason the price chart's lines do; the profit and the trend are both white, one solid and one
  dashed, so neither can be taken for an account. It loads by htmx like the price chart, and for
  the same reason. An account that is empty right across the window is left off altogether, and a
  week the ledger cannot price every account for is left out rather than drawn part-known.
- **The weeks behind the profit chart are cached**, by `history.py`, through Django's cache
  framework — `CACHES` in settings, the file-based backend, on disk because the figures have to
  outlive the process to be worth keeping. **Everything sits under one key**, `CACHE_KEY`, so there
  is one file: it is replaced whenever the weeks move rather than added to, which is why nothing
  expires. A week that has closed cannot change unless the ledger does — only today's rate is ever
  downloaded again — so a boot or a page load **works out the week in progress**, tops up any week
  that has turned over since, and takes the rest as they are. Do not hand-roll the file handling
  again: serialising, replacing and locating the file are the cache framework's job.
  It is **a cache and never a record**: every figure in it can be worked out again from the
  transactions and the rates, so an entry that is missing or out of date costs a recalculation and
  never a wrong number, and clearing it is always safe. Being out of date is the part worth care,
  since any transaction here can be edited or backdated. The weeks are stored beside **a stamp of
  the accounts and entries they were read from**, and a stamp that no longer matches throws all of
  them away rather than only the recent ones — there is no cheap way to tell which weeks a
  correction moved, and a chart drawn off a balance that has since been corrected is worse than one
  worked out again. The stamp costs a hash and no query, since the entries are already in hand for
  the balances. Each week's close is worked out from the days actually priced rather than read back
  off the cache, so a close that moves comes out as a week the cache does not hold. A load that
  changes nothing leaves the cache alone instead of writing back what it just read. `wsgi.py` warms
  it as the server comes up, next to the rate download and guarded the same way.
- **Transactions** are double entry: one transaction moves value out of one account and into
  another, so it has two sides. Entered from a page on one account, choosing the other
  account as the counterpart. A transaction may instead be **one-sided**, with a single entry
  and no counterpart chosen — value that came from or went to somewhere the ledger keeps no
  account for. That is the only way a transaction has other than two entries; do not invent a
  plug account to face it, since a holding nobody holds is worse than a blank. A one-sided
  transaction matches FIFO like any other. A debit increases an account, a credit decreases
  it. A transaction is dated to the day — `occurred_on` is a `DateField` and there is no time of
  day anywhere in the ledger. Rates are per day and a hand-kept ledger does not know the
  minute; transactions sharing a date are ordered by the order they were entered. A
  transaction can be deleted only while it is the last one on every account it touches —
  deleting an earlier one would pull a lot out from under the matching that came after it.
  Any transaction can be **edited**, whenever it happened: the same form, filled in from the
  transaction as the account it was opened from sees it, correcting the date, either quantity,
  the account on the other side, or whether it matches. Editing is not the same risk as
  deleting, because the lot stays there — so instead of refusing, saving replays the matching.
- **Matching is replayed, never patched.** Recording, editing or deleting a transaction throws
  away the FIFO matches on every account it touches — the accounts touched before an edit as
  well, since the other side can be moved to a different account — and replays them oldest
  first. FIFO is deterministic, so the replay gives the matching the ledger would have reached
  had it always read that way. Creating replays for the same reason editing does: entering a
  purchase that was forgotten hands the sales already recorded after it a lot they should have
  consumed, and nothing short of a replay finds it. Deleting replays because same-date
  transactions match in the order they were entered, so even the last transaction on an
  account can be a lot that an earlier credit consumed. There is deliberately no button to
  match one credit by hand: matching is not something the user does, it is something that is
  true of the ledger, and one credit matched out of step is a number nobody can read a tax
  return off. Whether a transaction takes part at all is the `match_fifo` tick box on its
  form, stored on the transaction so that every replay honours it — a disposal left open on
  purpose stays open. It has to be stored rather than read back off the matches, because a
  credit entered before the lot covering it has no matches either, and a replay must tell the
  two apart; inferred, the backdated purchase that finally covers it would pass it over.
- **FIFO matching** is the point of the whole thing. A credit (a disposal — selling BTC) is
  matched against the earlier unmatched debits (acquisitions) on that account, oldest first,
  consuming each one fully before moving to the next, until the credit is fully matched or
  there is nothing left to match against. A debit dated the same day as the credit is
  eligible. Matching is optional on a transaction and may be
  partial; a debit carries a remaining unmatched quantity that shrinks to 0 as credits eat it.
  Always FIFO — never LIFO, never specific-lot, never an average cost.
- **Capital gains** are read off the matching, never stored. **The rows that give up a crypto**
  carry an icon through to a page working out that transaction's proceeds, base cost and gain,
  plus the method written out at the bottom of the page. Those are the disposal's own row on the
  wallet the crypto left, and the rand row facing it on a sale — a sale is read from the bank as
  often as from the wallet, and both reach the one page, on the wallet. A row that gives up no
  crypto has no icon: buying a crypto with rands, and an asset arriving with its details lost,
  create a base cost and give up nothing, so there is nothing on them to declare; and the crypto
  acquired in a swap has none either, since that swap is declared from its own row on the account
  it happened on. The disposal is the credit side, and the
  proceeds are what came in for it, valued on the day. The base cost is what the FIFO lots it
  consumed cost on the days *they* were acquired, and the trail stops there — a lot bought with
  rands cost what left the bank, and one swapped out of another crypto cost what it was worth
  the day it arrived, which is the same figure declared as the proceeds of that swap, so the two
  sides agree. Every crypto-to-crypto swap is a disposal in its own right, declared on its own
  page, reached from its own row on the account it happened on — a lot's row says where it came
  from but does not carry the other transaction's workings. Clicking a lot's row goes to the
  account holding it, scrolled to that transaction and briefly highlighted. There is exactly one
  way to arrive at a base cost here
  and there must stay exactly one — chasing swaps back to the original rands gives a second,
  equally arguable number, and a tax return with two answers to one question is worse than
  either. Crediting rands is not a disposal (the base currency cannot gain against itself) and a
  transaction with no credit at all is an asset arriving with its details lost; both still get a
  page, showing the base cost they create and no gain.
- **The capital gain page is filed from**, so it carries what a return asks for and not just the
  arithmetic. Every rand figure on the page must be traceable to the record behind it — a rate
  shown with its date and source, a cash cost shown as cash with no rate against it, since a
  return that cannot say where a number came from is worse than one that shows a smaller number
  honestly. A disposal consuming several lots splits its proceeds across them pro rata, rounded
  to the cent with the last lot taking the rounding, because a return wants one date acquired per
  line and such a disposal is several lines; the split must always add back to the proceeds
  exactly. The method at the foot of the page, and of the report, both say what these disposals
  are: the holdings are a long-term capital investment and the disposals are small balancing
  moves between them, declared in full even though nothing was cashed out. The annual exclusion
  is nowhere in the ledger: it belongs to a whole year rather than to any one disposal, and
  working it out is the return's job, not this app's. The lots consumed sit in a collapsed
  `details.section`, so the page opens on the three figures and the workings are there for whoever
  wants them. There is no print stylesheet and no print button anywhere: this is a screen the
  owner reads, and the figures go onto a return by being typed into one.
- **The tax year report** is the one report and the one period in the ledger, reached from a
  button and a year picker in the navbar's settings dropdown. It lists every disposal in a SARS
  tax year — 1 March to the end of February, named for the February it ends in — with its
  proceeds, base cost and gain, and totals the three. It defaults to the last tax year to have
  ended, since that is the one there is a return to file for, not the one in progress. Only
  disposals are listed: a purchase or an arrival creates a base cost but gives up nothing, so
  there is nothing on it to declare. Each row is `cgt.trace` on that transaction, and clicks
  through to its own page for the lots behind it — the year total and the per-transaction page
  can never disagree, because they are the same calculation.
- **The analysis page** is the one place that asks what a plan *would* have come to, and it answers
  only by reading the past. `WEEKLY_CONTRIBUTION` arrives from outside every week over the whole
  history and goes into a rand wallet or a Bitcoin wallet; it is contributed and never taken out of
  the rand wallet, so every combination is handed the same money and ranking them by what they
  finished with *is* ranking them by profit. Where it goes is two moving averages of the BTC price,
  the long being the short times a multiplier — so the grid asks how far apart the two must be
  rather than pinning a length on each. Two plans, `PLANS` in `backtest.py`, and they are **the one
  reading taken the two ways round**: **Bitcoin on a rise** buys BTC while the short average is over
  the long and sells back into rands while it is under, and **Bitcoin on a fall** does the exact
  opposite. Neither is the sensible one and the other the perverse one — which way round the history
  rewarded is the question, and it is asked by running both, so do not drop one for looking wrong.
  One average is always over the other, so there is always a reading and a plan never sits a week
  out; there is no third plan and no condition beyond the two averages, since a rule needing more
  than that is one a sweep this size cannot say much about. On the same reading each week also moves
  a percentage of one wallet into the other, always taken from the wallet it leaves so neither can
  be spent past empty. A **fee** is charged on everything that crosses between the wallets — the
  move both ways, and the contribution too on the weeks it buys BTC rather than landing as rands —
  taken off the amount converted, the way an exchange takes it. A week that only puts rands in the
  rand wallet converts nothing and pays nothing, and a fee of 0% is a plan costed as though it were
  free, which is worth being able to see. **The fee is set once for the whole sweep and never swept
  over**: what an exchange charges is a fact about where the money is held, not a setting to go
  looking for the best value of, and a sweep asked to optimise it would only ever answer "pay less".
  So it is one slider rather than a range, it is no part of the combination count, and seeing what a
  dearer exchange costs means moving it and running again. **The window is set the same way** —
  `years`, one slider from one to fifteen, `prices.within` trimming the history that is already
  downloaded rather than fetching a different one. It is not swept for the fee's reason: a plan run
  over a different stretch of history is a different question, not a better answer to this one.
  Fifteen is a ceiling and not a promise, the prices beginning in September 2014, so asking for more
  than there is gives the whole of it and the page prints the dates it actually covered. A window
  too short for the averages set is said so plainly rather than drawn as an empty sweep.
- **The analysis page's ranges are set on the page** as a pair of sliders each, a lowest and a
  highest for every setting in `DEFAULTS`, and **nothing runs until Run is pressed** — a sweep is
  worth choosing rather than being handed, and the answer to one grid is usually a reason to try
  another. `DEFAULTS` in `backtest.py` is what the sliders open on the first time and `BOUNDS` is
  how far they go; **the settings behind the last sweep that ran are remembered**, by
  `preferences.py` through the same cache framework the profit chart's weeks use, so the page
  opens where it was left rather than back at the defaults every time the server comes up. They
  are kept on the server rather than in the browser because the page is rendered there — the
  sliders arrive already in place instead of jumping once a script has run — and they are read
  back through the form that wrote them, exactly as a slice of a sweep is, so an entry from
  before a bound moved cannot draw the page outside what a sweep will now run. It is a
  convenience and never a record: settings missing, unreadable or turned away cost the defaults
  and never a wrong figure, so clearing the cache is always safe. Both plans are always run,
  since comparing them is what the page is for. The sweep is
  **exhaustive** — the default grid is 660 combinations in about a sixth of a second — because a grid
  this size gives the exact answer where an optimiser gives an approximation, and that is why there
  is no numeric library here. What keeps it exhaustive is the cap: `MAX_COMBINATIONS` turns a grid
  away with its own count rather than letting it run, because a page that never finishes says less
  than a smaller grid that does. **The sliders hold themselves to that cap as they are dragged**:
  widen one and the widest of the others gives up a step, then the widest again, until the grid
  fits — a step at a time rather than one cut, so the ranges stay as near what was asked for as the
  cap allows, and never the one being dragged while any other can still give. That is a convenience
  and not the rule; the form checks the same cap on arrival, for everything reaching it another way.
  A winner sitting at the end of a range is worth saying so about, since the best setting is then
  probably outside it. The sweep runs in slices fetched by htmx, each asking for the next, so the
  results fill in as they come. **The grid and `?done=` are the whole of the state**: a fixed grid
  in a fixed order means any prefix can be worked out again from the query string alone, so there is
  no run to keep hold of and nothing to go stale between requests. The slice is scaled to the grid
  rather than fixed, since each request works out everything up to its own end — a fixed batch would
  deliver a small grid in one lump and a large one in hundreds of requests re-treading the same
  ground. Every slice is read back through the same form the page submits, so a hand-edited URL is
  checked exactly as the form was rather than trusted for having come from us.
- **Every sweep is set against a baseline**: the same R 1 000 a week straight into BTC, never sold,
  paying the same fee on each purchase. `hold` in `backtest.py`. It is not a plan and is never
  swept — there is nothing in it to vary — but a ranking of plans against each other cannot say
  whether any of them was worth running, and this can. It is started from **the same first week as
  the plan it sits beside** (`combo["long"] - 1`), because a baseline handed different money over a
  different number of weeks is not one; the contributed figures must come out identical, and that is
  worth checking whenever this is touched. It shows as a card by the winner, as a card on a plan's
  own page, and as **a line across the results chart** — marks above it beat doing nothing, marks
  below it did not. On the ten years downloaded, nothing beats it: the honest reading of the sweep
  is that it ranks plans by how little they cost against simply holding, and that is the reading
  the page should support rather than hide.
- **A sweep is reported one setting at a time**, never as a leaderboard. `report` in `backtest.py`
  gives a table per setting in `TABS`, listing every value that setting was swept over against the
  best result found at it — because a sweep is run to find out what a setting is worth, and the top
  ten of a grid are usually the same setting ten times over, which says nothing about the nine
  values it beat. **Each table is complete in itself and ranked by profit**, best first, so the
  order down it is that setting's own answer; the plan's table is therefore two rows, and which of
  them is on top is the answer to which way round the history rewarded. **A combination that leads
  more than one setting is listed in every table it leads** — the overall best is normally the top
  row of all of them, and holding it back from the later tables to avoid repeating it would leave
  those tables headed by something that is not their best. The tables are tabbed rather than
  stacked, since several of the same shape run down one page read as one long table. The column
  being read down is picked out on its own rows, a table being legible only if it says which figure
  is the one varying. `TABS` is deliberately not every setting: the short average is swept like the
  rest but has far more values than the others, and a table two hundred rows long answers nothing;
  the fee is not swept at all, so there is only ever one value of it to report.
- **The sweep keeps no weeks.** `search` holds each combination's totals only: at the cap that is
  five thousand walks through five hundred weeks, and keeping every one of them costs hundreds of
  megabytes to answer a question nobody asked. Anything wanting the weeks — the equity chart, a
  plan's own page — calls `replay`, which is one walk and costs nothing worth saving. **Every
  combination is four numbers**, so a plan's page is reached by naming them in a query string and
  running it again; there is deliberately nothing kept between the two pages, and being able to
  recalculate freely is what makes that so. The figures are
  **floats, not `Decimal`** — the one place in the ledger that is true — because this is a simulation
  and not a rand that goes on a return; they become `Decimal` at `equity_weeks`, where the chart
  takes them. The page must say on its face that it is a reading of history swept with nothing held
  back, that it recommends nothing, and that no part of the ledger acts on it — the same standing
  the price chart's crossings have.
- **The long history is not the ledger's rates**, and must never become them. CoinGecko's
  public API refuses anything older than a year, so `prices.py` downloads everything there is from
  Yahoo instead — a shade under twelve years, and the window slider trims it: BTC's daily close in dollars times the daily rand price of the dollar, the mirror of the
  division `rates.py` does. The dollar rate is carried forward over the days the currency market is
  shut, since BTC closes on all of them. It is cached under one key like the profit chart's weeks,
  refetched once a day, and **deliberately never written into `ExchangeRate`** — a figure on a
  return has to be traceable to one source, and two providers quoting a day a shade apart is exactly
  the doubt that must not get into the ledger. Do not "improve" this by backfilling the rates table
  from it. It is a cache and never a record, and `RATES_DOWNLOAD` switches it off with everything
  else, which is how the tests stay off the network. The **price chart's lead** is the one other
  thing read out of it, `lead`: the days behind the home page's window, which reach back further
  than CoinGecko will serve. That stays on the right side of the same line — a lead is never
  drawn, never labelled and never stored, so no figure anyone reads comes from it, and it is
  wanted precisely because it is the one series long enough to give the 260-day average and the
  change strip a figure on the window's first day.

## Tech stack

- Python 3.13.1 (pinned in `.python-version` and `requires-python = "==3.13.1"`)
- Django 6.1
- SQLite (default `DATABASES` config, `db.sqlite3`)
- requests, against the public CoinGecko API (no key) for the ledger's ZAR prices, and against
  Yahoo Finance's chart endpoint (no key) for the decade of prices the analysis page is swept over
  — CoinGecko's public API goes back only a year. Nothing else is downloaded from anywhere
- htmx 2, vendored at `main/static/main/htmx.min.js` rather than loaded off a CDN, so the app
  keeps working with no connection. It is the only JavaScript library here and it fetches
  fragments of the page — anything it loads is a normal Django view rendering a template
- uv for dependency and environment management
- pytest + pytest-django for tests (`DJANGO_SETTINGS_MODULE` set in `pyproject.toml`; tests
  live in the top-level `tests/` package, not in the app)
- ruff for lint and format (broad ruleset, configured in `pyproject.toml`)
- pre-commit for the git hook pipeline: ruff check/format, django-upgrade, uv lock check,
  and the standard pre-commit-hooks file checks

## Layout

- `crypto_ledger/` — Django project package: `settings.py`, `urls.py`, `wsgi.py`, `asgi.py`.
  `wsgi.py` calls `rates.refresh_at_startup()` after `get_wsgi_application()`, which is the
  only place a server boot reaches the network, and then `history.warm()` off those prices. The
  imports there have to sit below that call, since nothing can touch the models until Django has
  loaded the apps
- `main/` — the app holding the project's main code; new models, views, and URLs go here
  unless there is a clear reason for a separate app. `models.py` holds `Account`,
  `Transaction`, `Entry`, `Match` and `ExchangeRate`; `matching.py` holds the FIFO algorithm
  and nothing else; `rates.py` holds the price downloads and ZAR conversion and nothing else;
  `cgt.py` reads the matches back into a base cost and a gain and writes nothing; `history.py`
  reads the ledger back week by week and keeps those weeks in its cache file; `preferences.py`
  keeps the settings the analysis page was last run with and nothing else; `prices.py` holds the
  years of prices the analysis page is swept over and the price chart's lead sits on, and touches
  no model; `backtest.py` holds the investment plans
  and the sweep over them and reads nothing at all; `chart.py`
  turns a dated series — prices, a week's holdings, or a sweep's results — into SVG coordinates and
  reads no database. `static/main/` holds the vendored htmx
- `tests/` — the pytest suite, outside the app
- `manage.py` — Django CLI entrypoint

An `Entry` stores a signed quantity: positive is a debit, negative is a credit. The two
entries of a transaction are not equal and opposite — a BTC/USD trade moves different
quantities on each side — so balances only ever sum within one account.

New apps must be added to `INSTALLED_APPS` in `crypto_ledger/settings.py`.

## Rules

### Keep the README describing what the project is

`README.md` must always say what the project is and what it does, not just how to install it.
Whenever a change alters what the app is for or how it behaves for the user, update the
README's description in the same change. Behaviour changes include:

- adding, removing, or reshaping a user-facing concept (accounts, transactions, matching)
- changing a rule the user relies on (how FIFO matching picks lots, what a transaction means)
- adding or removing a screen or workflow

Keep it short and concrete — a reader who has never seen the repo should understand what the
app does within the first few paragraphs. Describe what is built, not what is planned. When
the domain changes, the `## Domain` section of this file changes with it.

### Word the ledger for a tax official reading it

The figures here go on a SARS return, so the words around them have to hold up as well as the
numbers do. Two things follow, and both cover every user-visible string — templates, form labels
and help text, messages and the README.

- Where the ledger holds no record of the other side of a transaction, call it **details lost**
  — never "outside the ledger" or any other phrase suggesting value sits somewhere deliberately
  unrecorded. Wording that reads as assets being kept off the books invites the suspicion of
  hiding them, when the plain fact is that the paperwork is gone.
- The holdings are a **long-term capital investment**, and the disposals are small balancing
  moves between assets. Never describe them as trading, and do not raise the capital-versus-
  revenue question in the app at all — the answer is settled, and a page that argues both sides
  of it reads as a doubt the owner does not have.

### Keep these rules in sync with my preferences

When the user states a preference about how work should be done — a correction, a "always do
X", a "never do Y", or an approach they confirm they like — add it to this file's `## Rules`
as part of that same change, so it holds for every later session.

- Write it as a rule, in the imperative, with the reasoning that motivated it. A rule whose
  "why" is missing gets misapplied at the edges.
- Fold it into an existing rule if one already covers the area, rather than adding a near
  duplicate. If the new preference contradicts an existing rule, replace the old wording —
  never leave both standing.
- Only durable preferences belong here. A one-off instruction for the current task ("skip the
  tests this time") is not a rule.
- Do not silently widen a preference. If it was stated about one narrow case, write it about
  that case, and ask before generalising it.

### Keep docs in sync with the tech stack

Whenever a change touches the tech stack, update `README.md` and this file (`CLAUDE.md`)
in the same change. Stack changes include:

- adding, removing, or replacing a dependency in `pyproject.toml`
- changing the Python version (`.python-version` and `requires-python` must stay identical)
- changing tooling: package manager, test runner, linter/formatter, task runner, CI
- adding a new component, service, or datastore

Both files must describe the stack that is actually in the repo — no planned or removed tools.
If a change makes a documented setup step wrong, fix the step, don't just append to it.

### Keep tests basic

Test only the basic outcome of a unit: the ordinary case, the thing the unit exists to do.
Assert the result, not the steps taken to reach it. One test per unit is the norm — if a unit
needs several, it is doing several things and should be split instead.

A basic test for `match_credit_fifo` is: a credit consumes an earlier debit. It is not a
sweep of partial matches, backdated debits, zero quantities and re-runs.

Leave out unless explicitly asked:

- edge cases, boundary values and unusual input combinations
- error and validation paths, unless the error *is* what the unit is for
- tests that only exercise Django itself — a constraint firing, a field round-tripping
- further variations of a case already covered

The point of the suite is a fast check that each unit works, not a proof that it cannot be
broken. This is a single-developer ledger where the data is entered by hand and mistakes are
visible on the page; exhaustive tests cost more to keep current than they catch here. Time
saved on tests goes into the code being simple enough not to need them.

### Run ruff after every change

When a change is finished, run `uv run ruff format .` and then `uv run ruff check .`, and fix
what they report before saying the work is done. Do it as the last step of every change, not
just the big ones — a one-line edit breaks the lint as easily as a new module does, and lint
found at commit time or in a later session costs more to place than lint found while the
change is still in mind. Reporting a change as finished means it is formatted and clean.

### Work on main, never on a branch

This is a single-developer repo with a linear history. All commits go directly to `main`.

Do not create branches, switch branches, or open pull requests — not for large changes,
not for risky ones, not "to be safe". If a change feels too big for `main`, split it into
smaller commits on `main` instead. The only exception is an explicit request for a branch.

### Never commit unless told to

Do not run `git commit`, `git push`, `git merge`, or any other history-changing command
unless the user asks for it in that message. Finishing a task means leaving the changes in
the working tree and saying what changed — not committing them. "Commit this" applies to
that commit only; it is not standing permission for the next one.

Staging (`git add`) and read-only inspection (`status`, `diff`, `log`) are fine at any time.

### Commit messages list the changes

`git log` is the source for the changelog, so every commit body must enumerate what actually
changed. Format:

```
<subject: imperative, <= 72 chars, no trailing period>

<optional one or two lines of context: why this change exists>

- <change 1>
- <change 2>
```

Rules for the bullets:

- One bullet per user-visible or behavioural change, written so it can be pasted into a
  changelog without editing: say what changed, not which file was touched.
  Good: `Add Transaction model with amount, asset and timestamp fields`.
  Bad: `Update models.py`.
- Cover every change in the commit. If the list runs past roughly seven bullets, the commit
  is doing too much — split it.
- Prefix bullets that need it: `BREAKING:` for anything requiring manual action (migrations
  that drop data, renamed settings, changed env vars), `Fix:` for bug fixes.
- Leave out pure noise — formatter reflows, lint fixes with no behaviour change — unless
  that is the entire point of the commit.

## Commands

- Install: `uv sync`
- Migrate: `uv run python manage.py migrate`
- Run server: `uv run python manage.py runserver`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Run all hooks: `uv run pre-commit run --all-files`
- Bump hook versions: `uv run pre-commit autoupdate`

Lint must stay clean. Suppress a rule in `[tool.ruff.lint.per-file-ignores]` with a comment
explaining why, rather than sprinkling `# noqa` or disabling the rule repo-wide.
Migrations are excluded from ruff entirely — never hand-edit them to satisfy the linter.
