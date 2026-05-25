from __future__ import annotations

import logging
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any, TypeGuard

import discord
from discord.ext import commands
from ui.layouts.common.errors import ErrorLayout
from ui.layouts.common.success import SuccessLayout

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.bot import Bot


class ErrorSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorResponseType(Enum):
    EMBED = "embed"
    TEXT = "text"
    EPHEMERAL = "ephemeral"
    DM = "dm"


class DiscordErrorCodes(IntEnum):
    """https://docs.discord.com/developers/topics/opcodes-and-status-codes#json"""

    GENERAL_ERROR = 0

    UNKNOWN_ACCOUNT = 10001
    UNKNOWN_APPLICATION = 10002
    UNKNOWN_CHANNEL = 10003
    UNKNOWN_GUILD = 10004
    UNKNOWN_INTEGRATION = 10005
    UNKNOWN_INVITE = 10006
    UNKNOWN_MEMBER = 10007
    UNKNOWN_MESSAGE = 10008
    UNKNOWN_PERMISSION_OVERWRITE = 10009
    UNKNOWN_PROVIDER = 10010
    UNKNOWN_ROLE = 10011
    UNKNOWN_TOKEN = 10012
    UNKNOWN_USER = 10013
    UNKNOWN_EMOJI = 10014
    UNKNOWN_WEBHOOK = 10015
    UNKNOWN_WEBHOOK_SERVICE = 10016
    UNKNOWN_SESSION = 10020
    UNKNOWN_ASSET = 10021
    UNKNOWN_BAN = 10026
    UNKNOWN_SKU = 10027
    UNKNOWN_STORE_LISTING = 10028
    UNKNOWN_ENTITLEMENT = 10029
    UNKNOWN_BUILD = 10030
    UNKNOWN_LOBBY = 10031
    UNKNOWN_BRANCH = 10032
    UNKNOWN_STORE_DIRECTORY_LAYOUT = 10033
    UNKNOWN_REDISTRIBUTABLE = 10036
    UNKNOWN_GIFT_CODE = 10038
    UNKNOWN_STREAM = 10049
    UNKNOWN_PREMIUM_SERVER_SUBSCRIBE_COOLDOWN = 10050
    UNKNOWN_GUILD_TEMPLATE = 10057
    UNKNOWN_DISCOVERABLE_SERVER_CATEGORY = 10059
    UNKNOWN_STICKER = 10060
    UNKNOWN_STICKER_PACK = 10061
    UNKNOWN_INTERACTION = 10062
    UNKNOWN_APPLICATION_COMMAND = 10063
    UNKNOWN_VOICE_STATE = 10065
    UNKNOWN_APPLICATION_COMMAND_PERMISSIONS = 10066
    UNKNOWN_STAGE_INSTANCE = 10067
    UNKNOWN_GUILD_MEMBER_VERIFICATION_FORM = 10068
    UNKNOWN_GUILD_WELCOME_SCREEN = 10069
    UNKNOWN_GUILD_SCHEDULED_EVENT = 10070
    UNKNOWN_GUILD_SCHEDULED_EVENT_USER = 10071
    UNKNOWN_TAG = 10087
    UNKNOWN_SOUND = 10097
    UNKNOWN_INVITE_TARGET_USERS_JOB = 10124
    UNKNOWN_INVITE_TARGET_USERS = 10129

    BOTS_CANNOT_USE_THIS_ENDPOINT = 20001
    ONLY_BOTS_CAN_USE_THIS_ENDPOINT = 20002
    EXPLICIT_CONTENT_CANNOT_BE_SENT_TO_RECIPIENTS = 20009
    NOT_AUTHORIZED_FOR_APPLICATION_ACTION = 20012
    ACTION_BLOCKED_BY_SLOWMODE_RATE_LIMIT = 20016
    ONLY_OWNER_CAN_PERFORM_THIS_ACTION = 20018
    MESSAGE_CANNOT_BE_EDITED_DUE_TO_ANNOUNCEMENT_RATE_LIMITS = 20022
    UNDER_MINIMUM_AGE = 20024
    CHANNEL_WRITE_RATE_LIMIT_HIT = 20028
    SERVER_WRITE_RATE_LIMIT_HIT = 20029
    CONTENT_CONTAINS_DISALLOWED_WORDS = 20031
    GUILD_PREMIUM_SUBSCRIPTION_LEVEL_TOO_LOW = 20035

    MAX_GUILDS_REACHED = 30001
    MAX_FRIENDS_REACHED = 30002
    MAX_PINS_REACHED_FOR_CHANNEL = 30003
    MAX_RECIPIENTS_REACHED = 30004
    MAX_GUILD_ROLES_REACHED = 30005
    MAX_WEBHOOKS_REACHED = 30007
    MAX_EMOJIS_REACHED = 30008
    MAX_REACTIONS_REACHED = 30010
    MAX_GROUP_DMS_REACHED = 30011
    MAX_GUILD_CHANNELS_REACHED = 30013
    MAX_ATTACHMENTS_IN_MESSAGE_REACHED = 30015
    MAX_INVITES_REACHED = 30016
    MAX_ANIMATED_EMOJIS_REACHED = 30018
    MAX_SERVER_MEMBERS_REACHED = 30019
    MAX_SERVER_CATEGORIES_REACHED = 30030
    GUILD_ALREADY_HAS_TEMPLATE = 30031
    MAX_APPLICATION_COMMANDS_REACHED = 30032
    MAX_THREAD_PARTICIPANTS_REACHED = 30033
    MAX_DAILY_APPLICATION_COMMAND_CREATES_REACHED = 30034
    MAX_BANS_FOR_NON_GUILD_MEMBERS_EXCEEDED = 30035
    MAX_BAN_FETCHES_REACHED = 30037
    MAX_UNCOMPLETED_GUILD_SCHEDULED_EVENTS_REACHED = 30038
    MAX_STICKERS_REACHED = 30039
    MAX_PRUNE_REQUESTS_REACHED = 30040
    MAX_GUILD_WIDGET_SETTINGS_UPDATES_REACHED = 30042
    MAX_SOUNDBOARD_SOUNDS_REACHED = 30045
    MAX_EDITS_TO_OLD_MESSAGES_REACHED = 30046
    MAX_PINNED_THREADS_IN_FORUM_REACHED = 30047
    MAX_TAGS_IN_FORUM_REACHED = 30048
    BITRATE_TOO_HIGH_FOR_CHANNEL_TYPE = 30052
    MAX_PREMIUM_EMOJIS_REACHED = 30056
    MAX_WEBHOOKS_PER_GUILD_REACHED = 30058
    MAX_CHANNEL_PERMISSION_OVERWRITES_REACHED = 30060
    CHANNELS_FOR_GUILD_ARE_TOO_LARGE = 30061

    UNAUTHORIZED = 40001
    ACCOUNT_VERIFICATION_REQUIRED = 40002
    OPENING_DIRECT_MESSAGES_TOO_FAST = 40003
    SEND_MESSAGES_TEMPORARILY_DISABLED = 40004
    REQUEST_ENTITY_TOO_LARGE = 40005
    FEATURE_TEMPORARILY_DISABLED_SERVER_SIDE = 40006
    USER_BANNED_FROM_GUILD = 40007
    CONNECTION_REVOKED = 40012
    ONLY_CONSUMABLE_SKUS_CAN_BE_CONSUMED = 40018
    ONLY_SANDBOX_ENTITLEMENTS_CAN_BE_DELETED = 40019
    TARGET_USER_NOT_CONNECTED_TO_VOICE = 40032
    MESSAGE_ALREADY_CROSSPOSTED = 40033
    APPLICATION_COMMAND_NAME_ALREADY_EXISTS = 40041
    APPLICATION_INTERACTION_FAILED_TO_SEND = 40043
    CANNOT_SEND_MESSAGE_IN_FORUM_CHANNEL = 40058
    INTERACTION_ALREADY_ACKNOWLEDGED = 40060
    TAG_NAMES_MUST_BE_UNIQUE = 40061
    SERVICE_RESOURCE_RATE_LIMITED = 40062
    NO_TAGS_AVAILABLE_FOR_NON_MODERATORS = 40066
    TAG_REQUIRED_TO_CREATE_FORUM_POST = 40067
    ENTITLEMENT_ALREADY_GRANTED_FOR_RESOURCE = 40074
    INTERACTION_MAX_FOLLOW_UP_MESSAGES_REACHED = 40094
    CLOUDFLARE_BLOCKING_REQUEST = 40333

    MISSING_ACCESS = 50001
    INVALID_ACCOUNT_TYPE = 50002
    CANNOT_EXECUTE_ACTION_ON_DM_CHANNEL = 50003
    GUILD_WIDGET_DISABLED = 50004
    CANNOT_EDIT_MESSAGE_AUTHORED_BY_ANOTHER_USER = 50005
    CANNOT_SEND_EMPTY_MESSAGE = 50006
    CANNOT_SEND_MESSAGES_TO_USER = 50007
    CANNOT_SEND_MESSAGES_IN_NON_TEXT_CHANNEL = 50008
    CHANNEL_VERIFICATION_LEVEL_TOO_HIGH = 50009
    OAUTH2_APPLICATION_DOES_NOT_HAVE_BOT = 50010
    OAUTH2_APPLICATION_LIMIT_REACHED = 50011
    INVALID_OAUTH2_STATE = 50012
    LACK_PERMISSIONS = 50013
    INVALID_AUTHENTICATION_TOKEN_PROVIDED = 50014
    NOTE_TOO_LONG = 50015
    INVALID_BULK_DELETE_MESSAGE_COUNT = 50016
    INVALID_MFA_LEVEL = 50017
    MESSAGE_CAN_ONLY_BE_PINNED_TO_SOURCE_CHANNEL = 50019
    INVITE_CODE_INVALID_OR_TAKEN = 50020
    CANNOT_EXECUTE_ACTION_ON_SYSTEM_MESSAGE = 50021
    CANNOT_EXECUTE_ACTION_ON_CHANNEL_TYPE = 50024
    INVALID_OAUTH2_ACCESS_TOKEN_PROVIDED = 50025
    MISSING_REQUIRED_OAUTH2_SCOPE = 50026
    INVALID_WEBHOOK_TOKEN_PROVIDED = 50027
    INVALID_ROLE = 50028
    INVALID_RECIPIENTS = 50033
    MESSAGE_TOO_OLD_TO_BULK_DELETE = 50034
    INVALID_FORM_BODY_OR_CONTENT_TYPE = 50035
    INVITE_ACCEPTED_TO_GUILD_BOT_NOT_IN = 50036
    INVALID_ACTIVITY_ACTION = 50039
    INVALID_API_VERSION_PROVIDED = 50041
    FILE_UPLOADED_EXCEEDS_MAXIMUM_SIZE = 50045
    INVALID_FILE_UPLOADED = 50046
    CANNOT_SELF_REDEEM_GIFT = 50054
    INVALID_GUILD = 50055
    INVALID_SKU = 50057
    INVALID_REQUEST_ORIGIN = 50067
    INVALID_MESSAGE_TYPE = 50068
    PAYMENT_SOURCE_REQUIRED_TO_REDEEM_GIFT = 50070
    CANNOT_MODIFY_SYSTEM_WEBHOOK = 50073
    CANNOT_DELETE_COMMUNITY_REQUIRED_CHANNEL = 50074
    CANNOT_EDIT_STICKERS_WITHIN_MESSAGE = 50080
    INVALID_STICKER_SENT = 50081
    OPERATION_ON_ARCHIVED_THREAD = 50083
    INVALID_THREAD_NOTIFICATION_SETTINGS = 50084
    BEFORE_VALUE_EARLIER_THAN_THREAD_CREATION = 50085
    COMMUNITY_SERVER_CHANNELS_MUST_BE_TEXT = 50086
    EVENT_ENTITY_TYPE_MISMATCH = 50091
    SERVER_NOT_AVAILABLE_IN_LOCATION = 50095
    SERVER_REQUIRES_MONETIZATION_ENABLED = 50097
    SERVER_NEEDS_MORE_BOOSTS = 50101
    REQUEST_BODY_CONTAINS_INVALID_JSON = 50109
    PROVIDED_FILE_INVALID = 50110
    PROVIDED_FILE_TYPE_INVALID = 50123
    PROVIDED_FILE_DURATION_EXCEEDS_MAX = 50124
    OWNER_CANNOT_BE_PENDING_MEMBER = 50131
    OWNERSHIP_CANNOT_TRANSFER_TO_BOT = 50132
    FAILED_TO_RESIZE_ASSET_BELOW_MAX = 50138
    CANNOT_MIX_SUBSCRIPTION_AND_NON_SUBSCRIPTION_ROLES_FOR_EMOJI = 50144
    CANNOT_CONVERT_BETWEEN_PREMIUM_AND_NORMAL_EMOJI = 50145
    UPLOADED_FILE_NOT_FOUND = 50146
    SPECIFIED_EMOJI_INVALID = 50151
    VOICE_MESSAGES_DO_NOT_SUPPORT_ADDITIONAL_CONTENT = 50159
    VOICE_MESSAGES_REQUIRE_SINGLE_AUDIO_ATTACHMENT = 50160
    VOICE_MESSAGES_REQUIRE_SUPPORTING_METADATA = 50161
    VOICE_MESSAGES_CANNOT_BE_EDITED = 50162
    CANNOT_DELETE_GUILD_SUBSCRIPTION_INTEGRATION = 50163
    CANNOT_SEND_VOICE_MESSAGES_IN_CHANNEL = 50173
    USER_ACCOUNT_MUST_BE_VERIFIED_FIRST = 50178
    PROVIDED_FILE_HAS_INVALID_DURATION = 50192
    NO_PERMISSION_TO_SEND_STICKER = 50600

    TWO_FACTOR_REQUIRED = 60003

    NO_USERS_WITH_DISCORDTAG_EXIST = 80004

    REACTION_BLOCKED = 90001
    USER_CANNOT_USE_BURST_REACTIONS = 90002

    APPLICATION_NOT_YET_AVAILABLE = 110001

    API_RESOURCE_OVERLOADED = 130000

    STAGE_ALREADY_OPEN = 150006

    CANNOT_REPLY_WITHOUT_READ_MESSAGE_HISTORY = 160002
    THREAD_ALREADY_CREATED_FOR_MESSAGE = 160004
    THREAD_LOCKED = 160005
    MAX_ACTIVE_THREADS_REACHED = 160006
    MAX_ACTIVE_ANNOUNCEMENT_THREADS_REACHED = 160007

    INVALID_JSON_FOR_UPLOADED_LOTTIE = 170001
    UPLOADED_LOTTIES_CANNOT_CONTAIN_RASTERIZED_IMAGES = 170002
    STICKER_MAX_FRAMERATE_EXCEEDED = 170003
    STICKER_FRAME_COUNT_EXCEEDS_MAX = 170004
    LOTTIE_MAX_DIMENSIONS_EXCEEDED = 170005
    STICKER_FRAME_RATE_OUT_OF_RANGE = 170006
    STICKER_ANIMATION_DURATION_EXCEEDS_MAX = 170007

    CANNOT_UPDATE_FINISHED_EVENT = 180000
    FAILED_TO_CREATE_STAGE_FOR_EVENT = 180002

    MESSAGE_BLOCKED_BY_AUTOMOD = 200000
    TITLE_BLOCKED_BY_AUTOMOD = 200001

    WEBHOOK_FORUM_REQUIRES_THREAD_NAME_OR_ID = 220001
    WEBHOOK_FORUM_CANNOT_HAVE_BOTH_THREAD_NAME_AND_ID = 220002
    WEBHOOK_CAN_ONLY_CREATE_THREADS_IN_FORUM = 220003
    WEBHOOK_SERVICES_CANNOT_BE_USED_IN_FORUM = 220004

    MESSAGE_BLOCKED_BY_HARMFUL_LINKS_FILTER = 240000

    CANNOT_ENABLE_ONBOARDING_REQUIREMENTS_NOT_MET = 350000
    CANNOT_UPDATE_ONBOARDING_BELOW_REQUIREMENTS = 350001

    FILE_UPLOADS_LIMITED_FOR_GUILD = 400001

    FAILED_TO_BAN_USERS = 500000

    POLL_VOTING_BLOCKED = 520000
    POLL_EXPIRED = 520001
    INVALID_CHANNEL_TYPE_FOR_POLL_CREATION = 520002
    CANNOT_EDIT_POLL_MESSAGE = 520003
    CANNOT_USE_EMOJI_INCLUDED_WITH_POLL = 520004
    CANNOT_EXPIRE_NON_POLL_MESSAGE = 520006

    PROVISIONAL_ACCOUNTS_PERMISSION_NOT_GRANTED = 530000
    ID_TOKEN_JWT_EXPIRED = 530001
    ID_TOKEN_JWT_ISSUER_MISMATCH = 530002
    ID_TOKEN_JWT_AUDIENCE_MISMATCH = 530003
    ID_TOKEN_JWT_ISSUED_TOO_LONG_AGO = 530004
    FAILED_TO_GENERATE_UNIQUE_USERNAME = 530006
    INVALID_CLIENT_SECRET = 530007


