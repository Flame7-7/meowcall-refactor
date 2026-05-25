from __future__ import annotations

from collections.abc import Awaitable
from typing import cast

from redis.exceptions import RedisError

from utils import logger, redis_client


async def warm_redis_pools(connections_to_warm: int | None = None) -> None:
    pool = redis_client.connection_pool

    if connections_to_warm is None:
        connections_to_warm = pool.max_connections

    if not connections_to_warm:
        logger.warning("No connections to warm. `max_connections` may be unset.")
        return

    logger.debug(
        f"Warming Redis using a single probe for pool size {connections_to_warm}..."
    )
    try:
        response = await cast(Awaitable[bool], redis_client.ping())
        if response:
            logger.debug(
                f"Successfully warmed Redis pool. Target size was {connections_to_warm}."
            )
        else:
            logger.warning(
                "Redis ping returned falsy during warmup; pools will warm during use."
            )
    except RedisError as e:
        logger.warning(
            f"Failed to warm Redis pool: {e}; pools will warm during use.",
            exc_info=True,
        )
    except Exception as e:
        logger.warning(
            f"Unexpected Redis warmup failure: {e}; pools will warm during use.",
            exc_info=True,
        )


async def validate_redis_connection():
    try:
        response = await cast(Awaitable[bool], redis_client.ping())
        if response:
            logger.info("Initialised Redis successfully")
        else:
            logger.warning("Redis ping returned falsy; continuing with fallback cache.")

    except RedisError as e:
        logger.warning(
            f"Failed to connect to redis: {e}; continuing with fallback cache.",
            exc_info=True,
        )
    except Exception as e:
        logger.warning(
            f"Unexpected Redis validation failure: {e}; continuing with fallback cache.",
            exc_info=True,
        )
