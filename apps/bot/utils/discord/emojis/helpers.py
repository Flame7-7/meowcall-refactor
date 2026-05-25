from __future__ import annotations

import discord
from utils.patterns import Patterns


def parse_discord_emoji(emoji_input: discord.Emoji | str | None) -> str:
    if not emoji_input:
        return "❓"

    def as_img(eid, name, animated):
        return f'<img src="https://cdn.discordapp.com/emojis/{eid}.{"gif" if animated else "png"}" alt="{name}" class="custom-emoji">'

    if isinstance(emoji_input, discord.Emoji):
        return as_img(
            emoji_input.id, emoji_input.name, getattr(emoji_input, "animated", False)
        )

    match = Patterns.DISCORD_EMOJI.match(str(emoji_input))
    if match:
        animated, name, _emoji_id = match.groups()
        return as_img(emoji_input, name, bool(animated))

    return "❓"