def is_interaction(
    source: discord.Interaction | commands.Context,
) -> TypeGuard[discord.Interaction]:
    return isinstance(source, discord.Interaction)


class ErrorContext:
    def __init__(
        self,
        source: discord.Interaction[Bot] | commands.Context[Bot] | None,
        error: Exception,
        user_message: str | None = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        should_log: bool = True,
        should_notify_user: bool = True,
        additional_context: dict[str, Any] | None = None,
    ):
        self.source = source
        self.error = error
        self.user_message = user_message
        self.severity = severity
        self.should_log = should_log
        self.should_notify_user = should_notify_user
        self.additional_context = additional_context or {}

        # Extract common properties (handle None source for service operations)
        if source:
            self.user = (
                source.user
                if isinstance(source, discord.Interaction)
                else source.author
            )
            self.bot = (
                source.client if isinstance(source, discord.Interaction) else source.bot
            )
            self.guild = source.guild
        else:
            self.user = None
            self.bot = None
            self.guild = None


class ResponseBuilder:
    @staticmethod
    def create_error_layout(
        bot: Bot,
        message: str,
        title: str = "### Error",
    ) -> discord.ui.LayoutView:
        layout = ErrorLayout(bot, title, message)

        return layout

    @staticmethod
    def create_success_layout(
        bot: Bot,
        message: str,
        title: str = "## Success",
    ) -> discord.ui.LayoutView:
        layout = SuccessLayout(title, message)

        return layout

    @staticmethod
    def create_warning_embed(
        bot: Bot,
        message: str,
        title: str = "Warning",
        color: discord.Color | None = None,
    ) -> discord.Embed:
        color = color or discord.Color.orange()
        embed = discord.Embed(title=f"{title}", description=message, color=color)
        return embed


