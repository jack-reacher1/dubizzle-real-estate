"""Import the legacy CSV snapshots into the PostgreSQL source of truth."""

import asyncio
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import asyncpg


ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("DATA_DIR", ROOT / "data"))


def rows(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def integer(value):
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def boolean(value):
    return str(value).lower() in {"true", "1", "yes", "t"}


def timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


async def main():
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    conn = await asyncpg.connect(
        os.environ["DATABASE_URL"],
        statement_cache_size=int(os.getenv("ASYNCPG_STATEMENT_CACHE_SIZE", "0")),
        timeout=float(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10")),
        command_timeout=float(os.getenv("DB_COMMAND_TIMEOUT_SECONDS", "120")),
    )
    try:
        await conn.execute((ROOT / "scripts" / "002_create_postgres_schema.sql").read_text(encoding="utf-8"))
        async with conn.transaction():
            seller_rows = rows(DATA / "sellers_cache.csv")
            seller_records = [
                (
                    seller.get("seller_id"), seller.get("seller_name") or None,
                    seller.get("profile_url") or None, integer(seller.get("active_ads_count")),
                    seller.get("active_ads_count_source") or None, seller.get("classification") or None,
                    timestamp(seller.get("checked_at")), boolean(seller.get("blocklist_permanent")),
                )
                for seller in seller_rows
                if seller.get("seller_id")
            ]
            await conn.execute("""
                CREATE TEMP TABLE sellers_import AS
                SELECT seller_id, seller_name, profile_url, active_ads_count,
                       active_ads_count_source, classification, checked_at,
                       blocklist_permanent
                FROM sellers WHERE false
            """)
            if seller_records:
                await conn.copy_records_to_table(
                    "sellers_import",
                    records=seller_records,
                    columns=[
                        "seller_id", "seller_name", "profile_url", "active_ads_count",
                        "active_ads_count_source", "classification", "checked_at",
                        "blocklist_permanent",
                    ],
                )
            await conn.execute("""
                INSERT INTO sellers
                    (seller_id, seller_name, profile_url, active_ads_count,
                     active_ads_count_source, classification, checked_at, blocklist_permanent)
                SELECT seller_id, seller_name, profile_url, active_ads_count,
                       active_ads_count_source, classification, checked_at,
                       blocklist_permanent
                FROM sellers_import
                ON CONFLICT (seller_id) DO UPDATE SET
                    seller_name=EXCLUDED.seller_name,
                    profile_url=EXCLUDED.profile_url,
                    active_ads_count=EXCLUDED.active_ads_count,
                    active_ads_count_source=EXCLUDED.active_ads_count_source,
                    classification=EXCLUDED.classification,
                    checked_at=EXCLUDED.checked_at,
                    blocklist_permanent=EXCLUDED.blocklist_permanent,
                    updated_at=now()
            """)

            fields = [
                "ad_id", "ad_url", "listing_type", "property_type", "title", "price", "area_sqm",
                "bedrooms", "bathrooms", "completion_status", "payment_method", "ownership", "furnished",
                "location_text", "compound", "location_link", "amenities", "description_full",
                "phone_in_description", "posted_at", "updated_at", "scraped_at", "days_since_updated",
                "is_verified_business", "is_agency", "agency_name", "has_broker_code_pattern",
                "seller_repeat_count", "seller_id", "seller_name", "first_seen_date", "last_seen_date", "is_active",
                "lead_status",
            ]
            placeholders = ", ".join(f"${i}" for i in range(1, len(fields) + 1))
            updates = ", ".join(
                f"{field}=EXCLUDED.{field}"
                for field in fields[1:]
                if field not in {"first_seen_date", "lead_status"}
            )
            listing_records = []
            today = datetime.now(timezone.utc).date().isoformat()
            for listing in rows(DATA / "listings.csv"):
                values = [listing.get(field) or None for field in fields]
                values[22] = integer(values[22])
                for index in (23, 24, 26, 32):
                    values[index] = boolean(values[index])
                values[27] = integer(values[27]) or 0
                values[30] = values[30] or today
                values[31] = values[31] or values[30]
                values[33] = listing.get("lead_status") or "new"
                if values[0]:
                    listing_records.append(tuple(values))

            await conn.execute(f"""
                CREATE TEMP TABLE listings_import AS
                SELECT {', '.join(fields)} FROM listings WHERE false
            """)
            if listing_records:
                await conn.copy_records_to_table(
                    "listings_import",
                    records=listing_records,
                    columns=fields,
                )
            await conn.execute(f"""
                INSERT INTO listings ({', '.join(fields)})
                SELECT {', '.join(fields)} FROM listings_import
                ON CONFLICT (ad_id) DO UPDATE SET {updates}
            """)
    finally:
        await conn.close()
    print("CSV migration completed")


if __name__ == "__main__":
    asyncio.run(main())