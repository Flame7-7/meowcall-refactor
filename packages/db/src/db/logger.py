# Copyright (c) 2026 Oxara Development
# All rights reserved.
#
# This source code and any related materials are the confidential and
# proprietary information of Oxara Development.
#
# Unauthorized copying, modification, distribution, use, or disclosure
# of this software, in whole or in part, is strictly prohibited without
# prior written permission from Oxara Development.
#
# Use is restricted to authorized members of the Oxara Development team.
# Any other use requires prior written approval from Oxara Development.

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

production: bool = os.getenv('PRODUCTION', 'False').lower() in ('true', '1', 't')
is_debug_mode: bool = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

if not production:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.theme import Theme

    console = Console(
        theme=Theme(
            {
                'logging.level.info': '#a6e3a1',
                'logging.level.debug': '#8aadf4',
                'logging.level.warning': '#f9e2af',
                'logging.level.error': '#f38ba8',
            }
        )
    )
    handler: logging.Handler = RichHandler(tracebacks_width=200, console=console)
else:
    handler = logging.StreamHandler()  # plain logs for prod

handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))

logger: logging.Logger = logging.getLogger('db')
logger.setLevel(logging.DEBUG if is_debug_mode else logging.INFO)
logger.addHandler(handler)
logger.propagate = False
