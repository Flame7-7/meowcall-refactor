from __future__ import annotations

import discord
from utils import logger


class EmojiManager:
    def __init__(self):
        self._emojis: dict[str, discord.Emoji] = {}

    async def load(self, bot: discord.Client):
        logger.debug("Fetching emojis...")
        emojis = await bot.fetch_application_emojis()
        logger.debug(f"Fetched {len(emojis)} emojis.")
        self._emojis = {e.name: e for e in emojis}
        self.__dict__.update(self._emojis)
        logger.debug("All Emojis cached and loaded.")

    def get(self, name: str | None) -> discord.Emoji | None:
        if name:
            return self._emojis.get(name)

    def __getattr__(self, name: str):
        if name in self._emojis:
            return self._emojis[name]
        raise AttributeError(f"Emoji '{name}' not found.")
