from __future__ import annotations

import json
import time
from dataclasses import dataclass

import discord
from utils import logger, redis_client

QUEUE_KEY = "userphone_queue"
MATCH_HISTORY_KEY = "userphone_match_history"
MATCH_HISTORY_TTL = 3600
BYPASS_WAIT_SECONDS = 30


@dataclass
class QueueEntry:
    user_id: str
    guild_id: str
    channel_id: str
    webhook_url: str
    message_id: str
    queued_at: float

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_id": self.user_id,
                "guild_id": self.guild_id,
                "channel_id": self.channel_id,
                "webhook_url": self.webhook_url,
                "message_id": self.message_id,
                "queued_at": self.queued_at,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> QueueEntry | None:
        try:
            parsed = json.loads(data)
            return cls(
                user_id=parsed["user_id"],
                guild_id=parsed["guild_id"],
                channel_id=parsed["channel_id"],
                webhook_url=parsed["webhook_url"],
                message_id=parsed["message_id"],
                queued_at=parsed["queued_at"],
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None


class UserphonePool:
    def __init__(
        self,
        user: discord.User | discord.Member,
        guild: discord.Guild,
        channel: discord.TextChannel | discord.Thread,
        webhook: discord.Webhook,
        message_id: str,
    ):
        self.user = user
        self.guild = guild
        self.channel = channel
        self.webhook = webhook
        self.message_id = message_id

    def _get_entry(self) -> QueueEntry:
        return QueueEntry(
            user_id=str(self.user.id),
            guild_id=str(self.guild.id),
            channel_id=str(self.channel.id),
            webhook_url=str(self.webhook.url),
            message_id=self.message_id,
            queued_at=time.time(),
        )

    async def add_to_queue(self) -> None:
        entry = self._get_entry()
        await redis_client.lpush(QUEUE_KEY, entry.to_json())  # type: ignore[misc]
        logger.debug(f"Added user {self.user.id} to queue")

    async def get_all_entries(self) -> list[QueueEntry]:
        entries = []
        data_list = await redis_client.lrange(QUEUE_KEY, 0, -1)  # type: ignore[misc]
        for data in data_list:
            entry = QueueEntry.from_json(data)
            if entry:
                entries.append(entry)
        return entries

    async def claim_entry(self, entry: QueueEntry) -> bool:
        # Atomically remove 1 occurrence of this entry
        count = await redis_client.lrem(QUEUE_KEY, 1, entry.to_json())  # type: ignore[misc]
        return count > 0

    async def remove_from_queue(self) -> None:
        all_entries = await redis_client.lrange(QUEUE_KEY, 0, -1)  # type: ignore[misc]
        for entry_data in all_entries:
            entry = QueueEntry.from_json(entry_data)
            if entry is None:
                await redis_client.lrem(QUEUE_KEY, 0, entry_data)  # type: ignore[misc]
                continue
            if entry.user_id == str(self.user.id) and entry.guild_id == str(
                self.guild.id
            ):
                await redis_client.lrem(QUEUE_KEY, 0, entry_data)  # type: ignore[misc]
                logger.debug(
                    f"Removed user {self.user.id} from guild {self.guild.id} queue"
                )

    async def get_recent_matches(self) -> set[str]:
        key = f"{MATCH_HISTORY_KEY}:{self.guild.id}"
        matches = await redis_client.smembers(key)  # type: ignore[misc]
        return set(matches) if matches else set()

    async def record_match(self, other_guild_id: str) -> None:
        my_key = f"userphone:activity:{self.guild.id}"
        their_key = f"userphone:activity:{other_guild_id}"
        await redis_client.sadd(my_key, other_guild_id)  # type: ignore[misc]
        await redis_client.sadd(their_key, str(self.guild.id))  # type: ignore[misc]
        await redis_client.expire(my_key, MATCH_HISTORY_TTL)  # type: ignore[misc]
        await redis_client.expire(their_key, MATCH_HISTORY_TTL)  # type: ignore[misc]
        logger.debug(
            f"Recorded match between guild {self.guild.id} and guild {other_guild_id}"
        )

    async def drop_queue(self) -> None:
        await redis_client.delete(QUEUE_KEY)
        logger.debug("Dropped queue")

    async def check_match(self) -> QueueEntry | None:
        key = f"userphone:match:{self.guild.id}"
        data = await redis_client.get(key)
        if data:
            await redis_client.delete(key)
            return QueueEntry.from_json(data)
        return None

    async def set_match(self, target_guild_id: str, entry: QueueEntry) -> None:
        key = f"userphone:match:{target_guild_id}"
        await redis_client.set(key, entry.to_json(), ex=60)
