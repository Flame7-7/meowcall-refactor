import asyncio
from datetime import datetime, timedelta, timezone

from db.database import async_session_maker
from models import Message, Report
from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased


async def test():
    async with async_session_maker() as session:
        before24h = datetime.now(timezone.utc) - timedelta(days=1)

        # Total messages > 24h
        total = await session.scalar(
            select(func.count(Message.id)).where(Message.createdAt < before24h)
        )
        print(f"Total old messages: {total}")

        MessageAlias = aliased(Message)

        # Protected by referred
        ref_count = await session.scalar(
            select(func.count(Message.id)).where(
                and_(
                    Message.createdAt < before24h,
                    Message.id.in_(
                        select(MessageAlias.referredMessageId).where(
                            MessageAlias.referredMessageId.is_not(None)
                        )
                    ),
                )
            )
        )
        print(f"Protected by references: {ref_count}")

        # Unprotected
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