class ErrorLogger:
    """Centralized error logging utilities to eliminate duplicate logging patterns."""

    @staticmethod
    def log_error(
        error: Exception,
        context: ErrorContext,
        logger_instance: logging.Logger | None = None,
    ) -> None:
        """Log error with standardized format and context."""
        if not logger_instance:
            logger_instance = logging.getLogger("InterChat")

        # Build context information
        context_info = {
            "user_id": str(context.user.id) if context.user else None,
            "guild_id": str(context.guild.id) if context.guild else None,
            "error_type": type(error).__name__,
            "is_interaction": isinstance(context.source, discord.Interaction),
        }

        # Add command context if available
        if not isinstance(context.source, discord.Interaction) and context.source:
            if context.source.command is not None:
                context_info["command"] = context.source.command.qualified_name
        elif isinstance(context.source, discord.Interaction) and hasattr(
            context.source, "command"
        ):
            context_info["command"] = getattr(
                context.source.command, "qualified_name", "unknown"
            )

        # Add additional context
        context_info.update(context.additional_context)

        # Log based on severity
        if context.severity == ErrorSeverity.CRITICAL:
            logger_instance.critical(
                f"Critical error: {error}", extra=context_info, exc_info=True
            )
        elif context.severity == ErrorSeverity.ERROR:
            logger_instance.error(f"Error: {error}", extra=context_info, exc_info=True)
        elif context.severity == ErrorSeverity.WARNING:
            logger_instance.warning(f"Warning: {error}", extra=context_info)
        else:
            logger_instance.info(f"Info: {error}", extra=context_info)


