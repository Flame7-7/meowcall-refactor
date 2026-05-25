from __future__ import annotations

import logging
import sys

from .constants import constants

if not constants.PRODUCTION:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.theme import Theme

    console = Console(
        theme=Theme(
            {
                "logging.level.info": "#a6e3a1",
                "logging.level.debug": "#8aadf4",
                "logging.level.warning": "#f9e2af",
                "logging.level.error": "#f38ba8",
            }
        )
    )
    # Pretty logs in dev environments
    handler = RichHandler(tracebacks_width=200, console=console, rich_tracebacks=True)
else:
    # Boring logs in prod environments
    handler = logging.StreamHandler()

handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
level = logging.DEBUG if constants.DEBUG else logging.INFO

logger = logging.getLogger("Meowcall")
logger.setLevel(level)
logger.addHandler(handler)
logger.propagate = False

discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.INFO)
discord_logger.addHandler(handler)
discord_logger.propagate = False

discord_http_logger = logging.getLogger("discord.http")
discord_http_logger.setLevel(logging.INFO)
discord_http_logger.addHandler(handler)
discord_http_logger.propagate = False


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log the exception with full traceback
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
