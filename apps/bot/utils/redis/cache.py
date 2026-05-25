from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, ClassVar

from redis.exceptions import MaxConnectionsError

from utils import logger, redis_client

if TYPE_CHECKING:
    from utils.interfaces import MeowcallBadge


class CacheManager:
    # TTL Values - In seconds
    DEFAULT_TTL = 300  # 5 Minutes
    SHORT_TTL = 30
    MEDIUM_TTL = 600  # 10 Minutes
    LONG_TTL = 3600  # 1 Hour

    PREFIXES: ClassVar[dict[str, str]] = {
        "user_badges": "badges:user",
        "validation": "validation",
        "webhook": "webhook",
        "user_data": "user",
        "guild_data": "guild",
        "connection": "connection",
        "rate_limit": "rate_limit",
        "spam_check": "spam_check",
        "spam_warnings": "spam_warnings",
        "guild_prefix": "prefix:guild",
        "voters": "voters",
    }

    def __init__(self):
        self.redis = redis_client
        self._lock = asyncio.locks

    def _build_key(self, prefix: str, *args: str) -> str:
        if prefix not in self.PREFIXES:
            raise ValueError(f"Unknown cache prefix: {prefix}")

        base_key = self.PREFIXES[prefix]
        if args:
            return f"{base_key}:{':'.join(str(arg) for arg in args)}"
        return base_key

    async def get(self, prefix: str, *args: str) -> Any | None:
        try:
            key = self._build_key(prefix, *args)
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None

        except MaxConnectionsError:
            logger.debug(
                "Cache get throttled (max connections) for %s:%s", prefix, args
            )
            return None
        except Exception as e:
            logger.warning(f"Cache get failed for {prefix}:{args}: {e}")
            return None

    async def set(
        self, prefix: str, *args: str, value: Any, ttl: int = DEFAULT_TTL
    ) -> bool:
        try:
            key = self._build_key(prefix, *args)
            serialised_valie = json.dumps(value, default=str)

            await self.redis.setex(key, ttl, serialised_valie)
            return True

        except Exception as e:
            if isinstance(e, MaxConnectionsError):
                logger.debug(
                    "Cache set throttled (max connections) for %s:%s", prefix, args
                )
            else:
                logger.warning(f"Cache set failed for {prefix}:{args}: {e}")
            return False

    async def delete(self, prefix: str, *args: str) -> bool:
        try:
            key = self._build_key(prefix, *args)
            await self.redis.delete(key)
            return True
        except Exception as e:
            if isinstance(e, MaxConnectionsError):
                logger.debug(
                    "Cache delete throttled (max connections) for %s:%s", prefix, args
                )
            else:
                logger.warning(f"Cache delete failed for {prefix}:{args}: {e}")
            return False

    async def get_user_profile(
        self, user_id: str | int
    ) -> dict | None:
        """Get cached user profile. Returns None if not cached."""
        return await self.get("user_data", str(user_id), "profile")
    
    async def set_user_profile(
        self, user_id: str | int, profile_data: dict
    ) -> bool:
        """Cache user profile with LONG_TTL (1 hour)."""
        return await self.set(
            "user_data",
            str(user_id),
            "profile",
            value=profile_data,
            ttl=self.LONG_TTL
        )
    
    async def get_guild_profile(
        self, guild_id: str | int
    ) -> dict | None:
        """Get cached guild profile. Returns None if not cached."""
        return await self.get("guild_data", str(guild_id), "profile")
    
    async def set_guild_profile(
        self, guild_id: str | int, profile_data: dict
    ) -> bool:
        """Cache guild profile with LONG_TTL (1 hour)."""
        return await self.set(
            "guild_data",
            str(guild_id),
            "profile",
            value=profile_data,
            ttl=self.LONG_TTL
        )
    
    async def get_user_validation(
        self, user_id: str | int, guild_id: str | int
    ) -> dict | None:
        """Get cached validation result. Returns None if not cached."""
        return await self.get("validation", str(user_id), str(guild_id))
    
    async def set_user_validation(
        self,
        user_id: str | int,
        guild_id: str | int,
        is_valid: bool,
        reason: str | None = None,
    ) -> bool:
        """Cache validation result with MEDIUM_TTL (10 minutes)."""
        return await self.set(
            "validation",
            str(user_id),
            str(guild_id),
            value={"valid": is_valid, "reason": reason},
            ttl=self.MEDIUM_TTL
        )

    async def exists(self, prefix: str, *args: str) -> bool:
        try:
            key = self._build_key(prefix, *args)
            return bool(await self.redis.exists(key))
        except Exception as e:
            if isinstance(e, MaxConnectionsError):
                logger.debug(
                    "Cache exists throttled (max connections) for %s:%s", prefix, args
                )
            else:
                logger.warning(f"Cache exists check failed for {prefix}:{args}: {e}")
            return False

    async def increment(self, prefix: str, *args: str, amount: int = 1) -> int | None:
        try:
            key = self._build_key(prefix, *args)
            return await self.redis.incrby(key, amount)
        except Exception as e:
            if isinstance(e, MaxConnectionsError):
                logger.debug(
                    "Cache increment throttled (max connections) for %s:%s",
                    prefix,
                    args,
                )
            else:
                logger.warning(f"Cache increment failed for {prefix}:{args}: {e}")
            return None

    async def expire(self, prefix: str, *args: str, ttl: int) -> bool:
        try:
            key = self._build_key(prefix, *args)
            await self.redis.expire(key, ttl)
            return True
        except Exception as e:
            if isinstance(e, MaxConnectionsError):
                logger.debug(
                    "Cache expire throttled (max connections) for %s:%s", prefix, args
                )
            else:
                logger.warning(f"Cache expire failed for {prefix}:{args}: {e}")
            return False

    async def get_multiple(self, keys: list[tuple]) -> dict[str, Any]:
        try:
            cache_keys = [self._build_key(prefix, *args) for prefix, *args in keys]
            values = await self.redis.mget(cache_keys)

            result = {}
            for i, (prefix, *args) in enumerate(keys):
                key_str = f"{prefix}:{':'.join(str(arg) for arg in args)}"
                if values[i]:
                    result[key_str] = json.loads(values[i])
                else:
                    result[key_str] = None

            return result
        except MaxConnectionsError:
            logger.debug("Cache get_multiple throttled (max connections)")
            return {}
        except Exception as e:
            logger.warning(f"Cache get_multiple failed: {e}")
            return {}

    async def set_multiple(self, items: dict[tuple, tuple]) -> bool:
        try:
            # Using async context manager ensures pipeline resources 
            # and connection state are always safely reset/returned.
            async with self.redis.pipeline() as pipe:
                for (prefix, *args), (value, ttl) in items.items():
                    key = self._build_key(prefix, *args)
                    serialized_value = json.dumps(value, default=str)
                    pipe.setex(key, ttl, serialized_value)

                await pipe.execute()
            return True
        except MaxConnectionsError:
            logger.debug("Cache set_multiple throttled (max connections)")
            return False
        except Exception as e:
            logger.warning(f"Cache set_multiple failed: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        try:
            count = 0
            async for key in self.redis.scan_iter(pattern):
                await self.redis.delete(key)
                count += 1
            return count
        except Exception as e:
            if isinstance(e, MaxConnectionsError):
                logger.debug(
                    "Cache clear_pattern throttled (max connections) for %s", pattern
                )
            else:
                logger.warning(f"Cache clear_pattern failed for {pattern}: {e}")
            return 0

    async def get_ttl(self, prefix: str, *args: str) -> int | None:
        try:
            key = self._build_key(prefix, *args)
            return await self.redis.ttl(key)
        except Exception as e:
            if isinstance(e, MaxConnectionsError):
                logger.debug(
                    "Cache get_ttl throttled (max connections) for %s:%s", prefix, args
                )
            else:
                logger.warning(f"Cache get_ttl failed for {prefix}:{args}: {e}")
            return None

    async def is_voter(self, user_id: str | int) -> bool:
        """Check if a user is a voter from cache. Returns boolean state value."""
        try:
            voter_state = await self.get("voters", str(user_id))
            return bool(voter_state) if voter_state is not None else False
        except Exception as e:
            logger.warning(f"Error checking voter status for user {user_id}: {e}")
            return False

    async def set_voter_state(
        self, user_id: str | int, is_voter: bool, ttl: int = LONG_TTL
    ) -> bool:
        """Set voter state in cache for a user."""
        return await self.set("voters", str(user_id), value=is_voter, ttl=ttl)

    @staticmethod
    async def flush_userphone_access_cache(
        user_id: str | int | None = None,
        guild_id: str | int | None = None,
    ) -> bool:
        """Flush cached userphone restriction and validation decisions.

        When a moderation action changes a user's or guild's access state,
        this clears the cached access-restriction lookups plus related
        validation entries that could otherwise keep stale allow/deny results.
        """
        try:
            cache = CacheManager()
            tasks: list[asyncio.Future | asyncio.Task] = []

            if user_id is not None:
                uid = str(user_id)
                tasks.extend(
                    [
                        cache.clear_pattern(f"user:{uid}:*:access_restriction"),
                        cache.clear_pattern(f"user:{uid}:*:validation"),
                        cache.clear_pattern(f"validation:{uid}:*"),
                        cache.clear_pattern(f"user:{uid}:*:ban"),
                        cache.clear_pattern(f"user:{uid}:*:blacklist"),
                    ]
                )

            if guild_id is not None:
                gid = str(guild_id)
                tasks.extend(
                    [
                        cache.clear_pattern(f"user:*:{gid}:access_restriction"),
                        cache.delete("guild_data", gid, "validation"),
                        cache.delete("guild_data", gid, "ban"),
                        cache.delete("guild_data", gid, "blacklist"),
                    ]
                )

            if not tasks:
                return True

            await asyncio.gather(*tasks, return_exceptions=True)
            return True
        except Exception as e:
            logger.debug(
                "Failed to flush userphone access cache for user=%s guild=%s: %s",
                user_id,
                guild_id,
                e,
            )
            return False


class UserBadgeCache:
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager

    async def get_user_badges(
        self, user_id: int
    ) -> tuple[bool, list[MeowcallBadge]] | None:
        data = await self.cache.get("user_badges", str(user_id))
        if data:
            return data["show_badges"], data["badges"]
        return None

    async def set_user_badges(
        self,
        user_id: int,
        show_badges: bool,
        badges: list[MeowcallBadge],
        ttl: int = CacheManager.DEFAULT_TTL,
    ) -> bool:
        data = {"show_badges": show_badges, "badges": badges}
        return await self.cache.set("user_badges", str(user_id), value=data, ttl=ttl)

    async def clear_user_badges(self, user_id: int) -> bool:
        return await self.cache.delete("user_badges", str(user_id))

    async def clear_all_badges(self) -> int:
        return await self.cache.clear_pattern(f"{self.cache.PREFIXES['user_badges']}:*")


class ValidationCache:
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager

    async def get_validation_result(
        self, user_id: str, guild_id: str, hub_id: str
    ) -> dict | None:
        return await self.cache.get("validation", user_id, guild_id, hub_id)

    async def set_validation_result(
        self,
        user_id: str,
        guild_id: str,
        hub_id: str,
        result: dict,
        ttl: int = CacheManager.SHORT_TTL,
    ) -> bool:
        return await self.cache.set(
            "validation", user_id, guild_id, hub_id, value=result, ttl=ttl
        )

    async def clear_validation_result(
        self, user_id: str, guild_id: str, hub_id: str
    ) -> bool:
        return await self.cache.delete("validation", user_id, guild_id, hub_id)


class WebhookCache:
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager

    async def get_webhook_url(self, channel_id: str) -> str | None:
        return await self.cache.get("webhook", channel_id)

    async def set_webhook_url(
        self, channel_id: str, webhook_url: str, ttl: int = CacheManager.MEDIUM_TTL
    ) -> bool:
        return await self.cache.set("webhook", channel_id, value=webhook_url, ttl=ttl)

    async def clear_webhook_url(self, channel_id: str) -> bool:
        return await self.cache.delete("webhook", channel_id)


# Global cache manager instance
cache_manager = CacheManager()
user_badge_cache = UserBadgeCache(cache_manager)
webhook_cache = WebhookCache(cache_manager)