class ErrorResponseSender:
    """Handles sending error responses to users with consistent patterns."""

    @staticmethod
    async def send_error_response(
        context: ErrorContext,
        response_type: ErrorResponseType = ErrorResponseType.EMBED,
        ephemeral: bool = True,
    ) -> bool:
        """Send error response to user."""
        try:
            if not context.bot:
                return False  # Cannot send response without bot instance

            if response_type == ErrorResponseType.EMBED:
                layout = ResponseBuilder.create_error_layout(
                    context.bot,
                    context.user_message or "An error occurred. Please try again.",
                )
                return await ErrorResponseSender._send_layout_response(
                    context, layout, ephemeral
                )

            elif response_type == ErrorResponseType.TEXT:
                message = f"{context.user_message or 'An error occurred.'}"
                return await ErrorResponseSender._send_text_response(
                    context, message, ephemeral
                )

            return False

        except Exception as send_error:
            try:
                if not context.bot or not context.user:
                    return False
                layout = ResponseBuilder.create_error_layout(
                    context.bot,
                    "I couldn't respond in the channel. Here's the error message.",
                )
                await context.user.send(view=layout)
                return True
            except Exception as exc:
                logger.debug("Failed to DM fallback error response: %s", exc)
                # Ultimate fallback: just log the error
                ErrorLogger.log_error(send_error, context)
                return False

    @staticmethod
    async def _send_embed_response(
        context: ErrorContext, embed: discord.Embed, ephemeral: bool = True
    ) -> bool:
        try:
            if context.source and isinstance(context.source, discord.Interaction):
                if not context.source.response.is_done():
                    await context.source.response.send_message(
                        embed=embed, ephemeral=ephemeral
                    )
                else:
                    await context.source.followup.send(embed=embed, ephemeral=ephemeral)
            elif context.source:
                await context.source.send(embed=embed)
            return True
        except discord.Forbidden:
            try:
                if context.user:
                    await context.user.send(embed=embed)
                    return True
            except Exception as exc:
                logger.debug("Failed to DM fallback embed response: %s", exc)
            return False

    @staticmethod
    async def _send_layout_response(
        context: ErrorContext,
        layout: discord.ui.View | discord.ui.LayoutView,
        ephemeral: bool = True,
    ) -> bool:
        try:
            if context.source and isinstance(context.source, discord.Interaction):
                if not context.source.response.is_done():
                    await context.source.response.send_message(
                        view=layout, ephemeral=ephemeral
                    )
                    if hasattr(layout, "bind_message"):
                        message = await context.source.original_response()
                        layout.bind_message(message)
                else:
                    message = await context.source.followup.send(
                        view=layout, ephemeral=ephemeral
                    )
                    if hasattr(layout, "bind_message"):
                        layout.bind_message(message)
            elif context.source:
                message = await context.source.send(view=layout)
                if hasattr(layout, "bind_message"):
                    layout.bind_message(message)
            return True
        except discord.Forbidden:
            try:
                if context.user:
                    message = await context.user.send(view=layout)
                    if hasattr(layout, "bind_message"):
                        layout.bind_message(message)
                    return True
            except Exception as exc:
                logger.debug("Failed to DM fallback layout response: %s", exc)
            return False

    @staticmethod
    async def _send_text_response(
        context: ErrorContext, message: str, ephemeral: bool = True
    ) -> bool:
        try:
            if context.source and isinstance(context.source, discord.Interaction):
                if not context.source.response.is_done():
                    await context.source.response.send_message(
                        message, ephemeral=ephemeral
                    )
                else:
                    await context.source.followup.send(message, ephemeral=ephemeral)
            elif context.source:
                await context.source.send(message)
            return True
        except discord.Forbidden:
            try:
                if context.user:
                    await context.user.send(message)
                    return True
            except Exception as exc:
                logger.debug("Failed to DM fallback text response: %s", exc)
            return False


