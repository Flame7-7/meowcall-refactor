from __future__ import annotations

import asyncio
import time

import discord
from utils import logger

from .pool import BYPASS_WAIT_SECONDS, QueueEntry, UserphonePool

POLL_INTERVAL_SECONDS = 3
MAX_WAIT_SECONDS = 120


class UserphoneRelay:
    def __init__(
        self,
        bot,
        user: discord.User | discord.Member,
        guild: discord.Guild,
        channel: discord.TextChannel | discord.Thread,
        webhook: discord.Webhook,
        searching_message: discord.Message,
    ):
        self.bot = bot
        self.user = user
        self.guild = guild
        self.channel = channel
        self.webhook = webhook
        self.searching_message = searching_message
        self.pool = UserphonePool(
            user, guild, channel, webhook, str(searching_message.id)
        )

    async def search_pool_once(
        self,
    ) -> tuple[discord.Webhook | None, QueueEntry | None]:
        recent_matches = await self.pool.get_recent_matches()
        entries = await self.pool.get_all_entries()

        for entry in reversed(entries):
            if entry.user_id == str(self.user.id) and entry.guild_id == str(
                self.guild.id
            ):
                continue

            wait_time = time.time() - entry.queued_at
            is_recent_match = entry.guild_id in recent_matches

            if is_recent_match and wait_time < BYPASS_WAIT_SECONDS:
                continue

            if await self.pool.claim_entry(entry):
                try:
                    matched_webhook = discord.Webhook.from_url(
                        entry.webhook_url, session=self.bot.http._HTTPClient__session
                    )
                    await self.pool.record_match(entry.guild_id)
                    return matched_webhook, entry
                except Exception as e:
                    logger.warning(
                        f"Invalid webhook URL in queue: {entry.webhook_url} - {e}"
                    )
                    continue

        return None, None

    async def search_pool(
        self,
    ) -> tuple[discord.Webhook | None, QueueEntry | None, bool]:
        # Ensure we are in the queue
        await self.pool.remove_from_queue()
        await self.pool.add_to_queue()

        start_time = time.time()
        while (time.time() - start_time) < MAX_WAIT_SECONDS:
            match = await self.pool.check_match()
            if match:
                try:
                    matched_webhook = discord.Webhook.from_url(
                        match.webhook_url, session=self.bot.http._HTTPClient__session
                    )
                    await self.pool.remove_from_queue()
                    return matched_webhook, match, False
                except Exception:
                    logger.warning(f"Invalid webhook in match: {match.webhook_url}")

            matched_webhook, matched_entry = await self.search_pool_once()
            if matched_webhook and matched_entry:
                my_entry = self.pool._get_entry()
                await self.pool.set_match(matched_entry.guild_id, my_entry)

                await self.pool.remove_from_queue()
                return matched_webhook, matched_entry, False

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        await self.pool.remove_from_queue()
        return None, None, True

    async def edit_to_connected(self, matched_entry: QueueEntry) -> None:
        matched_guild = self.bot.get_guild(int(matched_entry.guild_id))

        try:
            await self.searching_message.edit(content="Searching for a match...")
        except Exception as e:
            logger.warning(f"Failed to edit own searching message: {e}")

        try:
            matched_channel = self.bot.get_channel(int(matched_entry.channel_id))
            if not matched_channel:
                matched_channel = await self.bot.fetch_channel(
                    int(matched_entry.channel_id)
                )

            matched_message = await matched_channel.fetch_message(
                int(matched_entry.message_id)
            )
            await matched_message.edit(
                content=f"Connected to **{matched_guild.name}** - Say hi!"
            )
        except Exception as e:
            logger.warning(f"Failed to edit matched user message: {e}")

    async def edit_to_timeout(self) -> None:
        embed = discord.Embed(
            title="Ended!",
            description="This call has been inactive for too long, it has been ended automatically.",
        )

        try:
            await self.searching_message.edit(embed=embed)
        except Exception as e:
            logger.warning(f"Failed to edit searching message to timeout: {e}")
