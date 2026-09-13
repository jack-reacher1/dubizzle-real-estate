"""PostgreSQL persistence for the Dubizzle scraper and API.

The CSV functions remain available for offline imports and local regression tests,
but production code uses this module whenever DATABASE_URL is configured.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, is_dataclass
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg

LISTING_COLUMNS = [
    "ad_id", "ad_url", "listing_type", "property_type", "title", "price",
    "area_sqm", "bedrooms", "bathrooms", "completion_status", "payment_method",
    "ownership", "furnished", "location_text", "compound", "location_link",
    "amenities", "description_full", "phone_in_description", "posted_at",
    "updated_at", "scraped_at", "days_since_updated", "is_verified_business",
    "is_agency", "agency_name", "has_broker_code_pattern", "seller_repeat_count",
    "seller_id", "seller_name", "first_seen_date", "last_seen_date", "is_active", "lead_status",
]


def database_url() -> str | None:
    return os.getenv("DATABASE_URL") or None


def database_enabled() -> bool:
    backend = os.getenv("STORAGE_BACKEND", "csv").lower()
    return bool(database_url()) and (backend == "postgres" or os.getenv("VERCEL") == "1")


def _run(coro):
    return asyncio.run(coro)


class PostgresStore:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or database_url()
        if not self.dsn:
            raise RuntimeError("DATABASE_URL is required for PostgreSQL persistence")
        self.statement_cache_size = int(os.getenv("ASYNCPG_STATEMENT_CACHE_SIZE", "0"))
        self.connect_timeout = float(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10"))
        self.command_timeout = float(os.getenv("DB_COMMAND_TIMEOUT_SECONDS", "30"))

    @asynccontextmanager
    async def connection(self):
        conn = await asyncpg.connect(
            self.dsn,
            statement_cache_size=self.statement_cache_size,
            timeout=self.connect_timeout,
            command_timeout=self.command_timeout,
        )
        try:
            yield conn
        finally:
            await conn.close()

    def load_sellers_cache(self) -> dict[str, dict]:
        return _run(self._load_sellers_cache())

    async def _load_sellers_cache(self) -> dict[str, dict]:
        async with self.connection() as conn:
            rows = await conn.fetch("SELECT * FROM sellers ORDER BY seller_id")
        return {str(row["seller_id"]): _db_seller_row(row) for row in rows}

    def save_sellers_cache(self, cache: dict[str, dict]) -> None:
        _run(self._save_sellers_cache(cache))

    async def _save_sellers_cache(self, cache: dict[str, dict]) -> None:
        async with self.connection() as conn:
            async with conn.transaction():
                for row in cache.values():
                    await conn.execute(
                        """
                        INSERT INTO sellers
                          (seller_id, seller_name, profile_url, active_ads_count,
                           active_ads_count_source, classification, checked_at,
                           blocklist_permanent)
                        VALUES ($1, $2, $3, $4, $5, $6, $7::timestamptz, $8)
                        ON CONFLICT (seller_id) DO UPDATE SET
                          seller_name = EXCLUDED.seller_name,
                          profile_url = EXCLUDED.profile_url,
                          active_ads_count = EXCLUDED.active_ads_count,
                          active_ads_count_source = EXCLUDED.active_ads_count_source,
                          classification = EXCLUDED.classification,
                          checked_at = EXCLUDED.checked_at,
                          blocklist_permanent = EXCLUDED.blocklist_permanent
                        """,
                        row.get("seller_id"), row.get("seller_name") or None,
                        row.get("profile_url") or None,
                        _int_or_none(row.get("active_ads_count")),
                        row.get("active_ads_count_source") or None,
                        row.get("classification") or None,
                        row.get("checked_at") or None,
                        _as_bool(row.get("blocklist_permanent")),
                    )

    def load_existing_ads(self) -> dict[str, dict]:
        return _run(self._load_existing_ads())

    async def _load_existing_ads(self) -> dict[str, dict]:
        async with self.connection() as conn:
            rows = await conn.fetch("SELECT * FROM listings")
        return {str(row["ad_id"]): _db_listing_row(row) for row in rows}

    def merge_and_save(self, new_listings: list[Any], retention_days: int) -> None:
        _run(self._merge_and_save(new_listings, retention_days))

    async def _merge_and_save(self, new_listings: list[Any], retention_days: int) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        seen_ids = {listing.ad_id for listing in new_listings}
        async with self.connection() as conn:
            async with conn.transaction():
                prior_rows = await conn.fetch("SELECT ad_id, ad_url, first_seen_date FROM listings")
                prior = {str(row["ad_id"]): row for row in prior_rows}
                for listing in new_listings:
                    row = asdict(listing) if is_dataclass(listing) else dict(listing)
                    ad_url = row.get("ad_url") or (prior.get(listing.ad_id) or {}).get("ad_url")
                    values = [_db_value(column, row.get(column)) for column in LISTING_COLUMNS]
                    values[1] = ad_url
                    values[30] = (prior.get(listing.ad_id) or {}).get("first_seen_date") or today
                    values[31] = today
                    values[32] = True
                    placeholders = ", ".join(f"${index}" for index in range(1, len(LISTING_COLUMNS) + 1))
                    updates = ", ".join(
                        f"{column} = EXCLUDED.{column}"
                        for column in LISTING_COLUMNS[1:]
                        if column not in {"first_seen_date", "lead_status"}
                    )
                    await conn.execute(
                        f"INSERT INTO listings ({', '.join(LISTING_COLUMNS)}) VALUES ({placeholders}) "
                        f"ON CONFLICT (ad_id) DO UPDATE SET {updates}",
                        *values,
                    )
                if seen_ids:
                    await conn.execute(
                        "UPDATE listings SET is_active = FALSE WHERE NOT (ad_id = ANY($1::text[]))",
                        list(seen_ids),
                    )
                else:
                    await conn.execute("UPDATE listings SET is_active = FALSE")
                await conn.execute(
                    """
                    DELETE FROM listings
                    WHERE NOT is_active
                      AND COALESCE(last_seen_date, updated_at, posted_at, first_seen_date)::date
                          < current_date - $1::int
                    """,
                    retention_days,
                )

    def configure_eligibility(self, freshness_days: int, owner_recheck_days: int) -> None:
        _run(self._configure_eligibility(freshness_days, owner_recheck_days))

    async def _configure_eligibility(self, freshness_days: int, owner_recheck_days: int) -> None:
        async with self.connection() as conn:
            await conn.executemany(
                """
                INSERT INTO app_config (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                """,
                [("freshness_days", str(freshness_days)), ("owner_recheck_days", str(owner_recheck_days))],
            )

    def business_count(self, freshness_days: int, owner_recheck_days: int) -> int:
        return _run(self._business_count(freshness_days, owner_recheck_days))

    async def _business_count(self, freshness_days: int, owner_recheck_days: int) -> int:
        await self._configure_eligibility(freshness_days, owner_recheck_days)
        async with self.connection() as conn:
            return int(await conn.fetchval("SELECT count(*) FROM business_listings"))

    def save_status(self, payload: dict[str, Any], run_id: str | None = None) -> None:
        _run(self._save_status(payload, run_id))

    async def _save_status(self, payload: dict[str, Any], run_id: str | None = None) -> None:
        async with self.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    """INSERT INTO scrape_meta (key, value, updated_at)
                       VALUES ('scrape_status', $1::jsonb, now())
                       ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at""",
                    json.dumps(payload, ensure_ascii=False),
                )
                if run_id:
                    await conn.execute(
                        """UPDATE scrape_runs SET status=$2, completed_at=now(),
                           scraped_listings=$3, business_listings=$4, sellers_count=$5,
                           error_message=$6 WHERE run_id=$1::uuid""",
                        run_id, payload.get("status"), payload.get("scraped_listings", 0),
                        payload.get("business_listings", 0), payload.get("sellers_count", 0),
                        payload.get("reason"),
                    )

    async def fetch_business_rows(self, pool=None) -> list[dict]:
        if pool is not None:
            rows = await pool.fetch("SELECT * FROM business_listings")
            return [dict(row) for row in rows]
        async with self.connection() as conn:
            rows = await conn.fetch("SELECT * FROM business_listings")
        return [dict(row) for row in rows]


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    return str(value).lower() in {"true", "1", "t", "yes"}


def _db_listing_row(row) -> dict:
    result = dict(row)
    for key in ("is_verified_business", "is_agency", "has_broker_code_pattern", "is_active"):
        result[key] = "True" if result.get(key) else "False"
    for key in ("first_seen_date", "last_seen_date"):
        if result.get(key) is not None:
            result[key] = str(result[key])
    return result


def _db_seller_row(row) -> dict:
    result = dict(row)
    result["active_ads_count"] = (
        "" if result.get("active_ads_count") is None else str(result["active_ads_count"])
    )
    result["blocklist_permanent"] = "True" if result.get("blocklist_permanent") else "False"
    checked_at = result.get("checked_at")
    result["checked_at"] = checked_at.isoformat() if checked_at is not None else ""
    for key in ("seller_name", "profile_url", "active_ads_count_source", "classification"):
        if result.get(key) is None:
            result[key] = ""
    return result


def _db_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in {"days_since_updated", "seller_repeat_count"}:
        return _int_or_none(value) or 0
    if column in {"is_verified_business", "is_agency", "has_broker_code_pattern", "is_active"}:
        return _as_bool(value)
    return value
