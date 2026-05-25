from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from core.cogs import CogBase
from discord.ext import commands
from ui.layouts.events.onGuildJoin import onGuildJoinLayout
from ui.layouts.events.welcome import WelcomeLayout
from utils import logger

if TYPE_CHECKING:
    from core.bot import Bot


class OnGuildJoin(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None) -> None:
        super().__init__(bot, emoji)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        logger.debug(f"Bot joined guild: {guild.name} ({guild.id})")
        try:
            dev_guild = await self.bot.fetch_guild(1508007962931888128)
            log_channel = await dev_guild.fetch_channel(1508007964949352496)
            await log_channel.send(view=onGuildJoinLayout(self.bot, guild))
        except Exception as e:
            logger.error(f"Failed to notify dev guild: {e}")

        target_channel = None

        if (
            guild.system_channel
            and guild.system_channel.permissions_for(guild.me).send_messages
        ):
            target_channel = guild.system_channel
            logger.debug(f"Selected system channel for welcome: {target_channel.name}")

        if not target_channel:
            channels = sorted(guild.text_channels, key=lambda c: c.position)
            for channel in channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    logger.debug(
                        f"Selected first available text channel for welcome: {target_channel.name}"
                    )
                    break

        if target_channel:
            try:
                view = WelcomeLayout(self.bot, guild, guild.owner)
                await target_channel.send(view=view)
                logger.info(
                    f"Sent welcome layout to {guild.name} ({guild.id}) in #{target_channel.name}"
                )
            except Exception as e:
                logger.error(f"Failed to send welcome layout to {guild.id}: {e}")
                try:
                    await target_channel.send("hi")
                except Exception as e2:
                    logger.error(f"Failed to send fallback hi to {guild.id}: {e2}")
        else:
            logger.warning(f"Could not find a speakable channel in guild {guild.id}")


async def setup(bot: Bot):
    await bot.add_cog(OnGuildJoin(bot, None))
