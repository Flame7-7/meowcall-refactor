from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

import aiohttp
from utils import logger

if TYPE_CHECKING:
    from core.bot import Bot


class GifFetchService:
    BASE_URL = "https://api.waifu.pics"

    MALE_SOURCES: ClassVar[list[dict]] = [
        {
            "url": "https://api.waifu.im/search",
            "params": {"included_tags": "male", "is_nsfw": "false", "limit": "1"},
            "extractor": "_extract_waifuim",
        },
        {
            "url": "https://nekos.best/api/v2/husbando",
            "params": {},
            "extractor": "_extract_nekosbest",
        },
        {
            "url": "https://api.nekosapi.com/v4/images/random",
            "params": {"tags": "male", "rating": "safe", "limit": "1"},
            "extractor": "_extract_nekosapi",
        },
    ]

    CAT_SOURCES: ClassVar[list[dict]] = [
        # returns {"id": "...", "url": "https://..."} — real photos
        {
            "url": "https://cataas.com/cat",
            "params": {"json": "true"},
            "extractor": "_extract_cataas",
        }
    ]

    DOG_SOURCES: ClassVar[list[dict]] = [
        # returns {"url": "https://..."} — real photos, may include .mp4 so we filter
        {
            "url": "https://random.dog/woof.json",
            "params": {"filter": "mp4,webm"},
            "extractor": "_extract_image_url",
        },
        # returns {"message": "https://..."} — real photos from Stanford Dogs Dataset
        {
            "url": "https://dog.ceo/api/breeds/image/random",
            "params": {},
            "extractor": "_extract_dog_ceo",
        },
    ]

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    def _build_endpoint(self, *, rating: str, filter_tag: str) -> str:
        clean_rating = rating.strip("/").strip()
        clean_filter = filter_tag.strip("/").strip()
        return f"{self.BASE_URL}/{clean_rating}/{clean_filter}"

    @staticmethod
    def _extract_image_url(payload: object) -> str | None:
        if not isinstance(payload, dict):
            return None
        candidates = (
            payload.get("url"),
            payload.get("image_url"),
            payload.get("preview_url"),
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    @staticmethod
    def _extract_waifuim(data: object) -> str | None:
        if not isinstance(data, dict):
            return None
        images = data.get("images")
        if isinstance(images, list):
            for image in images:
                url = GifFetchService._extract_image_url(image)
                if url:
                    return url
        return GifFetchService._extract_image_url(data)

    @staticmethod
    def _extract_nekosbest(data: object) -> str | None:
        if not isinstance(data, dict):
            return None
        results = data.get("results")
        if isinstance(results, list):
            for result in results:
                url = GifFetchService._extract_image_url(result)
                if url:
                    return url
        return None

    @staticmethod
    def _extract_nekosapi(data: object) -> str | None:
        if not isinstance(data, dict):
            return None
        items = data.get("items")
        if isinstance(items, list):
            for item in items:
                url = GifFetchService._extract_image_url(item)
                if url:
                    return url
        return GifFetchService._extract_image_url(data)

    @staticmethod
    def _extract_cataas(data: object) -> str | None:
        """cataas.com: {"id": "...", "url": "/cat/..."} — prepend base URL."""
        if not isinstance(data, dict):
            return None
        url = data.get("url")
        if not isinstance(url, str) or not url:
            return None
        if url.startswith("http"):
            return url
        return f"https://cataas.com{url}"

    @staticmethod
    def _extract_dog_ceo(data: object) -> str | None:
        """dog.ceo: {"message": "https://...", "status": "success"}"""
        if not isinstance(data, dict):
            return None
        url = data.get("message")
        return url if isinstance(url, str) and url else None

    async def _fetch_from_source(self, source: dict) -> str | None:
        session = self.bot.http_session
        if session is None or session.closed:
            return None

        extractor_name = source["extractor"]
        extractor = getattr(self.__class__, extractor_name, None)
        if extractor is None:
            return None

        try:
            async with session.get(
                source["url"],
                params=source["params"] or None,
                timeout=aiohttp.ClientTimeout(total=12),
            ) as response:
                if response.status != 200:
                    return None
                data = await response.json(content_type=None)
        except Exception as exc:
            logger.debug(f"Fetch failed from {source['url']}: {exc}")
            return None

        return extractor(data)

    async def _fetch_from_sources(self, sources: list[dict]) -> str | None:
        """Try all sources in random order, return first hit."""
        shuffled = list(sources)
        random.shuffle(shuffled)
        for source in shuffled:
            url = await self._fetch_from_source(source)
            if url:
                return url
        return None

    async def _fetch_male_image(self) -> str | None:
        return await self._fetch_from_sources(self.MALE_SOURCES)

    async def fetch_cat(self, *, fallback_url: str | None = None) -> str | None:
        """Fetch a random real cat photo from multiple no-auth sources."""
        url = await self._fetch_from_sources(self.CAT_SOURCES)
        return url or fallback_url

    async def fetch_dog(self, *, fallback_url: str | None = None) -> str | None:
        """Fetch a random real dog photo from multiple no-auth sources."""
        url = await self._fetch_from_sources(self.DOG_SOURCES)
        return url or fallback_url

    async def fetch_gif(
        self,
        *,
        filter_tag: str,
        rating: str = "sfw",
        fallback_filters: Sequence[str] | None = None,
        fallback_url: str | None = None,
    ) -> str | None:
        if filter_tag == "male":
            male_url = await self._fetch_male_image()
            if male_url:
                return male_url
            if fallback_filters:
                fallback_urls = await self.fetch_gifs(
                    filters=fallback_filters, rating=rating, limit=1
                )
                if fallback_urls:
                    return fallback_urls[0]
            return fallback_url

        urls = await self.fetch_gifs(filters=[filter_tag], rating=rating, limit=1)
        if urls:
            return urls[0]

        if fallback_filters:
            fallback_urls = await self.fetch_gifs(
                filters=fallback_filters, rating=rating, limit=1
            )
            if fallback_urls:
                return fallback_urls[0]

        return fallback_url

    async def fetch_gifs(
        self,
        *,
        filters: Sequence[str],
        rating: str = "sfw",
        limit: int = 2,
    ) -> list[str]:
        if limit <= 0:
            return []

        normalized_filters = [
            f.strip() for f in filters if isinstance(f, str) and f.strip()
        ]
        if not normalized_filters:
            return []

        endpoints = [
            self._build_endpoint(rating=rating, filter_tag=tag)
            for tag in normalized_filters
        ]

        session = self.bot.http_session
        if session is None or session.closed:
            return []

        results: list[str] = []
        max_attempts = max(limit * len(endpoints) * 3, len(endpoints))

        for _ in range(max_attempts):
            if len(results) >= limit:
                break

            endpoint = random.choice(endpoints)
            try:
                async with session.get(
                    endpoint, timeout=aiohttp.ClientTimeout(total=12)
                ) as response:
                    if response.status != 200:
                        continue
                    data = await response.json(content_type=None)
            except Exception as exc:
                logger.debug(f"GIF fetch failed from {endpoint}: {exc}")
                continue

            url = self._extract_image_url(data)
            if not url:
                continue

            if url in results:
                continue

            results.append(url)

        return results
