from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from core.cogs import CogBase
from discord.ext import tasks
from services.messageService import MessageService
from utils import logger

if TYPE_CHECKING:
    from core.bot import Bot
    from sqlalchemy.ext.asyncio import AsyncSession


class MessageCleanup(CogBase):
    def __init__(self, bot: Bot):
        super().__init__(bot, None)

    async def cog_load(self):
        self.message_cleanup.start()

    async def cog_unload(self):
        if self.message_cleanup.is_running():
            self.message_cleanup.cancel()

    @staticmethod
    def _service(session: AsyncSession) -> MessageService:
        return MessageService(session)

    @tasks.loop(hours=1)
    async def message_cleanup(self):
        logger.info("Running message cleanup...")
        # Assuming UTC is imported correctly now by the user
        before24h = datetime.now(timezone.utc) - timedelta(days=1)

        total_deleted = 0
        while True:
            async with self.bot.db.uow() as uow:
                svc = self._service(uow.session)
                messages = await svc.get_unprotected_messages_older_than(
                    before24h, 100_000
                )
                if not messages:
                    break

                message_ids = [m.id for m in messages]
                await svc.bulk_delete_messages(message_ids)
                total_deleted += len(message_ids)

        logger.debug(f"Cleaned up {total_deleted} messages from the database")

    @message_cleanup.before_loop
    async def before_message_clean(self):
        await self.bot.wait_until_ready()

    @message_cleanup.after_loop
    async def after_message_clean(self):
        if self.message_cleanup.failed():
            self.message_cleanup.stop()


async def setup(bot: Bot):
    await bot.add_cog(MessageCleanup(bot))
