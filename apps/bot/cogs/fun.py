from __future__ import annotations

import asyncio
import random
from collections import deque
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

from core.cogs import CogBase
from utils.runtime.constants import SHIP_GIFS, dares, truths

if TYPE_CHECKING:
    from core.bot import Bot
RECENT_LINES = deque(maxlen=30)


class Fun(CogBase):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None):
        super().__init__(bot, emoji)
        self.bot = bot

    @commands.hybrid_command(
        name="say",
        description="💬 - Output text from the bot.",
        aliases=["sa", "sayy", "echo", "output"],
    )
    @app_commands.describe(text="The desired text to be output")
    @commands.has_guild_permissions(manage_channels=True)
    async def fun_say(self, ctx: commands.Context[Bot], *, text: str):
        formatted_text = (
            f"{text}\n-# This content is not sent, or endorsed by Meowcall Officials."
        )

        view = View()
        view.add_item(
            Button(
                label=f"This message was sent by {ctx.author.name}",
                style=discord.ButtonStyle.grey,
                disabled=True,
            )
        )
        await ctx.send(content=formatted_text, view=view)

    @commands.hybrid_command(
        name="coinflip",
        description="🪙 - Flip a coin!",
        aliases=["cf", "coinf", "coinfli", "conflipp"],
    )
    async def fun_coinflip(self, ctx: commands.Context[Bot]):
        outcomes = ("The coin landed on **heads**!", "The coin landed on **tails**!")
        message = await ctx.send("Flipping...")
        await asyncio.sleep(1.5)
        await message.edit(content=random.choice(outcomes))

    @commands.hybrid_command(
        name="8ball", description="🎱 - Ask the ball!", aliases=["8b", "8bal", "8balll"]
    )
    @app_commands.describe(query="The question you want to ask the ball")
    async def fun_8ball(self, ctx: commands.Context[Bot], *, query: str):
        EIGHT_BALL_RESPONSES = [
            "It is certain.",
            "It is decidedly so.",
            "Without a doubt.",
            "Yes – definitely.",
            "You may rely on it.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Yes.",
            "Signs point to yes.",
            "Reply hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Don’t count on it.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful.",
        ]
        message = await ctx.send("🎱 Shaking the ball...")
        await asyncio.sleep(1.5)
        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            description=f"**Question:** {query}\n**Answer:** {random.choice(EIGHT_BALL_RESPONSES)}",
            color=discord.Color.purple(),
        )
        embed.set_thumbnail(url="https://i.ibb.co/5W3G6vN/8ball.png")
        embed.set_footer(text=f"Asked by {ctx.author.display_name}")
        await message.edit(content=None, embed=embed)

    # Ship command
    @commands.hybrid_command(
        name="ship",
        description="💖 - Calculate love compatibility between two users",
    )
    @app_commands.describe(
        user1="First user", user2="Second user (optional - defaults to you)"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ship(
        self,
        ctx: commands.Context,
        user1: discord.Member | discord.User | None = None,
        user2: discord.Member | discord.User | None = None,
        title: str = "💘 Love Compatibility Results",
    ):
        if user1 is None:
            user1 = ctx.author
        if user2 is None:
            members = [m for m in ctx.guild.members if m != user1 and not m.bot]
            if not members:
                await ctx.send("No other members to ship with!")
                return
            user2 = random.choice(members)

        if user1 == user2:
            await ctx.send("You can't ship a user with themselves!")
            return

        seed = (user1.id + user2.id) % 100
        random.seed(seed)
        percentage = random.randint(0, 100)
        random.seed()
        if percentage < 20:
            status = "❌ Not Compatible"
            gif_url = random.choice(SHIP_GIFS["low"])
            advice = "Maybe just stay friends?"
            color = discord.Color.red()
        elif percentage < 40:
            status = "🤔 Slight Potential"
            gif_url = random.choice(SHIP_GIFS["low"])
            advice = "Could work with effort!"
            color = discord.Color.orange()
        elif percentage < 60:
            status = "✨ Good Match"
            gif_url = random.choice(SHIP_GIFS["medium"])
            advice = "Potential for something more!"
            color = discord.Color.gold()
        elif percentage < 80:
            status = "💖 Great Match!"
            gif_url = random.choice(SHIP_GIFS["medium"])
            advice = "This could be special!"
            color = 0xFF69B4
        else:
            status = "💕 PERFECT MATCH! 💕"
            gif_url = random.choice(SHIP_GIFS["high"])
            advice = "A match made in heaven! ✨"
            color = 0xFF1493
        ship_name = f"{user1.display_name[:3]}{user2.display_name[-3:]}".upper()
        bar_length = 10
        filled = int((percentage / 100) * bar_length)
        progress_bar = "█" * filled + "░" * (bar_length - filled)

        embed = discord.Embed(title=title, color=color)
        embed.add_field(
            name="👫 Couple",
            value=f"**{user1.display_name}** 💕 **{user2.display_name}**",
            inline=False,
        )
        embed.add_field(
            name=f"💝 Compatibility: {percentage}%",
            value=f"```{progress_bar} {percentage}%```",
            inline=False,
        )
        embed.add_field(name="🎯 Result", value=f"**{status}**\n{advice}", inline=False)
        embed.add_field(name="🔤 Ship Name", value=f"**{ship_name}**", inline=True)
        embed.set_image(url=gif_url)
        embed.set_thumbnail(url="https://i.ibb.co/SsCFmH9/heart.png")
        embed.set_footer(
            text=f"Shipped by {ctx.author.display_name} • MeowCall 🐱",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
        )
        await ctx.send(embed=embed)

    # Kiss command
    @commands.hybrid_command(
        name="kiss", description="💋 - Send a kiss to another user"
    )
    @app_commands.describe(user="User to kiss")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def kiss(self, ctx: commands.Context, user: discord.Member | discord.User):
        if user == ctx.author:
            await ctx.send("⚠️ You can't kiss yourself, silly!", ephemeral=True)
            return
        ship_name = f"{ctx.author.display_name[:3]}{user.display_name[-3:]}".upper()
        gif_url = random.choice(SHIP_GIFS["high"])

        embed = discord.Embed(
            title=f"**__💋 {ctx.author.display_name} kisses {user.display_name}!__**",
            description=f"A romantic moment for **{ship_name}**! 😘",
            color=0xFF69B4,
        )
        embed.set_image(url=gif_url)
        embed.set_thumbnail(url="https://i.ibb.co/SsCFmH9/heart.png")
        embed.set_footer(text=f"Kissed by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # Hug command
    @commands.hybrid_command(name="hug", description="🤗 - Send a hug to another user")
    @app_commands.describe(user="User to hug")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def hug(self, ctx: commands.Context, user: discord.Member | discord.User):

        if user == ctx.author:
            await ctx.send("⚠️ You can't hug yourself, silly!", ephemeral=True)
            return
        ship_name = f"{ctx.author.display_name[:3]}{user.display_name[-3:]}".upper()
        gif_url = random.choice(SHIP_GIFS["medium"])

        embed = discord.Embed(
            title=f"**__🤗 {ctx.author.display_name} hugs {user.display_name}!__**",
            description=f"A warm moment for **{ship_name}**! 🥰",
            color=0xFF69B4,
        )
        embed.set_image(url=gif_url)
        embed.set_thumbnail(url="https://i.ibb.co/SsCFmH9/heart.png")
        embed.set_footer(text=f"Hugged by {ctx.author.display_name}")

        await ctx.send(embed=embed)

    # Pickup lines
    @commands.hybrid_command(
        name="pickup",
        aliases=["pu"],
        description="😏 - Get a random pickup line!",
    )
    @app_commands.describe(user="Send the pickup line to someone (optional)")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pickup(
        self, ctx: commands.Context, user: discord.Member | discord.User | None = None
    ):

        # Check for replied message in prefix mode
        if not ctx.interaction and ctx.message.reference and not user:
            try:
                replied_message = await ctx.channel.fetch_message(
                    ctx.message.reference.message_id
                )
                user = replied_message.author
                if user == ctx.author:
                    await ctx.send(
                        "⚠️ You can't send a pickup line to yourself!", ephemeral=True
                    )
                    return
                if user.bot:
                    await ctx.send(
                        "⚠️ You can't send a pickup line to a bot!", ephemeral=True
                    )
                    return
            except (discord.NotFound, discord.Forbidden):
                # If the referenced message was deleted or is inaccessible, continue
                # without a target user and fall back to the generic pickup flow.
                user = None

        # Get unique pickup line
        pickup_line = None
        for _ in range(3):
            async with self.bot.http_session.get(
                "https://rizzapi.vercel.app/random"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    line = data.get("text")
                    if line and line not in RECENT_LINES:
                        pickup_line = line
                        RECENT_LINES.append(line)
                        break

        if not pickup_line:
            pickup_line = random.choice(
                [
                    "Is your name Wi-Fi? Because I'm feeling a connection!",
                    "Do you have a map? I keep getting lost in your eyes.",
                ]
            )

        if user:
            message = (
                f'{ctx.author.mention} says: "Hey {user.mention}, {pickup_line}" 😏'
            )
        else:
            message = f'{ctx.author.mention} says: "{pickup_line}" 😏'

        await ctx.send(message)

    # Cat command
    @commands.hybrid_command(
        name="cat", description="🐱 - Get a random cat picture with a fun fact!"
    )
    @app_commands.describe(user="Gift this cat to someone (optional)")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def cat(
        self, ctx: commands.Context, user: discord.Member | discord.User | None = None
    ):

        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        async with self.bot.http_session.get(
            "https://api.thecatapi.com/v1/images/search"
        ) as img_response:
            if img_response.status != 200:
                await ctx.send(
                    "⚠️ Couldn't fetch a cat right now. Try again later!", ephemeral=True
                )
                return
            cat_data = await img_response.json()
            cat_url = cat_data[0]["url"]

        async with self.bot.http_session.get(
            "https://catfact.ninja/fact"
        ) as fact_response:
            cat_fact = (
                (await fact_response.json())["fact"]
                if fact_response.status == 200
                else "Cats sleep for an average of 12-16 hours a day! 😴"
            )

        embed = discord.Embed(
            title="🐱 Meow! Here's Your Cat!",
            description=f"**Fun Fact:** {cat_fact}",
            color=discord.Color.orange(),
        )
        embed.set_image(url=cat_url)
        embed.set_thumbnail(url="https://i.imgur.com/u9h6Lif.jpeg")

        if user:
            embed.set_footer(
                text=f"Gifted to {user.display_name} by {ctx.author.display_name}"
            )
            await ctx.send(
                content=f"{user.mention}, here's a cute cat for you! 🐾", embed=embed
            )
        else:
            await ctx.send(embed=embed)

    # Truth or Dare command
    @commands.hybrid_command(
        name="truthdare",
        aliases=["td"],
        description="😺 - Play Truth or Dare!",
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def truth_dare(self, ctx: commands.Context):

        choice = random.choice(["truth", "dare"])
        if choice == "truth":
            selected_item = random.choice(truths)
            title = "😺 Truth Time!"
            description = f"**Truth**: {selected_item}"
            color = discord.Color.blue()
        else:
            selected_item = random.choice(dares)
            title = "😺 Dare Challenge!"
            description = f"**Dare**: {selected_item}"
            color = discord.Color.red()

        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=f"Requested by {ctx.author.display_name} | Have fun! 🐾")
        embed.set_thumbnail(url="https://i.ibb.co/4tQJq7V/truth-or-dare.png")
        await ctx.send(embed=embed)

    # Meme command
    @commands.hybrid_command(
        name="meme", description="😂 - Get a random meme from a subreddit!"
    )
    @app_commands.describe(subreddit="Choose a subreddit (optional)")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def meme(self, ctx: commands.Context, subreddit: str | None = None):

        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        funny_subreddits = [
            "dankmemes",
            "memes",
            "wholesomememes",
            "PrequelMemes",
            "BoneHurtingJuice",
            "Animemes",
            "ProgrammerHumor",
        ]
        selected_subreddit = (
            subreddit.lower() if subreddit else random.choice(funny_subreddits)
        )

        if subreddit and selected_subreddit not in funny_subreddits:
            await ctx.send(
                f"⚠️ Invalid subreddit! Try one of: {', '.join(funny_subreddits)}",
                ephemeral=True,
            )
            return

        async with self.bot.http_session.get(
            f"https://meme-api.com/gimme/{selected_subreddit}"
        ) as response:
            if response.status != 200:
                await ctx.send(
                    "⚠️ Couldn't fetch a meme right now. Try again later!",
                    ephemeral=True,
                )
                return

            data = await response.json()
            meme_url = data.get("url")

            if not meme_url:
                await ctx.send("⚠️ No meme found. Try again!", ephemeral=True)
                return

            embed = discord.Embed(
                title=data.get("title", f"Random Meme from r/{selected_subreddit}"),
                description=f"From r/{data.get('subreddit', selected_subreddit)} 😂",
                color=discord.Color.orange(),
            )
            embed.set_image(url=meme_url)
            embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            await ctx.send(embed=embed)


async def setup(bot: Bot):
    await bot.add_cog(Fun(bot, "🎊"))