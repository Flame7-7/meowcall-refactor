from __future__ import annotations

import html
import random
from typing import TYPE_CHECKING, ClassVar

from cachetools import TTLCache
from utils import logger

if TYPE_CHECKING:
    from core.bot import Bot


class AnimeService:
    """Service for fetching and managing anime-related data from Jikan API and waifu services."""

    # Anime IDs that are children's shows or have predominantly young casts
    EXCLUDED_ANIME_IDS: ClassVar[set[int]] = {
        223,  # Dragon Ball
        813,  # Dragon Ball Z
        6033,  # Dragon Ball GT
        21,  # One Piece
        269,  # Bleach
        20,  # Naruto
        1735,  # Naruto Shippuden
    }

    # Keywords in character names/roles that hint at a child role
    CHILD_ROLE_KEYWORDS: ClassVar[set[str]] = {
        "child",
        "kid",
        "young",
        "little",
        "baby",
        "chibi",
    }

    # Cache with 30-minute TTL
    _cache = TTLCache(maxsize=50, ttl=1800)

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @staticmethod
    def _looks_like_child_character(char_data: dict) -> bool:
        """Check if a character appears to be a child based on role and name keywords."""
        name: str = char_data.get("name", "").lower()
        role: str = char_data.get("role", "").lower()

        # Skip background characters
        if role == "background":
            return True

        # Check for child keywords
        return any(kw in name for kw in AnimeService.CHILD_ROLE_KEYWORDS)

    async def fetch_random_character(self, popular_anime_ids: list[int]) -> dict | None:
        """Fetch a random anime character with filtering for child characters."""
        max_attempts = 5

        for _ in range(max_attempts):
            try:
                eligible_ids = [
                    aid
                    for aid in popular_anime_ids
                    if aid not in self.EXCLUDED_ANIME_IDS
                ]
                anime_id = random.choice(eligible_ids)

                # Check and cache anime rating
                rating_cache_key = f"anime_{anime_id}_rating"
                if rating_cache_key not in self._cache:
                    async with self.bot.http_session.get(
                        f"https://api.jikan.moe/v4/anime/{anime_id}"
                    ) as resp:
                        if resp.status != 200:
                            continue
                        anime_data = (await resp.json()).get("data", {})
                        rating = anime_data.get("rating", "")
                        self._cache[rating_cache_key] = rating
                else:
                    rating = self._cache[rating_cache_key]

                # Skip child-friendly content
                if rating and (
                    rating.startswith("G")
                    or (rating.startswith("PG") and "13" not in rating)
                ):
                    continue

                # Fetch characters
                cache_key = f"anime_{anime_id}_characters"
                if cache_key in self._cache:
                    characters = self._cache[cache_key]
                else:
                    async with self.bot.http_session.get(
                        f"https://api.jikan.moe/v4/anime/{anime_id}/characters"
                    ) as response:
                        if response.status != 200:
                            continue
                        data = await response.json()
                        characters = data.get("data", [])
                        if not characters:
                            continue
                        self._cache[cache_key] = characters

                # Filter valid characters
                valid_characters = [
                    c
                    for c in characters
                    if (
                        c["character"]["images"]["jpg"]["image_url"]
                        and c["character"]["name"]
                        and not self._looks_like_child_character(
                            {
                                "name": c["character"]["name"],
                                "role": c.get("role", ""),
                            }
                        )
                    )
                ]

                if not valid_characters:
                    continue

                character = random.choice(valid_characters)["character"]
                anime_titles = await self.fetch_anime_titles(anime_id)

                return {
                    "name": character["name"],
                    "anime": anime_titles.get("english")
                    or anime_titles.get("default", "Unknown Anime"),
                    "image": character["images"]["jpg"]["image_url"],
                    "anime_id": anime_id,
                }
            except Exception as e:
                logger.error(f"Error fetching character: {e}")
                continue

        return None

    async def fetch_anime_titles(self, anime_id: int) -> dict[str, str]:
        """Fetch anime titles (default and English)."""
        try:
            cache_key = f"anime_{anime_id}_titles"
            if cache_key in self._cache:
                return self._cache[cache_key]

            async with self.bot.http_session.get(
                f"https://api.jikan.moe/v4/anime/{anime_id}"
            ) as response:
                if response.status != 200:
                    return {"default": "Unknown Anime"}

                data = await response.json()
                titles = data["data"]["titles"]
                title_dict = {"default": titles[0]["title"]}

                for title in titles:
                    if title["type"] == "English":
                        title_dict["english"] = title["title"]
                        break

                self._cache[cache_key] = title_dict
                return title_dict
        except Exception as e:
            logger.error(f"Error fetching anime titles: {e}")
            return {"default": "Unknown Anime"}

    async def fetch_random_waifu(self) -> dict | None:
        """Fetch a random safe waifu image."""
        try:
            # Try waifu.im first
            url = "https://api.waifu.im/images"
            query = "IncludedTags=waifu&ExcludedTags=underage&ExcludedTags=loli&IsNsfw=false"
            async with self.bot.http_session.get(f"{url}?{query}") as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get("items", [])
                    if items:
                        image_data = items[0]
                        # 2. Check the URL and NSFW status using the correct JSON keys
                        waifu_url = image_data.get("url")

                        # Note: is_nsfw is usually snake_case in the response body
                        is_nsfw = image_data.get("isNsfw", False)

                        if waifu_url and not is_nsfw:
                            return {"image": waifu_url, "source": "waifu.im"}
            return None
        except Exception as e:
            logger.error(f"Error fetching waifu: {e}")
            return None

    async def fetch_anime_recommendation(self, anime_id: int) -> dict | None:
        """Fetch detailed anime recommendation data."""
        try:
            async with self.bot.http_session.get(
                f"https://api.jikan.moe/v4/anime/{anime_id}"
            ) as response:
                if response.status != 200:
                    return None

                data = (await response.json()).get("data", {})

                return {
                    "title": data.get("title_english") or data.get("title", "Unknown"),
                    "synopsis": (
                        data.get("synopsis", "No synopsis available.")[:200] + "..."
                    )
                    if data.get("synopsis")
                    else "No synopsis available.",
                    "genres": ", ".join(g["name"] for g in data.get("genres", []))
                    or "Unknown",
                    "image": data.get("images", {}).get("jpg", {}).get("image_url", ""),
                    "url": data.get("url", ""),
                }
        except Exception as e:
            logger.error(f"Error fetching anime recommendation: {e}")
            return None

    @staticmethod
    async def fetch_trivia_question(session) -> dict | None:
        """Fetch an anime trivia question from OpenTDB."""
        try:
            async with session.get(
                "https://opentdb.com/api.php?amount=1&category=31&type=multiple"
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                if data.get("response_code") != 0:
                    return None

                res = data["results"][0]
                question = html.unescape(res["question"])
                correct = html.unescape(res["correct_answer"])
                options = [html.unescape(ans) for ans in res["incorrect_answers"]] + [
                    correct
                ]
                random.shuffle(options)

                return {
                    "question": question,
                    "correct": correct,
                    "options": options,
                }
        except Exception as e:
            logger.error(f"Error fetching trivia: {e}")
            return None
