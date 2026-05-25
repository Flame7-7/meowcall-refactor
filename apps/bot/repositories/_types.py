from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Required, TypedDict

if TYPE_CHECKING:
    from models.base import (
        AppealStatus,
        Badges,
        InfractionStatus,
        MessageStatus,
        ReportStatus,
        UserphoneCallStatus,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Connection
# ═══════════════════════════════════════════════════════════════════════════


class _ConnectionCreateRequired(TypedDict):
    """Required Connection fields not in ``ConnectionRepository.create``."""

    webhookURL: str


class ConnectionCreateKwargs(_ConnectionCreateRequired, total=False):
    """Remaining kwargs for ``ConnectionRepository.create``."""

    parentId: str | None
    lastActive: datetime | None


class ConnectionUpdateKwargs(TypedDict, total=False):
    """Mutable Connection columns for ``update`` / ``update_by_id``."""

    webhookURL: str
    parentId: str | None
    lastActive: datetime | None


# ═══════════════════════════════════════════════════════════════════════════
# User  (create already passes: user_id)
# ═══════════════════════════════════════════════════════════════════════════


class UserCreateKwargs(TypedDict, total=False):
    """Constructor fields for ``UserRepository.create`` (user_id is explicit).

    All User constructor fields (except id) that have defaults.
    """

    name: str | None
    image: str | None
    useServerNickname: bool
    useServerProfile: bool
    useAutoTranslate: bool
    hideBadges: bool
    voteCount: int
    messageCount: int
    callCount: int
    locale: str
    badges: list[Badges]
    lastVoted: datetime | None
    lastMessageAt: datetime | None


class UserUpdateKwargs(TypedDict, total=False):
    """Mutable User columns for ``update`` / ``upsert``."""

    name: str | None
    image: str | None
    useServerNickname: bool
    useServerProfile: bool
    useAutoTranslate: bool
    hideBadges: bool
    voteCount: int
    messageCount: int
    callCount: int
    locale: str
    badges: list[Badges]
    lastVoted: datetime | None
    lastMessageAt: datetime | None


# ═══════════════════════════════════════════════════════════════════════════
# ServerData  (create already passes: server_id)
# ═══════════════════════════════════════════════════════════════════════════


class _ServerDataRequired(TypedDict):
    """Required ServerData fields not in ``ServerRepository.create``."""

    name: str


class ServerDataCreateKwargs(_ServerDataRequired, total=False):
    """Remaining kwargs for ``ServerRepository.create``."""

    iconUrl: str | None


class ServerDataUpdateKwargs(TypedDict, total=False):
    """Mutable ServerData columns for ``update`` / ``upsert``."""

    name: str
    iconUrl: str | None


# ═══════════════════════════════════════════════════════════════════════════
# Message   (create already passes: author_id, call_id, server_id)
# ═══════════════════════════════════════════════════════════════════════════


class _MessageCreateRequired(TypedDict):
    """Required fields not in ``MessageRepository.create``."""

    id: str
    content: str
    channelId: str


class MessageCreateKwargs(_MessageCreateRequired, total=False):
    """Remaining kwargs for ``MessageRepository.create``."""

    imagesUrl: list[str] | None
    referredMessageId: str | None
    status: MessageStatus


# ═══════════════════════════════════════════════════════════════════════════
# Infraction  (create_infraction already passes: moderator_id,
#             type, reason, user_id, server_id)
# ═══════════════════════════════════════════════════════════════════════════


class InfractionCreateKwargs(TypedDict, total=False):
    """Remaining kwargs for ``ModerationRepository.create_infraction``."""

    expiresAt: datetime | None
    serverName: str | None
    status: InfractionStatus
    notified: bool


# ═══════════════════════════════════════════════════════════════════════════
# Appeal  (create_appeal already passes: infraction_id, user_id, reason)
# ═══════════════════════════════════════════════════════════════════════════


class AppealCreateKwargs(TypedDict, total=False):
    """Remaining kwargs for ``ModerationRepository.create_appeal``."""

    status: AppealStatus


# ═══════════════════════════════════════════════════════════════════════════
# Report  (create_report has no explicit params)
# ═══════════════════════════════════════════════════════════════════════════


class ReportCreateKwargs(TypedDict, total=False):
    """All constructor fields for ``ReportRepository.create_report``."""

    reporterUserId: Required[str]
    reportedUserId: Required[str]
    reportedServerId: Required[str]
    reason: Required[str]
    messageId: str | None
    resolvedBy: str | None
    resolvedAt: datetime | None
    status: ReportStatus
    reportMessageId: str | None
    reportChannelId: str | None
    actionTaken: str | None


# ═══════════════════════════════════════════════════════════════════════════
# UserphoneCall  (create_report has no explicit params)
# ═══════════════════════════════════════════════════════════════════════════


class UserphoneCallCreateKwargs(TypedDict, total=False):
    """All constructor fields for ``UserphoneRepository.create_call``."""

    channelId: Required[str]
    guildId: Required[str]
    userId: Required[str]
    pairedCallId: str | None
    status: UserphoneCallStatus
    endedAt: datetime | None
