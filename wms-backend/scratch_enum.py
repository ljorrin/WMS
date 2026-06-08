import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings

async def main():
    engine = create_async_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT pg_type.typname, enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname IN ('userstatus', 'adjustmentstatus');"))
        for row in res:
            print(f'{row[0]}: {row[1]}')
    await engine.dispose()

asyncio.run(main())
