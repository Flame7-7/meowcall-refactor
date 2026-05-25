import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select, func, and_
from sqlalchemy.orm import aliased

from db.database import init_database
from models import Message, Report

# Load .env from current file directory
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

# Debug
print(f"env path: {ENV_PATH}")
print(f"env exists: {ENV_PATH.exists()}")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")


async def test():
    db = init_database(os.getenv("DATABASE_URL"))

    async with db.async_session() as session:
        before24h = datetime.now(timezone.utc) - timedelta(days=1)

        # Total old messages
        total = await session.scalar(
            select(func.count(Message.id)).where(Message.createdAt < before24h)
        )

        print(f"Total old messages > 24h: {total}")

        MessageAlias = aliased(Message)

        # Messages safe to delete
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

        # Individual checks
        subq1 = select(MessageAlias.referredMessageId).where(
            MessageAlias.referredMessageId.is_not(None)
        )

        subq2 = select(Report.messageId).where(Report.messageId.is_not(None))

        c1 = await session.scalar(
            select(func.count(Message.id)).where(
                Message.createdAt < before24h, ~Message.id.in_(subq1)
            )
        )

        c2 = await session.scalar(
            select(func.count(Message.id)).where(
                Message.createdAt < before24h, ~Message.id.in_(subq2)
            )
        )

        print(f"Unprotected from references: {c1}")
        print(f"Unprotected from reports: {c2}")


if __name__ == "__main__":
    asyncio.run(test())
