from discord.ext import commands
from jishaku.cog import async_setup


async def setup(bot: commands.Bot):
    await async_setup(bot)
