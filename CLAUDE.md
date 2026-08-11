# crypto-ledger

Manually keep track of your crypto transactions.

## Tech stack

- Python 3.13.1 (pinned in `.python-version` and `requires-python = "==3.13.1"`)
- Django 6.1
- SQLite (default `DATABASES` config, `db.sqlite3`)
- uv for dependency and environment management
- pytest for tests
- ruff for lint and format (broad ruleset, configured in `pyproject.toml`)
- pre-commit for the git hook pipeline: ruff check/format, django-upgrade, uv lock check,
  and the standard pre-commit-hooks file checks

## Layout

- `crypto_ledger/` — Django project package: `settings.py`, `urls.py`, `wsgi.py`, `asgi.py`
- `main/` — the app holding the project's main code; new models, views, and URLs go here
  unless there is a clear reason for a separate app
- `manage.py` — Django CLI entrypoint

New apps must be added to `INSTALLED_APPS` in `crypto_ledger/settings.py`.

## Rules

### Keep docs in sync with the tech stack

Whenever a change touches the tech stack, update `README.md` and this file (`CLAUDE.md`)
in the same change. Stack changes include:

- adding, removing, or replacing a dependency in `pyproject.toml`
- changing the Python version (`.python-version` and `requires-python` must stay identical)
- changing tooling: package manager, test runner, linter/formatter, task runner, CI
- adding a new component, service, or datastore

Both files must describe the stack that is actually in the repo — no planned or removed tools.
If a change makes a documented setup step wrong, fix the step, don't just append to it.

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
