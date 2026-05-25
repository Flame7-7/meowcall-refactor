from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    sql,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UserphoneCallStatus, UserphoneCallStatusEnum, cuid

if TYPE_CHECKING:
    from .users import User


class UserphoneCall(Base):
    __tablename__ = "UserphoneCall"

    # Primary Fields
    id: Mapped[str] = mapped_column(
        Text(), primary_key=True, insert_default=lambda: cuid.generate(), init=False
    )

    # Ownership
    channelId: Mapped[str] = mapped_column(Text(), nullable=False)
    guildId: Mapped[str] = mapped_column(Text(), nullable=False)
    userId: Mapped[str] = mapped_column(Text(), ForeignKey("User.id"), nullable=False)

    # Attachment
    pairedCallId: Mapped[str | None] = mapped_column(
        Text(),
        ForeignKey("UserphoneCall.id"),
        nullable=True,
        default=None,
        server_default=sql.null(),
    )

    # Status
    status: Mapped[UserphoneCallStatus] = mapped_column(
        UserphoneCallStatusEnum,
        nullable=False,
        default=UserphoneCallStatus.WAITING,
        server_default=UserphoneCallStatus.WAITING.value,
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User", foreign_keys=[userId], lazy="noload", init=False
    )
    pairedCall: Mapped["UserphoneCall | None"] = relationship(
        "UserphoneCall",
        foreign_keys=[pairedCallId],
        remote_side="UserphoneCall.id",
        lazy="noload",
        init=False,
    )

    # Timestamps
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updatedAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )
    endedAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, server_default=sql.null()
    )

    __table_args__ = (
        Index("UserphoneCall_channelId_idx", "channelId"),
        Index("UserphoneCall_userId_idx", "userId"),
        Index("UserphoneCall_status_idx", "status"),
        Index("UserphoneCall_status_createdAt_idx", "status", "createdAt"),
    )
