import asyncio
from datetime import datetime, timedelta, timezone

from db import create_db_engine
from models import Message, Report
from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased


async def test():
    engine = create_db_engine()
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        before24h = datetime.now(timezone.utc) - timedelta(days=1)

        # Total messages > 24h
        total = await session.scalar(
            select(func.count(Message.id)).where(Message.createdAt < before24h)
        )
        print(f"Total old messages: {total}")

        MessageAlias = aliased(Message)

        stmt = select(func.count(Message.id)).where(
            and_(
                Message.createdAt < before24h,
                ~Message.id.in_(
                    select(MessageAlias.referredMessageId).where(
                        MessageAlias.referredMessageId.is_not(None)
                    )
                ),
                ~Message.id.in_(
                    select(Report.messageId).where(Report.messageId.is_not(None))
                ),
            )
        )
        unprotected = await session.scalar(stmt)
        print(f"Unprotected old messages: {unprotected}")


asyncio.run(test())
