from __future__ import annotations

from discord.ext import commands


class InteractionCheck(commands.CommandError):
    def __init__(self, message: str | None = None) -> None:
        self.message = message or "You may not interact with this."
        super().__init__(self.message)


class InvalidInput(commands.CommandError):
    def __init__(self, message: str | None = None) -> None:
        self.message = (
            message or "I could not use that argument. Have you input the correct type?"
        )
        super().__init__(self.message)


class RateLimited(commands.CommandError):
    def __init__(self, message: str | None = None) -> None:
        self.message = message or "Woah! Slow down, you are using commands too fast."
        super().__init__(self.message)


class UserBlacklisted(commands.CheckFailure):
    def __init__(self, message: str | None = None) -> None:
        self.message = (
            message
            or "You are blacklisted from using this bot, you may attempt an appeal within our support server below."
        )
        super().__init__(self.message)
