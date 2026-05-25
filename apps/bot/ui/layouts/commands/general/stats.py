from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import discord
import psutil
from discord import ui
from ui.layouts.commands.general.sharedButtons import SharedButtonsActionRow
from ui.layouts.uiBase import BaseActionRow, BaseLayoutView

if TYPE_CHECKING:
    from core.bot import Bot


def build_shard_embed(bot: Bot, current_shard_id: int | None = None) -> discord.Embed:
    embed = discord.Embed(title="Meowcall Shards", color=16765404)

    if bot.shards:
        for shard_id, shard in bot.shards.items():
            guild_count = sum(1 for guild in bot.guilds if guild.shard_id == shard_id)
            latency = round(shard.latency * 1000)

            if latency > 2500:
                status = "Provisioning"
            elif latency > 250:
                status = "Degraded"
            else:
                status = "Ready"

            embed.add_field(
                name=f"Shard #{shard_id}",
                value=f"> **Status:** {status}\n> **Latency:** {latency}ms\n> **Guilds:** {guild_count}",
                inline=True,
            )
            embed.set_footer(text=f"Current Shard: {current_shard_id}")
    else:
        embed.description = "No shard information is available."

    return embed


class ShardDisplayActionRow(BaseActionRow):
    def __init__(self, bot: Bot):
        super().__init__(bot, None)

        shard_button = ui.Button(
            emoji=getattr(bot.emotes, "gear_icon", None),
            label="Shards",
            style=discord.ButtonStyle.secondary,
        )
        shard_button.callback = self.shard_button_callback
        self.add_item(shard_button)

    async def shard_button_callback(
        self, interaction: discord.Interaction[Bot]
    ) -> None:
        current_shard = interaction.guild.shard_id if interaction.guild else 0
        embed = build_shard_embed(self.bot, current_shard)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class StatsLayout(BaseLayoutView):
    def __init__(self, bot: Bot):
        super().__init__(None, 300)

        process = psutil.Process()
        ram_usage = process.memory_info().rss / (1024**2)
        uptime = getattr(bot, "start_time", None)
        uptime_text = f"<t:{int(uptime.timestamp())}:R>" if uptime else "Unknown"
        version = getattr(getattr(bot, "constants", None), "version", "Unknown")

        self.add_item(
            ui.Container(
                ui.TextDisplay("### Meowcall Statistics"),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                SharedButtonsActionRow(bot, selected=type(self)),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(
                    f"**Bot**\n> **Uptime:** {uptime_text}\n> **Servers:** {len(bot.guilds)}\n> **Members:** {sum(guild.member_count or 0 for guild in bot.guilds)}"
                ),
                ui.TextDisplay(
                    f"**System**\n> **Operating System:** {sys.platform.title()}\n> **Python Version:** {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n> **RAM Usage:** {ram_usage:.0f}mb"
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ShardDisplayActionRow(bot),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay(f"-# Meowcall Version: {version}"),
                accent_color=16765404,
            )
        )
