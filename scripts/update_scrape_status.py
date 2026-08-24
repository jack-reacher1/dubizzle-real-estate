import os
import json
import asyncio
import asyncpg
import sys

async def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    statement_cache_size = int(os.getenv("ASYNCPG_STATEMENT_CACHE_SIZE", "0"))

    status_file = os.path.join(os.path.dirname(__file__), "..", "data", "scrape_status.json")
    status_file = os.path.normpath(status_file)

    if not os.path.exists(status_file):
        print(f"Status file not found: {status_file}", file=sys.stderr)
        sys.exit(1)

    with open(status_file, encoding="utf-8") as fh:
        data = json.load(fh)

    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=3,
        statement_cache_size=statement_cache_size,
    )
    async with pool.acquire() as conn:
        # Ensure the scrape_meta table exists (idempotent)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scrape_meta (
                key TEXT PRIMARY KEY,
                value JSONB,
                updated_at TIMESTAMPTZ DEFAULT now()
            )
            """
        )

        # Insert/Update the scrape status. Send the payload as a JSON string and
        # cast to jsonb to avoid driver/typing edge-cases.
        await conn.execute(
            """
            INSERT INTO scrape_meta (key, value, updated_at)
            VALUES ($1, $2::jsonb, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
            """,
            "scrape_status",
            json.dumps(data, ensure_ascii=False),
        )
    await pool.close()
    print("Scrape status uploaded to DB")

if __name__ == "__main__":
    asyncio.run(main())
