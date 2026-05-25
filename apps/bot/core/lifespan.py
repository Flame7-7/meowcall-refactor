from __future__ import annotations

import asyncio as _asyncio
import contextlib
import socket
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
import discord
from db import init_database

from services.orchestratorService import OrchestratorService
from utils import constants, logger, redis_client
from utils.redis import validate_redis_connection, warm_redis_pools
from utils.redis.zeroDowntime import (
    claim_shard,
    open_shard_gate,
    redis_shutdown_listener,
    run_ownership_heartbeat,
    subscribe_shard_handoffs,
    watch_shard_ownership,
)

if TYPE_CHECKING:
    from core.bot import Bot

BASE_DIRECTORY = Path(__file__).resolve().parent.parent
COGS_DIRECTORY = BASE_DIRECTORY / "cogs"

INSTANCE_ID = str(uuid.uuid4())
STARTUP_ANNOUNCEMENT_DONE_KEY = "startup:official_server_announcement:done"
STARTUP_ANNOUNCEMENT_LOCK_KEY = "startup:official_server_announcement:lock"
STARTUP_ANNOUNCEMENT_LOCK_TTL_SECONDS = 86_400


async def load_cogs(bot: Bot):
    count = 0
    loaded_cogs: list[str] = []

    for file in COGS_DIRECTORY.rglob("*.py"):
        cog_module = (
            file.relative_to(COGS_DIRECTORY)
            .with_suffix("")
            .as_posix()
            .replace("/", ".")
        )

        try:
            if cog_module in ("cogs.jishaku", "cogs.__init__") or cog_module.endswith(
                ".__init__"
            ):
                continue
            await bot.load_extension(f"cogs.{cog_module}")
            count += 1
            loaded_cogs.append(cog_module)
        except Exception as e:
            logger.error(f"{cog_module} failed to load: {e}", exc_info=e)

    logger.info(f"Successfully loaded {count} cog(s).")


async def setup_hook(bot: Bot) -> None:
    try:
        bot.db = init_database(constants.DATABASE_URL)
        if bot.http_session is None or bot.http_session.closed:
            bot.http_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(
                    limit=300,
                    limit_per_host=50,
                    keepalive_timeout=60,
                    enable_cleanup_closed=True,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                ),
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        logger.error(f"Failed to initialise database: {e}")
        raise

    await bot.emotes.load(bot)
    await validate_redis_connection()

    if constants.POOL_WARMING:
        await warm_redis_pools()

    await bot.sync_staff_ids()
    await load_cogs(bot)

    if constants.IS_CLUSTERED:
        bot.orchestrator = OrchestratorService(
            bot=bot,
            ws_url=constants.ORCHESTRATOR_WS,
            cluster_id=constants.CLUSTER_ID
        )
        await bot.orchestrator.connect()

    await bot._sync_app_commands()

    await bot.change_presence(activity=discord.CustomActivity(name=bot.presence_text))

    from core.errors.errorHandler import error_handler

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction[Bot],
        error: discord.app_commands.AppCommandError,
    ):
        await error_handler(interaction, error)


async def on_shard_ready(bot: Bot, shard_id: int) -> None:
    """
    Called when a shard has connected and received its READY payload.
    Claims ownership in Redis so the old instance knows to yield this
    shard. The gate stays closed until the old instance publishes the
    handoff event confirming it has disconnected.
    """
    if constants.IS_CLUSTERED:
        # If orchestrator instructed this replacement to hold shards closed,
        # do not open the gate until the handoff subscriber opens it.
        if constants.HOLD_SHARDS_CLOSED:
            await bot.orchestrator.send_shard_ready(shard_id)
            await bot.orchestrator.mark_shard_ready(shard_id)
            return

        open_shard_gate(shard_id)
        await bot.orchestrator.send_shard_ready(shard_id)
        await bot.orchestrator.mark_shard_ready(shard_id)
        return

    try:
        await claim_shard(INSTANCE_ID, shard_id)
    except Exception as e:
        logger.error(f"Failed to claim shard {shard_id}: {e}")
        # Fail open — don't leave the shard permanently blocked.
        open_shard_gate(shard_id)


