# crypto-ledger

Manually keep track of your crypto transactions.

## Domain

A personal ledger for crypto and fiat holdings. Deliberately simplistic — it borrows
double-entry bookkeeping's one useful idea and nothing else. It is not accounting software:
no chart of accounts, no journals, no periods, no reports, no trial balance. If a feature
only makes sense to a bookkeeper, it does not belong here.

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
  once and kept. Only two assets are priced, `RatedAsset`: BTC and USD. The stablecoins are
  not priced separately — a USDT and a USDC are each held to be one dollar, so both are valued
  off the USD rate. One download covers both assets: CoinGecko quotes BTC in ZAR and USD at
  once, and dividing the one by the other gives the dollar rate. The current prices are
  downloaded when the server starts (from `wsgi.py`, so management commands and tests stay off
  the network) and from the refresh button on the accounts page; a past date is downloaded the
  first time something needs it. `RATES_DOWNLOAD = False` in settings switches all downloading
  off, which is how the tests run.
- **Transactions** are double entry: one transaction moves value out of one account and into
  another, so it always has two sides. Entered from a page on one account, choosing the other
  account as the counterpart. A debit increases an account, a credit decreases it. A
  transaction is dated to the day — `occurred_on` is a `DateField` and there is no time of
  day anywhere in the ledger. Rates are per day and a hand-kept ledger does not know the
  minute; transactions sharing a date are ordered by the order they were entered. A
  transaction can be deleted only while it is the last one on both accounts it touches —
  deleting an earlier one would pull a lot out from under the matching that came after it.
  There is no editing a transaction: delete the last one and enter it again.
- **FIFO matching** is the point of the whole thing. A credit (a disposal — selling BTC) is
  matched against the earlier unmatched debits (acquisitions) on that account, oldest first,
  consuming each one fully before moving to the next, until the credit is fully matched or
  there is nothing left to match against. A debit dated the same day as the credit is
  eligible. Matching is optional on a transaction and may be
  partial; a debit carries a remaining unmatched quantity that shrinks to 0 as credits eat it.
  Always FIFO — never LIFO, never specific-lot, never an average cost.

## Tech stack

- Python 3.13.1 (pinned in `.python-version` and `requires-python = "==3.13.1"`)
- Django 6.1
- SQLite (default `DATABASES` config, `db.sqlite3`)
- requests, against the public CoinGecko API (no key) for the ZAR prices
- uv for dependency and environment management
- pytest + pytest-django for tests (`DJANGO_SETTINGS_MODULE` set in `pyproject.toml`; tests
  live in the top-level `tests/` package, not in the app)
- ruff for lint and format (broad ruleset, configured in `pyproject.toml`)
- pre-commit for the git hook pipeline: ruff check/format, django-upgrade, uv lock check,
  and the standard pre-commit-hooks file checks

## Layout

- `crypto_ledger/` — Django project package: `settings.py`, `urls.py`, `wsgi.py`, `asgi.py`.
  `wsgi.py` calls `rates.refresh_at_startup()` after `get_wsgi_application()`, which is the
  only place a server boot reaches the network. The import there has to sit below that call,
  since nothing can touch the models until Django has loaded the apps
- `main/` — the app holding the project's main code; new models, views, and URLs go here
  unless there is a clear reason for a separate app. `models.py` holds `Account`,
  `Transaction`, `Entry`, `Match` and `ExchangeRate`; `matching.py` holds the FIFO algorithm
  and nothing else; `rates.py` holds the price downloads and ZAR conversion and nothing else
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
