# Copilot instructions for this repository

## Goal

Keep AI-assisted changes narrow, architecture-aware, and aligned with the real deployment model.

## Read order

1. [README.md](../README.md)
2. [app.py](../app.py)
3. [worker/app.py](../worker/app.py)
4. [scraper.py](../scraper.py)
5. The nearest test file for the behavior being changed

## Project rules

- Local runs are CSV-backed unless `STORAGE_BACKEND=postgres` and `DATABASE_URL` are set.
- The app and worker are intentionally separate: Vercel triggers the worker on Render instead of running the scraper directly in the frontend platform.
- Preserve the advisory-lock and concurrency guard in [worker/app.py](../worker/app.py).
- Keep API query validation strict in [app.py](../app.py); reject unknown parameters and validate numeric/sort filters.
- Do not rewrite parser logic without checking the real Dubizzle `__NEXT_DATA__` contract and the current scraper tests.

## Agent workflow

- Prefer targeted search and narrow reads over broad exploration.
- Prefer minimal patch sizes that match the current design.
- Validate with the smallest relevant test target, not the full suite by default.
- If a change affects storage, deployment, or scraper behavior, confirm the flow against [README.md](../README.md) before finalizing.
