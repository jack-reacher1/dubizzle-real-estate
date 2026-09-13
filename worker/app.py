from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid

import asyncpg
from fastapi import FastAPI, Header, HTTPException

from scraper import main as run_scraper

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("dubizzle_worker")

app = FastAPI(title="Dubizzle scraper worker")
_running_lock = threading.Lock()


async def _database_connection():
    return await asyncpg.connect(
        os.environ["DATABASE_URL"],
        statement_cache_size=int(os.getenv("ASYNCPG_STATEMENT_CACHE_SIZE", "0")),
        timeout=float(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10")),
        command_timeout=float(os.getenv("DB_COMMAND_TIMEOUT_SECONDS", "30")),
    )


def _run_scrape(run_id: str) -> None:
    asyncio.run(_run_scrape_async(run_id))


async def _run_scrape_async(run_id: str) -> None:
    conn = None
    try:
        conn = await _database_connection()
        log.info("Starting scraper run %s", run_id)
        try:
            await asyncio.to_thread(run_scraper)
        except SystemExit as exc:
            await conn.execute(
                "UPDATE scrape_runs SET status='failed', completed_at=now(), error_message=$2 WHERE run_id=$1",
                uuid.UUID(run_id), f"exit code {exc.code}",
            )
            log.error("Scraper run %s failed with exit code %s", run_id, exc.code)
            return
        except Exception as exc:
            await conn.execute(
                "UPDATE scrape_runs SET status='failed', completed_at=now(), error_message=$2 WHERE run_id=$1",
                uuid.UUID(run_id), str(exc),
            )
            log.exception("Scraper run %s failed", run_id)
            return

        await conn.execute(
            "UPDATE scrape_runs SET status='success', completed_at=now() WHERE run_id=$1",
            uuid.UUID(run_id),
        )
        log.info("Scraper run %s completed successfully", run_id)
    finally:
        if conn is not None:
            await conn.close()
        _running_lock.release()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.api_route("/run", methods=["GET", "POST"])
async def trigger_run(authorization: str | None = Header(default=None)):
    expected = os.getenv("WORKER_TRIGGER_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="Worker trigger secret is not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    if not _running_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A scraper run is already in progress")

    try:
        conn = await _database_connection()
    except Exception:
        _running_lock.release()
        log.exception("Could not connect to the database")
        raise HTTPException(status_code=503, detail="Could not connect to the database")

    try:
        locked = await conn.fetchval("SELECT pg_try_advisory_lock(hashtext('dubizzle-scrape'))")
        if not locked:
            raise HTTPException(status_code=409, detail="A scraper run is already in progress")
        run_id = str(await conn.fetchval(
            "INSERT INTO scrape_runs (status) VALUES ('running') RETURNING run_id"
        ))
    except HTTPException:
        _running_lock.release()
        await conn.close()
        raise
    except Exception:
        _running_lock.release()
        await conn.close()
        log.exception("Could not initialize scraper run")
        raise HTTPException(status_code=503, detail="Could not initialize scraper run")

    async def release_database_lock():
        try:
            await conn.execute("SELECT pg_advisory_unlock(hashtext('dubizzle-scrape'))")
        finally:
            await conn.close()

    async def worker_wrapper():
        try:
            await _run_scrape_async(run_id)
        finally:
            await release_database_lock()

    asyncio.create_task(worker_wrapper())
    log.info("Accepted scraper run %s", run_id)
    return {"status": "accepted", "run_id": run_id}
