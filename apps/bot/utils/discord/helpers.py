from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from services.guildService import GuildService
from utils import constants, logger
from utils.redis.cache import CacheManager

if TYPE_CHECKING:
    from core.bot import Bot


def filter_user_mentions(user_id: int | None) -> discord.AllowedMentions:
    allowed_mentions = discord.AllowedMentions.none()

    if user_id:
        allowed_mentions.users = [discord.Object(id=user_id)]

    return allowed_mentions


def build_discord_jump_link(guild_id: str, channel_id: str, message_id: str) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


async def get_prefix(bot: Bot, message: discord.Message) -> list[str]:
    prefix = constants.PREFIX

    if message.guild:
        cache_manager: CacheManager = CacheManager()
        guild_id = str(message.guild.id)
        cached = await cache_manager.get("guild_prefix", guild_id)

        if cached:
            prefix = cached
        else:
            try:
                async with bot.db.uow() as uow:
                    guild_service = GuildService(uow.session)
                    guild = await guild_service.get_guild_by_id(message.guild.id)
                    prefix = (
                        guild.customPrefix
                        if guild and guild.customPrefix
                        else constants.PREFIX
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to resolve guild prefix for %s, falling back to default: %s",
                    guild_id,
                    exc,
                )
                prefix = constants.PREFIX

            await cache_manager.set(
                "guild_prefix", guild_id, value=prefix, ttl=CacheManager.LONG_TTL
            )

    # Case-insensitive prefix matching
    content_lower = message.content.lower()
    prefix_lower = prefix.lower()

    if content_lower.startswith(prefix_lower):
        matched_prefix = message.content[: len(prefix_lower)]
        return commands.when_mentioned_or(matched_prefix)(bot, message)

    return commands.when_mentioned_or(prefix)(bot, message)
