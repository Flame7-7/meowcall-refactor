import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from core.cogs import CogBase
from discord.ext import tasks
from models.base import Badges
from repositories.userRepository import UserRepository
from services.userService import UserService
from ui.layouts.tasks.voter import VoterLayout
from utils import logger, redis_client
from utils.redis.cache import CacheManager

if TYPE_CHECKING:
    from core.bot import Bot
    from sqlalchemy.ext.asyncio import AsyncSession

_VOTER_TTL = 8 * 60 * 60  # 8 hours in seconds


class TopggVoter(CogBase):
    def __init__(self, bot: Bot):
        super().__init__(bot, None)
        self.guild: discord.Guild | None = None
        self.role: discord.Role | None = None
        self._cache_manager = CacheManager()

    async def cog_load(self):
        self.topgg_voter.start()
        self.voter_cleanup.start()

    async def cog_unload(self):
        if self.topgg_voter.is_running():
            self.topgg_voter.cancel()
        if self.voter_cleanup.is_running():
            self.voter_cleanup.cancel()

    @staticmethod
    def _service(session: AsyncSession) -> UserService:
        return UserService(session)

    @tasks.loop(minutes=1)
    async def topgg_voter(self):
        cached_keys = await redis_client.keys("topgg:voters:*")
        cached_ids = {key.split(":")[-1] for key in cached_keys}

        async with self.bot.db.uow() as session:
            voters = await self._service(session).fetch_voters(exclude_ids=cached_ids)

        if not voters:
            return

        for voter in voters:
            try:
                member = await self.guild.fetch_member(voter.id)
                await member.send(view=VoterLayout(self.bot, member))
                await member.add_roles(self.role)
                await redis_client.set(
                    f"topgg:voters:{voter.id}", voter.id, _VOTER_TTL
                )
                # Also set the CacheManager voter state so the on_message
                # voter check (which uses the "voters" prefix) can find it.
                await self._cache_manager.set_voter_state(
                    voter.id, True, ttl=_VOTER_TTL
                )
                # Add VOTER badge to the user in DB so the DB fallback check
                # in on_message also works.
                async with self.bot.db.uow() as uow:
                    user_repo = UserRepository(uow.session)
                    user = await user_repo.get_by_id(voter.id)
                    if user and Badges.VOTER not in (user.badges or []):
                        user.badges = (user.badges or []) + [Badges.VOTER]
                        await uow.session.flush()
                await asyncio.sleep(1)
            except (discord.NotFound, discord.Forbidden):
                continue
            except Exception as e:
                logger.error(f"Error processing voter {voter.id}: {e}")
                continue

    @topgg_voter.before_loop
    async def before_topgg_voter(self):
        await self.bot.wait_until_ready()
        self.guild = await self.bot.fetch_guild(1508007962931888128)
        roles = await self.guild.fetch_roles()
        self.role = discord.utils.get(roles, id=1508007962969378929)

    @topgg_voter.after_loop
    async def after_topgg_voter(self):
        if self.topgg_voter.failed():
            self.topgg_voter.stop()

    # ══════════════════════════════════════════════════════════════════════
    # Voter cleanup — remove voter role + badge when 8-hour window expires
    # ══════════════════════════════════════════════════════════════════════

    @tasks.loop(minutes=5)
    async def voter_cleanup(self):
        """Remove the voter role from members whose 8-hour window has expired
        and clean up the VOTER badge from the database."""
        if self.guild is None or self.role is None:
            return

        cutoff = datetime.now(UTC) - timedelta(hours=8)

        # Remove expired VOTER badges from the database
        try:
            async with self.bot.db.uow() as uow:
                user_repo = UserRepository(uow.session)
                removed_count = await user_repo.remove_expired_voter_badges(cutoff)
                if removed_count:
                    logger.info(
                        f"Removed VOTER badge from {removed_count} expired voter(s)"
                    )
        except Exception as e:
            logger.error(f"Error removing expired voter badges: {e}")

        # Remove Discord role from members who no longer have the Redis key
        try:
            members_with_role = []
            async for member in self.guild.fetch_members(limit=None):
                if self.role in member.roles:
                    members_with_role.append(member)

            for member in members_with_role:
                has_key = await redis_client.exists(f"topgg:voters:{member.id}")
                if not has_key:
                    try:
                        await member.remove_roles(self.role)
                        logger.debug(
                            f"Removed voter role from {member.id} (expired)"
                        )
                        await asyncio.sleep(0.5)
                    except discord.HTTPException as e:
                        logger.warning(
                            f"Failed to remove voter role from {member.id}: {e}"
                        )
        except Exception as e:
            logger.error(f"Error during voter role cleanup: {e}")

    @voter_cleanup.before_loop
    async def before_voter_cleanup(self):
        await self.bot.wait_until_ready()
        # Wait for the main voter task to initialise guild/role
        await asyncio.sleep(10)


async def setup(bot: Bot):
    await bot.add_cog(TopggVoter(bot))
