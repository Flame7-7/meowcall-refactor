from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from core.bot import Bot


class CogBase(commands.Cog):
    def __init__(self, bot: Bot, emoji: discord.Emoji | None = None) -> None:
        self.bot = bot
        self.constants = bot.constants
        self.emoji = emoji
        self._init_context_menus()

    def _init_context_menus(self) -> None:
        self._context_menus: list[discord.app_commands.ContextMenu] = []

        for attribute_name in dir(self):
            maybe_func = getattr(self, attribute_name)
            if callable(maybe_func) and hasattr(maybe_func, "__context_menu__"):
                name, type_ = maybe_func.__context_menu__
                menu = discord.app_commands.ContextMenu(
                    name=name,
                    callback=maybe_func,  # pyright: ignore[reportArgumentType]
                    type=type_,
                )
                self.bot.tree.add_command(menu)
                self._context_menus.append(menu)

    async def cog_unload(self) -> None:
        for menu in getattr(self, "_context_menus", []):
            self.bot.tree.remove_command(menu.name, type=menu.type)


def ContextMenuCommand(
    name: str,
    type_: discord.AppCommandType = discord.AppCommandType.message,
):
    def decorator(func: Callable[..., Awaitable[Any]]):
        func.__context_menu__ = (name, type_)  # pyright: ignore[reportFunctionMemberAccess]
        return func

    return decorator
