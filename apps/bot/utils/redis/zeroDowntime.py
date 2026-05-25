from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from utils import logger, redis_client

if TYPE_CHECKING:
    from core.bot import Bot

_SHARD_OWNER_TTL = 30
_POLL_INTERVAL = 0.5
_SHARD_HANDOFF_TIMEOUT = 15

_shard_gates: dict[int, asyncio.Event] = {}


def _get_gate(shard_id: int) -> asyncio.Event:
    if shard_id not in _shard_gates:
        _shard_gates[shard_id] = asyncio.Event()
    return _shard_gates[shard_id]


def open_shard_gate(shard_id: int) -> None:
    gate = _get_gate(shard_id)
    if not gate.is_set():
        gate.set()
        logger.info(f"Shard {shard_id} gate opened — now processing events.")


async def wait_for_shard_gate(shard_id: int) -> None:
    gate = _get_gate(shard_id)
    if gate.is_set():
        return
    try:
        await asyncio.wait_for(gate.wait(), timeout=_SHARD_HANDOFF_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(
            f"Shard {shard_id} gate timed out after {_SHARD_HANDOFF_TIMEOUT}s — opening anyway."
        )
        gate.set()


async def subscribe_shard_handoffs(instance_id: str, shard_ids: set[int]) -> None:
    """
    Runs on the NEW instance. Subscribes to handoff events for all shards
    and opens each gate as the old instance confirms it has disconnected.
    Exits once all shards have been opened or timed out.
    """
    channels = [f"shard:handoff:{shard_id}" for shard_id in shard_ids]
    pending = set(shard_ids)

    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(*channels)
        logger.info(
            f"Instance {instance_id} subscribed to handoff events for shards: {sorted(shard_ids)}"
        )

        # Open gates for any shards that have no current owner — they were
        # either never claimed (fresh deploy) or the old instance already died.
        for shard_id in list(pending):
            try:
                owner = await redis_client.get(f"shard:owner:{shard_id}")
                if owner is None or owner == instance_id:
                    logger.info(
                        f"Shard {shard_id} has no prior owner — opening gate immediately."
                    )
                    open_shard_gate(shard_id)
                    pending.discard(shard_id)
            except Exception as e:
                logger.error(f"Error checking owner for shard {shard_id}: {e}")

        if not pending:
            await pubsub.unsubscribe(*channels)
            return

        async for message in pubsub.listen():
            if not pending:
                break

            if message["type"] != "message":
                continue

            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()

            # channel is "shard:handoff:{shard_id}"
            try:
                shard_id = int(channel.split(":")[-1])
            except (ValueError, IndexError):
                continue

            if shard_id in pending:
                logger.info(
                    f"Received handoff signal for shard {shard_id} — opening gate."
                )
                open_shard_gate(shard_id)
                pending.discard(shard_id)

            if not pending:
                break

    except asyncio.CancelledError:
        # Task cancelled (e.g. during shutdown) — open remaining gates so
        # nothing is left permanently blocked.
        for shard_id in pending:
            open_shard_gate(shard_id)
        raise
    except Exception as e:
        logger.error(f"Shard handoff subscriber error: {e}")
        for shard_id in pending:
            open_shard_gate(shard_id)
    finally:
        try:
            await pubsub.unsubscribe(*channels)
            await pubsub.aclose()
        except Exception:
            pass


async def claim_shard(instance_id: str, shard_id: int) -> None:
    await redis_client.set(
        f"shard:owner:{shard_id}", instance_id, ex=_SHARD_OWNER_TTL
    )
    logger.info(f"Instance {instance_id} claimed shard {shard_id}.")


async def release_shard(instance_id: str, shard_id: int) -> None:
    """
    Called by the OLD instance when it disconnects a shard.
    Cleans up ownership and publishes the handoff event so the
    new instance opens its gate for this shard immediately.
    """
    try:
        current = await redis_client.get(f"shard:owner:{shard_id}")
        if current == instance_id:
            await redis_client.delete(f"shard:owner:{shard_id}")
        await redis_client.publish(f"shard:handoff:{shard_id}", instance_id)
        logger.info(f"Instance {instance_id} published handoff for shard {shard_id}.")
    except Exception as e:
        logger.error(f"Error releasing shard {shard_id}: {e}")


async def refresh_shard_ownership(instance_id: str, shard_ids: list[int]) -> None:
    for shard_id in shard_ids:
        try:
            current = await redis_client.get(f"shard:owner:{shard_id}")
            if current == instance_id:
                await redis_client.expire(f"shard:owner:{shard_id}", _SHARD_OWNER_TTL)
        except Exception as e:
            logger.error(f"Error refreshing ownership for shard {shard_id}: {e}")


async def run_ownership_heartbeat(bot: Bot, instance_id: str) -> None:
    while not getattr(bot, "_shutdown_requested", False):
        try:
            await refresh_shard_ownership(instance_id, list(bot.shards.keys()))
        except Exception as e:
            logger.error(f"Ownership heartbeat error: {e}")
        await asyncio.sleep(_SHARD_OWNER_TTL // 3)


async def watch_shard_ownership(bot: Bot, instance_id: str) -> None:
    shard_ids = set(bot.shards.keys())
    logger.info(
        f"Instance {instance_id} watching ownership for shards: {sorted(shard_ids)}"
    )

    while shard_ids:
        await asyncio.sleep(_POLL_INTERVAL)

        yielded: set[int] = set()
        for shard_id in list(shard_ids):
            try:
                current_owner = await redis_client.get(f"shard:owner:{shard_id}")

                if current_owner is None:
                    # No owner — reclaim defensively
                    await claim_shard(instance_id, shard_id)

                elif current_owner != instance_id:
                    logger.warning(
                        f"Shard {shard_id} claimed by {current_owner} — "
                        f"yielding from {instance_id}."
                    )
                    shard = bot.get_shard(shard_id)
                    if shard is not None:
                        try:
                            await shard.disconnect()
                        except Exception as e:
                            logger.error(f"Error disconnecting shard {shard_id}: {e}")

                    await release_shard(instance_id, shard_id)
                    yielded.add(shard_id)

            except Exception as e:
                logger.error(f"Error checking ownership for shard {shard_id}: {e}")
                yielded.add(shard_id)  # also yield on outer failure to prevent infinite loop

        shard_ids -= yielded

    logger.warning(
        f"Instance {instance_id} has yielded all shards — initiating shutdown."
    )
    asyncio.create_task(bot.close())


async def redis_shutdown_listener(bot: Bot, instance_id: str) -> None:
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("startup:rolling:restart")
        logger.info(f"Instance {instance_id} listening for shutdown signals.")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            incoming = message["data"]
            if isinstance(incoming, bytes):
                incoming = incoming.decode()

            if incoming != instance_id:
                logger.warning(
                    f"New instance {incoming} detected. Shutting down {instance_id}..."
                )
                await pubsub.unsubscribe("startup:rolling:restart")
                await bot.close()
                return

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Redis shutdown listener error: {e}")