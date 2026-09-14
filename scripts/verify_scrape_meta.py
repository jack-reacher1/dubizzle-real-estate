import os
import asyncio
import asyncpg

async def main():
    db = os.getenv('DATABASE_URL')
    if not db:
        print('DATABASE_URL not set')
        return
    # Some managed Postgres pools (e.g., pgbouncer in transaction mode) do not
    # support asyncpg prepared statement caching. Disable statement cache for
    # compatibility when verifying on Supabase/connection-poolers.
    conn = await asyncpg.connect(dsn=db, statement_cache_size=0)
    row = await conn.fetchrow("SELECT updated_at, value FROM scrape_meta WHERE key='scrape_status'")
    if not row:
        print('scrape_status row NOT FOUND')
    else:
        print('scrape_status row FOUND; updated_at=', row['updated_at'])
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
