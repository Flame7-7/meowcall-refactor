from __future__ import annotations

import re


class Patterns:
    URL = re.compile(r"https?://\S+")
    """ Matches http/https URLs """

    URL_BROAD = re.compile(
        r"(?i)(?:\b(?:https?://|www\.)\S+|\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?)"
    )
    """ Matches common links, including protocol, www-prefixed, and bare domains """

    IMAGE_URL_STRICT = re.compile(
        r"^https?://[^\s]+\.(?:png|jpe?g|gif|webp)$", re.IGNORECASE
    )
    """ Matches http/https image URLs ending in png/jpg/jpeg/gif/webp """

    DURATION = re.compile(r"(\d+)\s*([a-z]+)", re.IGNORECASE)
    """ Matches duration strings like '10m', '2 hours', '3d', etc. """

    DISCORD_ID = re.compile(r"^\d{17,20}$")
    """ Matches Discord IDs (17 to 20 digit numbers) """

    DISCORD_ID_OR_MENTION = re.compile(r"^(?:<@!?)?(?P<discord_id>[0-9]{15,20})(?:>)?$")
    """ Matches Discord IDs or mentions like `<@12345678901234567>` or `<@!12345678901234567>` """

    DISCORD_EMOJI = re.compile(r"<(a?):([^:]+):(\d+)>")
    """ Matches custom Discord emojis like `<emoji_name:emoji_id>` or `<a:emoji_name:emoji_id>` """

    MESSAGE_LINK = re.compile(
        r"https?://(?:(ptb|canary|www)\.)?discord(?:app)?\.com/channels/"
        r"(?P<guild_id>[0-9]{15,20})"
        r"/(?P<channel_id>[0-9]{15,20})/(?P<message_id>[0-9]{15,20})/?$"
    )
    """ Matches Discord message links (eg. `https://discord.com/channels/{guild_id}/{channel_id}/{message_id}`) """

    DISCORD_INVITE = re.compile(
        r"(?:https?://)?(?:www\.)?discord(?:app)?\.(?:gg|com/invite)/([a-zA-Z0-9-]+)"
    )
    """ Matches Discord invite links """

    DISCORD_INVITE_BROAD = re.compile(
        r"(?:https?://)?discord(?:\.gg|app\.com/invite)/[a-zA-Z0-9-]+"
    )
    """ Broad match for Discord invite links """

    MENTION_EVERYONE_HERE = re.compile(r"@(everyone|here)")
    """ Matches @everyone and @here mentions """

    FORBIDDEN_USERNAMES = re.compile(r"(discord|clyde|meowcall|```)", re.IGNORECASE)
    """ Matches forbidden usernames containing 'discord', 'clyde', or code blocks """

    IMAGE_URL_MARKER = re.compile(r"\[⁥]\(([^)]+)\)")
    """ Matches image or video URLs marked with an invisible separator """

    GIF_URL_MARKER = re.compile(r"\[♥]\(([^)]+)\)")
    """ Matches GIF URLs marked with a special wuv yuu separator """

    GIF_URL_STRICT = re.compile(r"^https?://[^\s]+\.gif$", re.IGNORECASE)
    """ Matches gif URLs ending in .gif """

    TENOR_URL = re.compile(
        r"^https?://(?:www\.)?tenor\.com/(?:view/|share/).+", re.IGNORECASE
    )
    """ Matches Tenor share/embed URLs """

    GIPHY_URL = re.compile(
        r"^https?://(?:www\.)?(?:media\.)?giphy\.com/.+", re.IGNORECASE
    )
    """ Matches Giphy share/embed URLs """

    WHITESPACE = re.compile(r"\s+")
    """ Matches one or more whitespace characters """

    ASTERISKS_ONLY = re.compile(r"[\*\s]+")
    """ Matches strings containing only asterisks and whitespace """

    WORDS = re.compile(r"\b\w+\b")
    """ Matches individual words """

    PYPROJECT_VERSION = re.compile(r'^version\s*=\s*["\']([^"\']+?)["\']', re.MULTILINE)
    """ Matches version strings in pyproject.toml files """
