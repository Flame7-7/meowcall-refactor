from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, cast

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy.exc import TimeoutError as PoolTimeout

from core.errors.customDiscord import UserBlacklisted
from services.guildService import GuildService
from services.userService import UserService
from utils import constants, logger, redis_client
from utils.discord.emojis import EmojiManager

# from utils.discord.helpers import get_prefix
from utils.discord.validators import is_blacklisted
from utils.redis.ratelimit import message_rate_limit

if TYPE_CHECKING:
    from db import Database


class Bot(commands.AutoShardedBot):
    user: discord.ClientUser  # pyright: ignore[reportIncompatibleMethodOverride]

    def __init__(self, presence: str) -> None:
        intent = discord.Intents.default()
        intent.message_content = True
        intent.members = True
        intent.guilds = True

        kwargs = dict(
            command_prefix=commands.when_mentioned_or('m.', 'M.'),
            intents=intent,
            chunk_guilds_at_startup=False,
            help_command=None,
            owner_ids=constants.developers,
            case_insensitive=True,
            strip_after_prefix=True,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, users=True, roles=False, replied_user=True
            ),
        )

        if constants.IS_CLUSTERED:
            kwargs["shard_count"] = constants.CLUSTER_SHARD_COUNT
            kwargs["shard_ids"] = constants.CLUSTER_SHARD_IDS
            self.cluster_id = constants.CLUSTER_ID

        super().__init__(**kwargs)

        self.presence_text = presence
        self.start_time = datetime.now()
        self.before_invoke(self._before_commands)
        self.after_invoke(self._after_commands)

        self.db: Database
        self.staff_ids: set[int] = set()
        self.moderator_ids: set[int] = set()
        self.admin_ids: set[int] = set()
        self.emotes = EmojiManager()
        self.http_session: aiohttp.ClientSession | None = None
        self.constants = constants

    async def get_context(
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[commands.Context[Bot]] = commands.Context,
    ) -> commands.Context:
        return cast(commands.Context, await super().get_context(origin, cls=cls))

    async def _before_commands(self, ctx: commands.Context[Bot]) -> None:
        await ctx.bot.wait_until_ready()

        if ctx.guild and not ctx.guild.chunked:
            await ctx.guild.chunk(cache=True)

        if await is_blacklisted(ctx.bot, ctx.author):
            raise UserBlacklisted()

        await message_rate_limit(ctx)

    async def _after_commands(self, ctx: commands.Context[Bot]) -> None:
        await self._persist_command_actor(ctx.author, ctx.guild)

    async def _persist_command_actor(
        self, user: discord.abc.User, guild: discord.Guild | None
    ) -> None:
        try:
            async with self.db.uow() as uow:
                user_service = UserService(uow.session)
                await user_service.upsert_user(user)

                if guild:
                    guild_service = GuildService(uow.session)
                    await guild_service.upsert_guild(guild)
        except PoolTimeout:
            logger.warning("DB pool exhausted while persisting command actor")
        except Exception as e:
            logger.error(f"Failed to persist command actor: {e}")

    async def on_app_command_completion(
        self,
        interaction: discord.Interaction[Bot],
        command: discord.app_commands.Command | discord.app_commands.Group | None,
    ) -> None:
        if interaction.user is None:
            return

        await self._persist_command_actor(interaction.user, interaction.guild)

    async def _sync_app_commands(self) -> None:
        already_synced = await redis_client.get("startup:commands_sync")

        if already_synced or getattr(self, "_commands_synced", False):
            logger.debug(
                "Skipping command sync (already synced by another cluster or this instance)"
            )
            return

        logger.info("First cluster — syncing application commands...")

        try:
            await redis_client.set("startup:commands_sync", "1")

            await asyncio.wait_for(self.tree.sync(), timeout=60)

            self._commands_synced = True
            logger.info("Application commands synced successfully")

        except TimeoutError:
            logger.warning(
                "Command sync timed out after 60 seconds. Continuing startup."
            )

        except discord.HTTPException as e:
            if e.status == 429:
                logger.warning(
                    "Rate limited while syncing commands. Will be out of sync until next restart."
                )
            else:
                logger.critical(
                    f"Unexpected error during command sync: {e}", exc_info=e
                )

    async def is_owner(self, user: discord.abc.User) -> bool:
        return user.id in constants.developers

    async def interaction_check(self, interaction: discord.Interaction[Bot]) -> bool:
        if await is_blacklisted(self, interaction.user):
            raise UserBlacklisted()
        return True

    async def sync_staff_ids(self) -> None:
        try:
            developer_guild = self.get_guild(1508007962931888128) or await self.fetch_guild(
                1508007962931888128
            )
            if not developer_guild:
                logger.warning(
                    "Developer guild not found. Staff commands may fail to work."
                )
                return

            staff_role = developer_guild.get_role(1508007962986414171)
            if not staff_role:
                logger.warning("Staff role not found in developer guild.")
                return

            self.staff_ids = {
                member.id
                async for member in developer_guild.fetch_members(limit=None)
                if staff_role in member.roles
            }

            logger.debug(f"Loaded {len(self.staff_ids)} staff IDs from developer guild.")
        except Exception as e:
            logger.warning(f'Failed to sync staff IDs, staff commands may fail. {e}')