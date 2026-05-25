from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    sql,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import (
    Base,
    MessageStatus,
    MessageStatusEnum,
    cuid,
)

if TYPE_CHECKING:
    from .messages import Message


class Message(Base):
    __tablename__ = "Message"

    # Primary Fields
    id: Mapped[str] = mapped_column(Text(), primary_key=True)  # Discord Snowflake ❄️
    content: Mapped[str] = mapped_column(
        String(4000)
    )  # Discord limits at 2000 but format innit guys
    guildId: Mapped[str] = mapped_column(Text())  # FK to server (?)
    channelId: Mapped[str] = mapped_column(Text())
    authorId: Mapped[str] = mapped_column(Text())  # FK to User (?)
    status: Mapped[MessageStatus] = mapped_column(
        MessageStatusEnum,
        nullable=False,
        server_default=MessageStatus.ACTIVE.value,
        default=MessageStatus.ACTIVE,
    )

    # Optional Content
    referredMessageId: Mapped[str | None] = mapped_column(
        ForeignKey("Message.id"), init=False
    )
    imagesUrl: Mapped[list[str] | None] = mapped_column(
        ARRAY(String()), default=None, server_default=sql.null()
    )

    # Relationships
    reactions: Mapped[list["MessageReaction"]] = relationship(
        "MessageReaction",
        back_populates="message",
        lazy="noload",
        cascade="all, delete-orphan",
        init=False,
    )

    # Timestamps
    deletionQueuedAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), default=None, init=False
    )
    retentionUntil: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
    createdAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updatedAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )

    # Indexes
    __table_args__ = (
        Index("Message_referredMesasageId_idx", "referredMessageId"),
        Index("Message_createdAt_idx", text('"createdAt" DESC')),
        Index("Message_guildId_authorId_idx", "guildId", "authorId"),
        Index("Message_status_createdAt_idx", "status", text('"createdAt" DESC')),
    )


class MessageReaction(Base):
    __tablename__ = "MessageReaction"

    # Primary Fields
    id: Mapped[str] = mapped_column(
        primary_key=True, insert_default=lambda: cuid.generate(), init=False
    )
    messageId: Mapped[str] = mapped_column(
        Text(), ForeignKey("Message.id", ondelete="CASCADE"), nullable=False
    )
    emoji: Mapped[str] = mapped_column(String(64), nullable=False)
    users: Mapped[list[str]] = dataclass_field(
        default_factory=list,
        metadata={"sa": mapped_column(ARRAY(Text()), insert_default=list)},
    )

    # Relationships
    message: Mapped[Message] = relationship(
        "Message", back_populates="reactions", lazy="noload", init=False
    )

    # Indexes
    __table_args__ = ((UniqueConstraint("messageId", "emoji")),)
