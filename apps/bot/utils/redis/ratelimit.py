from __future__ import annotations

import asyncio

from discord.ext import commands
from redis.exceptions import MaxConnectionsError

from core.errors.customDiscord import RateLimited
from utils import constants, redis_client


async def message_rate_limit(ctx: commands.Context) -> bool:
    scope = "standard"

    limit = constants.RATE_LIMITS[scope]["commands"]["limit"]
    period = constants.RATE_LIMITS[scope]["commands"]["period"]

    key = f"command_rate_limit:{ctx.guild.id if ctx.guild else ctx.author.id}:{ctx.author.id}"

    for attempt in range(3):
        try:
            count = await redis_client.incr(key)

            if count == 1:
                await redis_client.expire(key, period)

            if count > limit:
                raise RateLimited()

            return True

        except RateLimited:
            raise
        except MaxConnectionsError:
            if attempt < 2:
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            # Pool exhausted after retries — fail open so commands aren't silently dropped
            return True
        except Exception:
            # Any other Redis failure — fail open
            return True

    return True