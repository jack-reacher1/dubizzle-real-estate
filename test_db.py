import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def main():
    conn = await asyncpg.connect(
        os.environ["DATABASE_URL"],
        statement_cache_size=int(os.getenv("ASYNCPG_STATEMENT_CACHE_SIZE", "0")),
    )
    print("DB connection: OK")
    await conn.close()

asyncio.run(main())
