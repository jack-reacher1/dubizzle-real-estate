import asyncio
import os
import asyncpg

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    print("DB connection: OK")
    await conn.close()

asyncio.run(main())
