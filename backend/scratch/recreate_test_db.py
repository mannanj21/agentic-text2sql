import asyncio
import psycopg

async def recreate_db():
    conn = await psycopg.AsyncConnection.connect(
        "postgresql://test_user:test_password@localhost:5433/postgres", 
        autocommit=True
    )
    await conn.execute("DROP DATABASE IF EXISTS test_db WITH (FORCE)")
    await conn.execute("CREATE DATABASE test_db")
    await conn.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(recreate_db())
