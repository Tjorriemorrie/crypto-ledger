# crypto-ledger

Manually keep track of your crypto transactions

## Tech stack

- Python 3.13.1
- Django 6.1 — web framework (project package `crypto_ledger`, app `main`)
- SQLite — default database (`db.sqlite3`)
- [uv](https://docs.astral.sh/uv/) — dependency and environment management
- pytest — tests
- ruff — lint and format
- pre-commit — git hooks running ruff, django-upgrade and file checks

## Layout

- `crypto_ledger/` — Django project settings, URLs, WSGI/ASGI entrypoints
- `main/` — the main app, where project code lives
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
