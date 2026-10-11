import asyncio
from backend.db.connection import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as session:
        # Check for April Dunford
        res = await session.execute(text("""
            SELECT DISTINCT guest_name, episode_title
            FROM transcript_chunks
            WHERE guest_name ILIKE '%april%' OR content ILIKE '%dunford%'
        """))
        april_rows = res.fetchall()
        print(f"April matches ({len(april_rows)}):", april_rows)

        # Check total chunks and unique guests
        res_guests = await session.execute(text("""
            SELECT guest_name, count(*) 
            FROM transcript_chunks 
            GROUP BY guest_name 
            ORDER BY count(*) DESC 
            LIMIT 30;
        """))
        print("\nTop guests in DB:")
        for r in res_guests.fetchall():
            print(f"- {r[0]}: {r[1]} chunks")

if __name__ == "__main__":
    asyncio.run(main())
