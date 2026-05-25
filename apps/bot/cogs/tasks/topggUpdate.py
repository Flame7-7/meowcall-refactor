import asyncio
from typing import TYPE_CHECKING

import aiohttp
from core.cogs import CogBase
from discord.ext import tasks
from utils import logger

if TYPE_CHECKING:
    from core.bot import Bot


class TopggUpdate(CogBase):
    def __init__(self, bot: "Bot"):
        super().__init__(bot, None)

    async def cog_load(self):
        self.topgg_update.start()

    async def cog_unload(self):
        if self.topgg_update.is_running():
            self.topgg_update.cancel()

    @tasks.loop(hours=1)
    async def topgg_update(self):
        if not self.bot.constants.TOPGG_TOKEN:
            logger.warning("TOPGG_TOKEN not set, task disabled for this build.")
            self.topgg_update.stop()
            return

        if not self.bot.http_session:
            logger.warning("HTTP session not yet created, skipping this run...")
            return

        try:
            async with self.bot.http_session.post(
                f"https://top.gg/api/bots/{self.bot.user.id}/stats",
                headers={"Authorization": self.bot.constants.TOPGG_TOKEN},
                json={"server_count": len(self.bot.guilds)},
            ) as response:
                if response.status == 200:
                    logger.info(
                        f"Updated Top.gg server count: {len(self.bot.guilds)} servers"
                    )
                elif response.status == 401:
                    logger.error(
                        "Top.gg token is invalid (401 Unauthorized). Stopping the update task."
                    )
                    self.topgg_update.stop()
                else:
                    text = await response.text()
                    logger.error(
                        f"Failed to update Top.gg server count: {response.status} - {text}"
                    )

        except asyncio.TimeoutError:
            logger.warning(
                "Timeout while trying to connect to Top.gg. Will retry next loop."
            )
        except aiohttp.ClientError as e:
            logger.error(f"Network error updating Top.gg server count: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in Top.gg update task: {e}")

    @topgg_update.before_loop
    async def before_topgg_update(self):
        await self.bot.wait_until_ready()

    @topgg_update.after_loop
    async def after_topgg_update(self):
        if self.topgg_update.failed():
            logger.error("Top.gg update task failed and loop has stopped.")


async def setup(bot: "Bot"):
    await bot.add_cog(TopggUpdate(bot))
