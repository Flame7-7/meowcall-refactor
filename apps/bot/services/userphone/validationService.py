import asyncio
import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp
import discord
from utils import constants, logger
from utils.patterns import Patterns
from utils.userphone import check_bans_and_validation as _check_bans_and_validation

if TYPE_CHECKING:
    from core.bot import Bot
    from sqlalchemy.ext.asyncio import AsyncSession
    from utils.redis.cache import CacheManager
    from utils.userphone import ValidationCtx


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    reason: str | None = None


class ValidationService:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    """
    Message Validation
    """

    @staticmethod
    def _has_image_attachment(message: discord.Message) -> bool:
        for attachment in message.attachments:
            content_type = (attachment.content_type or "").lower()
            if content_type.startswith("image/"):
                return True

            filename = attachment.filename.lower()
            if filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
                return True

        return False

    @staticmethod
    def _is_tenor_or_giphy(url: str) -> bool:
        """Return True if the URL is a Tenor or Giphy share/embed link."""
        return bool(Patterns.TENOR_URL.match(url) or Patterns.GIPHY_URL.match(url))

    async def validate_url(
        self, message: discord.Message, is_voter: bool = False
    ) -> ValidationResult:

        logger.debug("validate_url message=%r is_voter=%s", message.content, is_voter)

        if message.attachments:
            logger.debug(
                "validate_url found %s attachment(s)", len(message.attachments)
            )

            attachment_urls: list[str] = []
            for attachment in message.attachments:
                logger.debug(
                    "attachment filename=%s content_type=%s url=%s",
                    attachment.filename,
                    attachment.content_type,
                    attachment.url,
                )

                content_type = (attachment.content_type or "").lower()
                is_image = content_type.startswith("image/")

                if not is_image:
                    filename = attachment.filename.lower()
                    is_image = filename.endswith(
                        (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
                    )

                if not is_image:
                    return ValidationResult(False, "Only image attachments are allowed")

                attachment_urls.append(attachment.url)

            if attachment_urls:
                tasks = [self.validate_image_safe(u) for u in attachment_urls]
                results = await asyncio.gather(*tasks)
                for res in results:
                    if not res.valid:
                        return res

        matches = list(Patterns.URL_BROAD.finditer(message.content))

        logger.debug("validate_url matches=%s", len(matches))

        if not matches:
            return ValidationResult(True)

        url_checks: list[str] = []
        for match in matches:
            url = match.group(0)
            image_marker = Patterns.IMAGE_URL_MARKER.search(url)
            gif_marker = Patterns.GIF_URL_MARKER.search(url)

            if image_marker:
                inner_url = image_marker.group(1)
                logger.debug("validate_url detected image url=%s", inner_url)
                if not Patterns.IMAGE_URL_STRICT.match(inner_url):
                    return ValidationResult(False, "Invalid image URL")
                url_checks.append(inner_url)

            elif gif_marker:
                inner_url = gif_marker.group(1)
                logger.debug("validate_url detected gif url=%s", inner_url)
                if not Patterns.IMAGE_URL_STRICT.match(inner_url):
                    return ValidationResult(False, "Invalid GIF URL")
                url_checks.append(inner_url)

            elif self._is_tenor_or_giphy(url):
                # Tenor/Giphy links are allowed for everyone — these platforms
                # self-moderate and direct image URLs aren't available to scrape.
                logger.debug("validate_url allowing tenor/giphy url=%s", url)
                continue

            else:
                logger.debug("validate_url rejected non-image url=%s", url)
                return ValidationResult(False, 'URLs aren\'t allowed here 🙀 [Vote for me on Top.gg](https://top.gg/bot/1355389597818945639/vote) to unlock GIFs and images for 12 hours! 😸')

        if url_checks:
            tasks = [self.validate_image_safe(u) for u in url_checks]
            results = await asyncio.gather(*tasks)
            for res in results:
                if not res.valid:
                    return res

        return ValidationResult(True)

    @staticmethod
    def validate_invite(message: discord.Message) -> ValidationResult:

        if Patterns.DISCORD_INVITE.search(message.content):
            return ValidationResult(False, "Message cannot contain Discord invites")

        return ValidationResult(True)

    @staticmethod
    def validate_not_empty(message: discord.Message) -> ValidationResult:

        content = Patterns.WHITESPACE.sub("", message.content)

        has_image_attachment = ValidationService._has_image_attachment(message)

        if (
            not content and not has_image_attachment
        ) or Patterns.ASTERISKS_ONLY.fullmatch(content):
            return ValidationResult(False, "Message cannot be empty")

        return ValidationResult(True)

    @staticmethod
    def validate_length(message: discord.Message) -> ValidationResult:

        if (
            len(message.content) > 1024
        ):  # Discord allows up to 2000 characters, but we leave room for formatting.
            return ValidationResult(False, "Message must not exceed 1024 characters")

        return ValidationResult(True)

    @staticmethod
    def validate_pings(message: discord.Message) -> ValidationResult:

        if Patterns.MENTION_EVERYONE_HERE.search(message.content):
            return ValidationResult(False, "Your message may not contain mentions")

        return ValidationResult(True)

    async def validate_message(
        self, message: discord.Message, is_voter: bool = False
    ) -> ValidationResult:

        checks = (
            self.validate_not_empty,
            self.validate_length,
            lambda m: self.validate_url(m, is_voter=is_voter),
            self.validate_invite,
            self.validate_pings,
        )

        for check in checks:
            result = check(message)
            if inspect.iscoroutine(result):
                result = await result

            if not result.valid:
                return result

        return ValidationResult(True)

    """
    User Validation
    """

    @staticmethod
    def validate_forbidden_username(
        user: discord.Member | discord.User,
    ) -> ValidationResult:
        names_to_check = [
            user.name,
            user.display_name,
            getattr(user, "global_name", None),
        ]
        for name in names_to_check:
            if name and Patterns.FORBIDDEN_USERNAMES.search(name):
                return ValidationResult(
                    False, "Your username contains forbidden words."
                )

        return ValidationResult(True)

    @staticmethod
    def validate_mentions_in_username(
        user: discord.Member | discord.User,
    ) -> ValidationResult:
        names_to_check = [
            user.name,
            user.display_name,
            getattr(user, "global_name", None),
        ]
        for name in names_to_check:
            if name and Patterns.MENTION_EVERYONE_HERE.search(name):
                return ValidationResult(False, "Your username cannot contain mentions.")

        return ValidationResult(True)

    @staticmethod
    def validate_urls_in_username(
        user: discord.Member | discord.User,
    ) -> ValidationResult:
        names_to_check = [
            user.name,
            user.display_name,
            getattr(user, "global_name", None),
        ]
        for name in names_to_check:
            if name and Patterns.IMAGE_URL_STRICT.search(name):
                return ValidationResult(False, "Your username contains a URL.")

        return ValidationResult(True)

    def validate_username(
        self, user: discord.Member | discord.User
    ) -> ValidationResult:

        checks = (
            self.validate_forbidden_username,
            self.validate_mentions_in_username,
            self.validate_urls_in_username,
        )

        for check in checks:
            result = check(user)

            if not result.valid:
                return result

        return ValidationResult(True)

    async def check_bans_and_validation(
        self,
        ctx: "ValidationCtx | discord.Message",
        session: "AsyncSession | None",
        cache_manager: "CacheManager",
        bot: "Bot",
        check_username: bool = True,
        check_guild_name: bool = True,
    ) -> tuple[bool, str | None]:
        return await _check_bans_and_validation(
            ctx,
            session,
            cache_manager,
            self,
            bot,
            check_username=check_username,
            check_guild_name=check_guild_name,
        )

    """
    Guild Validation
    """

    @staticmethod
    def validate_forbidden_guild_name(guild: discord.Guild) -> ValidationResult:
        if guild.id == constants.DEVELOPER_GUILD_ID:
            return ValidationResult(True)
        if Patterns.FORBIDDEN_USERNAMES.search(guild.name):
            return ValidationResult(False, "Your guild name contains forbidden words. The official server HAS changed. The new  link is: https://discord.gg/BxNnGC8TAs")

        return ValidationResult(True)

    @staticmethod
    def validate_mentions_in_guild_name(guild: discord.Guild) -> ValidationResult:

        if Patterns.MENTION_EVERYONE_HERE.search(guild.name):
            return ValidationResult(False, "Your guild name cannot contain mentions.")

        return ValidationResult(True)

    @staticmethod
    def validate_urls_in_guild_name(guild: discord.Guild) -> ValidationResult:

        if Patterns.URL_BROAD.search(guild.name):
            return ValidationResult(False, "Your guild name contains a URL.")

        return ValidationResult(True)

    def validate_guild_name(self, guild: discord.Guild) -> ValidationResult:

        checks = (
            self.validate_forbidden_guild_name,
            self.validate_mentions_in_guild_name,
            self.validate_urls_in_guild_name,
        )

        for check in checks:
            result = check(guild)

            if not result.valid:
                return result

        return ValidationResult(True)

    """
    Image Validation
    """

    async def validate_image_safe(self, url: str) -> ValidationResult:

        payload = {"urls": [url]}

        logger.debug("validate_image_safe payload=%s", payload)

        if not constants.ENABLE_NSFW_DETECTION:
            logger.debug(
                "NSFW detection disabled (ENABLE_NSFW_DETECTION=False). Skipping check for %s",
                url,
            )
            return ValidationResult(True)

        async def _call_and_process(session: aiohttp.ClientSession) -> ValidationResult:
            async with session.post(constants.NSFW_DETECTOR_URL, json=payload) as resp:
                logger.debug("NSFW detector status=%s url=%s", resp.status, url)

                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    logger.exception(
                        "Failed to parse JSON from NSFW detector: %s", text
                    )
                    return ValidationResult(
                        False,
                        "Could not verify image safety - Please open a ticket in our support server.",
                    )

                logger.debug("NSFW detector response=%s", data)

                if resp.status == 404:
                    logger.error("NSFW detector returned 404 for URL", url)
                    return ValidationResult(
                        False,
                        "Could not verify image safety - Please open a ticket in our support server",
                    )

                if resp.status != 200:
                    logger.error(
                        "NSFW detector returned status=%s body=%s", resp.status, data
                    )
                    return ValidationResult(
                        False,
                        "Could not verify image safety - Please open a ticket in our support server",
                    )

                if isinstance(data, dict):
                    results = data.get("results", [data])
                elif isinstance(data, list):
                    results = data
                else:
                    logger.debug("Unexpected NSFW response type=%s", type(data))
                    return ValidationResult(
                        False,
                        "Could not verify image safety - Please open a ticket in our support server",
                    )

                if not results:
                    return ValidationResult(
                        False,
                        "Could not verify image safety - Please open a ticket in our support server",
                    )

                result = results[0]
                logger.debug("Parsed NSFW result=%s", result)

                is_nsfw = (
                    (result.get("is_nsfw") if isinstance(result, dict) else None)
                    or (result.get("nsfw") if isinstance(result, dict) else None)
                    or (result.get("unsafe") if isinstance(result, dict) else None)
                )

                if is_nsfw:
                    logger.debug("Image flagged NSFW url=%s", url)
                    return ValidationResult(False, "Image contains NSFW content")

                return ValidationResult(True)

        try:
            session_obj = getattr(self, "session", None)
            if (
                session_obj
                and hasattr(session_obj, "post")
                and not isinstance(session_obj, type)
            ):
                return await _call_and_process(session_obj)

            async with aiohttp.ClientSession() as temp_session:
                return await _call_and_process(temp_session)

        except aiohttp.ClientError:
            logger.exception(
                "Could not connect to NSFW detector %s", constants.NSFW_DETECTOR_URL
            )
            return ValidationResult(
                False,
                "Could not verify image safety - Please open a ticket in our support server",
            )
