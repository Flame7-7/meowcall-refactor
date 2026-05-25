from __future__ import annotations

import sys

from utils import constants, logger
from utils.runtime.logger import handle_exception


def bootstrap() -> str:
    if constants.PRODUCTION:
        import sentry_sdk

        logger.debug("Initialising Sentry")
        sentry_sdk.init(
            dsn=constants.SENTRY_DSN,
            traces_sample_rate=1.0,
            enable_logs=True,
            profiles_sample_rate=1.0,
            send_default_pii=constants.SENTRY_SEND_DEFAULT_PII,
            release=f"oxara-meowcall@{constants.version}",
        )
        logger.info("Succesfully initialised sentry")
        return "Not in development"

    else:
        sys.excepthook = handle_exception
        return "In Development"
