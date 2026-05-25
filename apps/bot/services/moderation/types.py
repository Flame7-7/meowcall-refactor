from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import discord


class ActionType(Enum):
    WARN = "warn"
    BAN = "ban"
    UNBAN = "unban"
    DELETE = "delete"
    BLACKLIST = "blacklist"


@dataclass
class ModerationTarget:
    user: discord.User | discord.Member | None = None
    guild: discord.Guild | None = None

    @property
    def is_user(self) -> bool:
        return self.user is not None

    @property
    def is_guild(self) -> bool:
        return self.guild is not None

    @property
    def target_id(self) -> str:
        if self.user:
            return str(self.user.id)
        elif self.guild:
            return str(self.guild.id)
        return ""

    @property
    def target_name(self) -> str:
        if self.user:
            return str(self.user)
        elif self.guild:
            return str(self.guild)
        return ""

    def validate(self) -> tuple[bool, str | None]:
        if self.user and self.guild:
            return False, "You may not select both a user, and guild."
        if not self.user and not self.guild:
            return False, "You must select either a user, or a guild."
        return True, None