async def on_ready(bot: Bot) -> None:
    logger.info(f"{bot.user} (ID: {bot.user.id}) has logged in.")
    bot.constants.CLIENT_ID = bot.user.id if bot.user else bot.constants.CLIENT_ID

    if constants.STARTUP_ANNOUNCEMENT_ENABLED:
        bot.loop.create_task(
            dispatch_startup_announcement(bot),
            name="startup-announcement-dispatch",
        )

    if not bot.constants.IS_CLUSTERED:
        await redis_client.set(f"startup:rolling:{socket.gethostname()}", INSTANCE_ID)

        # Signal old instances that a new one has arrived. The old instance's
        # redis_shutdown_listener picks this up as a fallback in case any shard
        # handoff events are missed.
        await redis_client.publish("startup:rolling:restart", INSTANCE_ID)
        logger.info(f"Instance {INSTANCE_ID} signal sent.")

        if await redis_client.delete("startup:commands_sync"):
            logger.debug("Redis sync key cleaned.")

        # Subscribe to per-shard handoff events published by the old instance
        # as it disconnects each shard. Gates open the instant each publish lands.
        bot._shard_handoff_task = bot.loop.create_task(
            subscribe_shard_handoffs(INSTANCE_ID, set(bot.shards.keys())),
            name="shard-handoff-subscriber",
        )

        # Refresh shard ownership TTLs so they don't expire during normal operation.
        bot._ownership_heartbeat_task = bot.loop.create_task(
            run_ownership_heartbeat(bot, INSTANCE_ID),
            name="shard-ownership-heartbeat",
        )

        # Watch for other instances claiming our shards and yield them when seen.
        bot._shard_watch_task = bot.loop.create_task(
            watch_shard_ownership(bot, INSTANCE_ID),
            name="shard-ownership-watcher",
        )

        # Fallback instance-level shutdown listener in case shard events are missed.
        bot._redis_shutdown_task = bot.loop.create_task(
            redis_shutdown_listener(bot, INSTANCE_ID),
            name="redis-shutdown-listener",
        )
    else:
        await bot.orchestrator.send_status('ready')
        async def metrics_loop():
            while True:
                await _asyncio.sleep(30)
                await bot.orchestrator.send_metrics()
        bot.loop.create_task(metrics_loop(), name='orchestrator-metrics-loop')

        # If this clustered instance was started as a replacement and the
        # orchestrator instructed it to hold shards closed, subscribe to
        # per-shard handoff events so gates open when the old instance
        # publishes them.
        if constants.HOLD_SHARDS_CLOSED:
            bot._shard_handoff_task = bot.loop.create_task(
                subscribe_shard_handoffs(INSTANCE_ID, set(bot.shards.keys())),
                name="shard-handoff-subscriber",
            )

        return


async def dispatch_startup_announcement(bot: Bot) -> None:
    try:
        if await redis_client.get(STARTUP_ANNOUNCEMENT_DONE_KEY):
            logger.debug("Startup announcement already sent; skipping.")
            return

        lock_acquired = await redis_client.set(
            STARTUP_ANNOUNCEMENT_LOCK_KEY,
            INSTANCE_ID,
            nx=True,
            ex=STARTUP_ANNOUNCEMENT_LOCK_TTL_SECONDS,
        )
        if not lock_acquired:
            logger.debug(
                "Another instance is already dispatching the startup announcement."
            )
            return

        if await redis_client.get(STARTUP_ANNOUNCEMENT_DONE_KEY):
            logger.debug("Startup announcement completed by another instance.")
            return

        message = constants.STARTUP_ANNOUNCEMENT_MESSAGE
        sent_count = 0
        skipped_count = 0
        failed_count = 0

        for guild in bot.guilds:
            member = guild.me or (bot.user and guild.get_member(bot.user.id))
            if member is None:
                skipped_count += 1
                continue

            target_channel = None

            if (
                guild.system_channel
                and guild.system_channel.permissions_for(member).send_messages
            ):
                target_channel = guild.system_channel
            else:
                for channel in sorted(guild.text_channels, key=lambda c: c.position):
                    if channel.permissions_for(member).send_messages:
                        target_channel = channel
                        break

            if target_channel is None:
                skipped_count += 1
                continue

            try:
                await target_channel.send(message)
                sent_count += 1
            except Exception as e:
                failed_count += 1
                logger.debug(
                    "Failed to send startup announcement to guild %s (%s): %s",
                    guild.name,
                    guild.id,
                    e,
                    exc_info=e,
                )

        await redis_client.set(STARTUP_ANNOUNCEMENT_DONE_KEY, INSTANCE_ID)
        logger.info(
            "Startup announcement dispatched. sent=%s skipped=%s failed=%s",
            sent_count,
            skipped_count,
            failed_count,
        )
    except Exception as e:
        logger.error("Startup announcement dispatch failed: %s", e, exc_info=e)
    finally:
        with contextlib.suppress(Exception):
            await redis_client.delete(STARTUP_ANNOUNCEMENT_LOCK_KEY)


async def close(bot: Bot) -> None:
    logger.info(f"Instance {INSTANCE_ID} cleaning up...")

    if constants.IS_CLUSTERED and hasattr(bot, 'orchestrator'):
        await bot.orchestrator.send_status('disconnected')
        await bot.orchestrator.close()

    if hasattr(bot, "db"):
        await bot.db.dispose()

    if (
        hasattr(bot, "http_session")
        and bot.http_session
        and not bot.http_session.closed
    ):
        await bot.http_session.close()

    for task_attr in (
        "_redis_shutdown_task",
        "_ownership_heartbeat_task",
        "_shard_watch_task",
        "_shard_handoff_task",
    ):
        task = getattr(bot, task_attr, None)
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(_asyncio.CancelledError):
                await task

    logger.info("Shutdown complete.")


async def release_shards_on_shutdown(bot: Bot) -> None:
    """Called by the orchestrator-driven drain path to release shards one-by-one.

    This function ensures each shard publishes its handoff event so the new
    replacement opens its gate promptly. It is safe to call even if the instance
    is not clustered; in that case it is a no-op.
    """
    if not constants.IS_CLUSTERED:
        return

    shard_ids = list(bot.shards.keys())
    for shard_id in shard_ids:
        try:
            # Attempt graceful disconnect of the shard
            shard = bot.get_shard(shard_id)
            if shard is not None:
                await shard.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting shard {shard_id}: {e}")

        # Publish handoff and allow the replacement to open its gate
        try:
            from utils.redis.zeroDowntime import release_shard

            await release_shard(INSTANCE_ID, shard_id)
        except Exception as e:
            logger.error(f"Failed to publish handoff for shard {shard_id}: {e}")

        # Short pause to let replacement detect handoff and open gate
        await _asyncio.sleep(0.5)