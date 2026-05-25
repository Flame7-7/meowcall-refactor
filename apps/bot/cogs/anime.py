from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

import discord
from core.cogs import CogBase
from discord.ext import commands
from services.animeService import AnimeService
from utils.runtime.constants import POPULAR_ANIME_IDS

if TYPE_CHECKING:
    from core.bot import Bot

# Lock to prevent concurrent trivia requests
trivia_lock = asyncio.Lock()


class Anime(CogBase):
    """Cog for anime-related commands including trivia and recommendations."""

    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None) -> None:
        super().__init__(bot, emoji)
        self.bot = bot
        self.anime_service = AnimeService(bot)

    @commands.hybrid_command(
        name="trivia",
        aliases=["t"],
        description="🎲 - Answer an anime trivia question!",
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def trivia(self, ctx: commands.Context[Bot]) -> None:
        """Answer an anime trivia question."""

        async with trivia_lock:
            trivia_data = await AnimeService.fetch_trivia_question(
                self.bot.http_session
            )

            if not trivia_data:
                await ctx.send(
                    "⚠️ Couldn't fetch trivia. Try again later!", ephemeral=True
                )
                return

            question = trivia_data["question"]
            correct = trivia_data["correct"]
            options = trivia_data["options"]

            embed = discord.Embed(
                title="🎲 Anime Trivia",
                description=(
                    f"**Question**: {question}\n\n**Options**:\n"
                    + "\n".join(f"{i + 1}. {ans}" for i, ans in enumerate(options))
                ),
                color=discord.Color.blue(),
            )
            embed.set_footer(text="Reply with the number (1-4) of your answer!")
            await ctx.send(embed=embed)

            def check(m: discord.Message) -> bool:
                return (
                    m.author == ctx.author
                    and m.channel == ctx.channel
                    and m.content in ["1", "2", "3", "4"]
                )

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30.0)
                if options[int(msg.content) - 1] == correct:
                    await ctx.send(f"✅ Correct! The answer is **{correct}**.")
                else:
                    await ctx.send(f"❌ Wrong! The correct answer was **{correct}**.")
            except TimeoutError:
                await ctx.send(f"⏳ Time's up! The correct answer was **{correct}**.")

    @commands.hybrid_command(
        name="animerec",
        aliases=["ar"],
        description="📺 - Get a random anime recommendation!",
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def anime_recommendation(self, ctx: commands.Context[Bot]) -> None:
        """Get a random anime recommendation."""

        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        anime_id = random.choice(POPULAR_ANIME_IDS)
        anime_data = await self.anime_service.fetch_anime_recommendation(anime_id)

        if not anime_data:
            await ctx.send(
                "⚠️ Couldn't fetch an anime. Try again later!", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📺 Anime Recommendation: {anime_data['title']}",
            description=f"**Genres**: {anime_data['genres']}\n**Synopsis**: {anime_data['synopsis']}",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=anime_data['image'])
        embed.add_field(
            name="Link", value=f"[MyAnimeList]({anime_data['url']})", inline=False
        )
        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Anime(bot, "📺"))
