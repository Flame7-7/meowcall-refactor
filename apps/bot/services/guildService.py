from typing import TYPE_CHECKING

import discord
from repositories.guildRepository import GuildRepository
from services.baseService import BaseService

if TYPE_CHECKING:
    from models import ServerData


class GuildService(BaseService):
    """Service for managing server/guild data."""

    def _server_repo(self) -> GuildRepository:
        return GuildRepository(self.session)

    async def upsert_server(self, guild: discord.Guild) -> None:
        """Upsert a guild into the ServerData table. Commits after."""
        await self._server_repo().upsert(
            str(guild.id),
            name=guild.name,
            icon_url=guild.icon.url if guild.icon else None,
        )

    async def upsert_guild(self, guild: discord.Guild) -> None:
        """Backward-compatible alias for older call sites."""
        await self.upsert_server(guild)

    async def get_server(self, guild_id: str | int) -> ServerData | None:
        """Get a server by ID."""
        return await self._server_repo().get_by_id(guild_id)

    async def get_guild_by_id(self, guild_id: str | int) -> ServerData | None:
        """Backward-compatible alias for older call sites."""
        return await self.get_server(guild_id)

    async def upsert_server_raw(
        self, guild_id: str | int, name: str, icon_url: str | None = None
    ) -> None:
        """Upsert by raw ID/name. Commits after."""
        await self._server_repo().upsert(guild_id, name=name, icon_url=icon_url)
