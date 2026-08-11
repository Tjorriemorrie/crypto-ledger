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
