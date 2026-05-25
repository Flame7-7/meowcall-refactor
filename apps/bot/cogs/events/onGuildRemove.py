from typing import TYPE_CHECKING

import discord
from core.cogs import CogBase
from discord.ext import commands
from ui.layouts.events.onGuildRemove import onGuildRemoveLayout

if TYPE_CHECKING:
    from core.bot import Bot


class OnGuildRemove(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None) -> None:
        super().__init__(bot, emoji)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        try:
            dev_guild = await self.bot.fetch_guild(1508007962931888128)
            channel = await dev_guild.fetch_channel(1508007964949352496)
            await channel.send(view=onGuildRemoveLayout(self.bot, guild))
        except Exception:
            pass


async def setup(bot: Bot):
    await bot.add_cog(OnGuildRemove(bot, None))
