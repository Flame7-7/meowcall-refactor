from typing import TYPE_CHECKING

import discord
from core.cogs import CogBase
from core.errors.errorHandler import error_handler
from discord.ext import commands

if TYPE_CHECKING:
    from core.bot import Bot


class OnCommandError(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None):
        super().__init__(bot, emoji)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        await error_handler(ctx, error)


async def setup(bot: Bot):
    await bot.add_cog(OnCommandError(bot))
