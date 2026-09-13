# AGENTS.md

## Project snapshot

This repository is a Python-based Dubizzle scraper and API for the 5th Settlement market in Egypt. It mixes a FastAPI web app, a background worker, and a scraper pipeline that can run locally against CSV files or against PostgreSQL in production.

## Architecture

- The public app lives in [app.py](app.py). It serves the UI and exposes API routes such as `/api/listings` and `/api/listings/{ad_id}/lead-status`.
- The background worker lives in [worker/app.py](worker/app.py). It authenticates trigger requests, acquires a PostgreSQL advisory lock, and starts the scraper asynchronously.
- The scraping and normalization logic lives in [scraper.py](scraper.py). This is the main business logic for data collection, filtering, and persistence.
- Storage decisions are centralized in [database.py](database.py). Local runs default to CSV data; production should use PostgreSQL when `STORAGE_BACKEND=postgres`.
- Deployment and environment expectations are documented in [README.md](README.md). Use that as the source of truth for infra setup.
- Regression tests live under [tests/](tests). Favor targeted test runs over broad suites when iterating on a fix.

## Working conventions

- Do not assume PostgreSQL is always enabled. Local behavior is intentionally CSV-backed unless the environment explicitly sets `STORAGE_BACKEND=postgres` and `DATABASE_URL`.
- Keep API validation strict. The public listing API in [app.py](app.py) rejects unknown query parameters and validates sort and numeric filters.
- When touching scraper/worker code, preserve the existing dual-mode design: local CSV workflow and production PostgreSQL workflow.
- Respect the Render/Vercel split described in [README.md](README.md): Vercel Cron calls the app endpoint, and that endpoint triggers the Render worker rather than running the scraper directly inside Vercel.
- If you change anything that affects asyncpg or database locking, keep the worker concurrency guard and advisory-lock behavior intact.
- The project is sensitive to deployment secrets. Treat `CRON_SECRET`, `WORKER_TRIGGER_SECRET`, `WORKER_URL`, and `DATABASE_URL` as infrastructure concerns rather than app logic.

## Commands

- Install dependencies:
  - `pip install -r requirements.txt`
- Run the scraper locally:
  - `python scraper.py`
- Run the API locally:
  - `uvicorn app:app --reload --port 8010`
- Run the test suite:
  - `pytest -q`
- Run a focused test file:
  - `pytest tests/test_cron.py -q`

## Common pitfalls

- The worker uses a PostgreSQL advisory lock to prevent concurrent scraper runs. Do not remove or bypass this without checking the worker flow and tests.
- `asyncpg` prepared-statement caching has to be disabled in the app when using Supabase PgBouncer; do not “simplify” this away without verifying the DB behavior.
- The app depends on real Dubizzle page structure and `__NEXT_DATA__` parsing conventions. If a scraper change affects source-page structure, verify against the actual page contracts before rewriting the parser.
- The project keeps production-data truth in PostgreSQL and local-data truth in CSVs. Keep that boundary explicit when changing persistence code.

## AI agent workflow

- Start with the highest-signal files only: [README.md](README.md), [app.py](app.py), [worker/app.py](worker/app.py), [scraper.py](scraper.py), and the closest test file for the changed behavior.
- Use targeted search and narrow reads instead of broad repo exploration. Do not read the whole project when a single module and its tests explain the issue.
- Keep changes scoped to one layer at a time: API validation, scraper logic, or worker orchestration.
- For DB or concurrency changes, verify the worker lock and advisory-lock semantics before modifying behavior.
- For scraper/parser changes, confirm assumptions against the real Dubizzle page contract and the parsing code rather than rewriting from scratch.
- Prefer targeted test runs such as `pytest tests/test_cron.py -q` over the full suite when iterating.

## When editing code

- Prefer the smallest patch that matches the current architecture.
- Prefer targeted tests for the area being changed, then only broaden scope if the change affects shared behavior.
- Keep code and configuration aligned with the deployment model in [README.md](README.md).
- Do not duplicate deployment instructions in code comments when the repo already has canonical docs.

## Files to read first

- [README.md](README.md)
- [app.py](app.py)
- [worker/app.py](worker/app.py)
- [scraper.py](scraper.py)
- [tests/test_cron.py](tests/test_cron.py)