class ErrorHandler:
    @staticmethod
    async def handle_error(
        source: discord.Interaction[Bot] | commands.Context[Bot],
        error: Exception,
        user_message: str | None = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        response_type: ErrorResponseType = ErrorResponseType.EMBED,
        should_log: bool = True,
        should_notify_user: bool = True,
        additional_context: dict[str, Any] | None = None,
    ) -> bool:
        context = ErrorContext(
            source=source,
            error=error,
            user_message=user_message,
            severity=severity,
            should_log=should_log,
            should_notify_user=should_notify_user,
            additional_context=additional_context,
        )

        # Log the error if requested
        if should_log:
            ErrorLogger.log_error(error, context)

        # Notify user if requested
        if should_notify_user:
            return await ErrorResponseSender.send_error_response(context, response_type)

        return True


# Convenience functions
async def handle_command_error(
    ctx: commands.Context[Bot], error: Exception, user_message: str | None = None
) -> bool:
    return await ErrorHandler.handle_error(
        source=ctx,
        error=error,
        user_message=user_message,
        response_type=ErrorResponseType.EMBED,
    )


async def handle_interaction_error(
    interaction: discord.Interaction[Bot],
    error: Exception,
    user_message: str | None = None,
    ephemeral: bool = True,
) -> bool:
    """Handle interaction error with standard patterns."""
    return await ErrorHandler.handle_error(
        source=interaction,
        error=error,
        user_message=user_message,
        response_type=ErrorResponseType.EMBED if ephemeral else ErrorResponseType.TEXT,
    )


async def send_error_message(
    source: discord.Interaction[Bot] | commands.Context[Bot],
    message: str,
    title: str = "### Error!",
    ephemeral: bool = True,
) -> bool:
    # Check for suppression flag (e.g. during help command generation)
    if getattr(source, "_suppress_check_errors", False):
        return True

    bot = source.client if isinstance(source, discord.Interaction) else source.bot
    layout = ResponseBuilder.create_error_layout(bot, message, title)
    context = ErrorContext(
        source=source, error=Exception(message), user_message=message
    )
    return await ErrorResponseSender._send_layout_response(context, layout, ephemeral)


async def send_success_message(
    source: discord.Interaction[Bot] | commands.Context[Bot],
    message: str,
    title: str = "## Success!",
    ephemeral: bool = True,
) -> bool:
    bot = source.client if isinstance(source, discord.Interaction) else source.bot
    layout = ResponseBuilder.create_success_layout(bot, message, title)
    context = ErrorContext(
        source=source, error=Exception(message), user_message=message
    )
    return await ErrorResponseSender._send_layout_response(context, layout, ephemeral)
