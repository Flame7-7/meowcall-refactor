from __future__ import annotations

import asyncio
import sys

import discord

from core import lifespan
from core.bootstrap import bootstrap
from core.bot import Bot
from utils import logger
from utils.redis.zeroDowntime import wait_for_shard_gate


def create_bot() -> Bot:
    presence = bootstrap()
    bot = Bot(presence)
    bot._started_event = asyncio.Event()  # type: ignore[assignment]

    async def _setup_hook() -> None:
        await lifespan.setup_hook(bot)

    bot.setup_hook = _setup_hook  # type: ignore[assignment]

    @bot.event
    async def on_ready() -> None:
        await lifespan.on_ready(bot)
        bot._started_event.set() 

    original_close = bot.close

    async def _close() -> None:
        bot._shutdown_requested = True
        if bot._started_event.is_set():
            await lifespan.close(bot)
        await original_close()

    bot.close = _close  # type: ignore[assignment]

    @bot.event
    async def on_connect() -> None:
        logger.debug("Connected to discord gateway")

    @bot.event
    async def on_disconnect() -> None:
        logger.warning("Disconnected from discord gateway")
        bot._started_event.clear()

    @bot.event
    async def on_shard_ready(shard_id: int) -> None:
        await lifespan.on_shard_ready(bot, shard_id)
        logger.debug(f"Shard {shard_id} ready and ownership claimed.")

    @bot.event
    async def on_shard_disconnected(shard_id: int) -> None:
        logger.info(f"Shard {shard_id} has disconnected from discord gateway")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.guild:
            await wait_for_shard_gate(message.guild.shard_id)
        await bot.process_commands(message)

    @bot.event
    async def on_interaction(interaction: discord.Interaction) -> None:
        shard_id = interaction.guild.shard_id if interaction.guild else 0
        await wait_for_shard_gate(shard_id)
        bot.dispatch("interaction_processed", interaction)
        await bot.process_commands(interaction.message) if interaction.message else None
    
    return bot


async def start_bot(bot: Bot) -> None:
    max_retries = 10
    retry_delay = 5
    retries = 0

    while retries < max_retries:
        try:
            logger.info(f"Starting bot... (Attempt {retries + 1})")
            async with bot:
                await bot.start(bot.constants.TOKEN)

            if getattr(bot, "_shutdown_requested", False):
                return
        except discord.LoginFailure:
            logger.critical("Invalid bot token provided")
            sys.exit("FAILED TO START: INVALID TOKEN")
        except discord.HTTPException as e:
            logger.error(f"HTTP Exception occurred: {e}", exc_info=e)
        except discord.GatewayNotFound:
            logger.error("Discord gateway could not be found")
        except (OSError, TimeoutError, ConnectionResetError) as e:
            logger.error(f"Connection error occurred: {e}", exc_info=e)
        except Exception as e:
            logger.critical(f"Unexpected error occurred: {e}", exc_info=e)
            sys.exit("FAILED TO START: UNEXPECTED ERROR")

        retries += 1
        bot._started_event.clear() 
        if retries < max_retries:
            logger.info(f"Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)


async def runtime() -> None:
    bot = create_bot()
    try:
        await start_bot(bot)
    except asyncio.CancelledError:
        raise


if __name__ == "__main__":
    try:
        asyncio.run(runtime())
    except KeyboardInterrupt:
        sys.exit(0)