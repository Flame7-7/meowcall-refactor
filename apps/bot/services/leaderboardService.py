from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import discord
from repositories.userRepository import UserRepository

if TYPE_CHECKING:
    from core.bot import Bot
    from sqlalchemy.ext.asyncio import AsyncSession


class LeaderboardService:
    def __init__(self, session: AsyncSession, bot: Bot):
        self._session = session
        self._bot = bot
        self._user_repo = UserRepository(session)

    async def get_user_leaderboard_embed(
        self, type: Literal["calls", "messages"], limit: int = 10
    ) -> discord.Embed:
        if type == "calls":
            top_users = await self._user_repo.get_top_by_call_count(limit)
            title = "📞 Top Callers"
            field_name = "Calls"
            attr = "callCount"
        else:
            top_users = await self._user_repo.get_top_by_message_count(limit)
            title = "💬 Top Messengers"
            field_name = "Messages"
            attr = "messageCount"

        embed = discord.Embed(
            title=f"🏆 {title} Leaderboard",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )

        description = ""
        for i, user_record in enumerate(top_users, 1):
            count = getattr(user_record, attr) or 0
            # Try to get user from cache to get current name, fallback to DB name
            user_id_int = None
            try:
                user_id_int = int(user_record.id)
            except (ValueError, TypeError):
                # Invalid/non-numeric IDs are ignored here; we fall back to the DB-stored name below.
                user_id_int = None

            user = self._bot.get_user(user_id_int) if user_id_int else None
            name = (
                user.display_name
                if user
                else (user_record.name or f"User {user_record.id}")
            )

            medal = ""
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "

            description += f"{medal}**#{i}** {name} — `{count}` {field_name}\n"

        if not description:
            description = "No data available yet! 😺"

        embed.description = description
        embed.set_footer(text="MeowCall Global Leaderboard")

        return embed
