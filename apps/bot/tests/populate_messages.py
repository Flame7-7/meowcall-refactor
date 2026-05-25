import asyncio
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from faker import Faker

from db.database import init_database
from models import Message, MessageReaction
from models.base import MessageStatus

# Load env
load_dotenv(Path(__file__).parent / ".env")

fake = Faker()


def random_snowflake() -> str:
    return str(random.randint(100000000000000000, 999999999999999999))


EMOJIS = ["👍", "👎", "❤️", "🔥", "💀", "😭", "😂", "🤝", "🎉", "😎"]


async def populate_messages(
    amount: int = 100_000,
    batch_size: int = 5_000,
) -> None:
    db = init_database(os.getenv("DATABASE_URL"))

    async with db.async_session() as session:
        created_message_ids: list[str] = []

        for batch_start in range(0, amount, batch_size):
            messages: list[Message] = []
            reactions: list[MessageReaction] = []

            for _ in range(batch_size):
                message_id = random_snowflake()

                referred_message_id = None

                # ~15% replies
                if created_message_ids and random.random() < 0.15:
                    referred_message_id = random.choice(created_message_ids)

                created_at = datetime.now(timezone.utc) - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )

                msg = Message(
                    id=message_id,
                    content=fake.text(max_nb_chars=300),
                    guildId=random_snowflake(),
                    channelId=random_snowflake(),
                    authorId=random_snowflake(),
                    status=random.choice(list(MessageStatus)),
                    retentionUntil=None,
                    imagesUrl=(
                        [fake.image_url(), fake.image_url()]
                        if random.random() < 0.10
                        else None
                    ),
                )

                msg.referredMessageId = referred_message_id
                msg.createdAt = created_at
                msg.updatedAt = created_at

                messages.append(msg)
                created_message_ids.append(message_id)

                # ~25% reactions
                if random.random() < 0.25:
                    used_emojis = random.sample(EMOJIS, random.randint(1, 3))

                    for emoji in used_emojis:
                        reaction = MessageReaction(
                            messageId=message_id,
                            emoji=emoji,
                            users=[
                                random_snowflake() for _ in range(random.randint(1, 15))
                            ],
                        )

                        reactions.append(reaction)

            session.add_all(messages)
            session.add_all(reactions)

            await session.commit()

            print(
                f"Inserted "
                f"{min(batch_start + batch_size, amount):,}"
                f"/{amount:,} messages"
            )

    print("Done populating messages")


if __name__ == "__main__":
    asyncio.run(populate_messages())
