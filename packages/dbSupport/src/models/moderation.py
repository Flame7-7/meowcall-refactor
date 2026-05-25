from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, sql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import (
    AppealStatus,
    AppealStatusEnum,
    Base,
    InfractionStatus,
    InfractionStatusEnum,
    InfractionType,
    InfractionTypeEnum,
    cuid,
)

if TYPE_CHECKING:
    from .servers import ServerData
    from .users import User


class Infraction(Base):
    __tablename__ = "Infraction"

    # Primary Fields
    id: Mapped[str] = mapped_column(
        Text(), primary_key=True, insert_default=lambda: cuid.generate(10), init=False
    )
    moderatorId: Mapped[str] = mapped_column(
        Text(), ForeignKey("User.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500))
    expiresAt: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    type: Mapped[InfractionType] = mapped_column(InfractionTypeEnum, nullable=False)

    # User
    userId: Mapped[str | None] = mapped_column(Text(), ForeignKey("User.id"))

    # Server
    serverId: Mapped[str | None] = mapped_column(Text(), ForeignKey("ServerData.id"))
    serverName: Mapped[str | None] = mapped_column(Text())

    # Flags
    status: Mapped[InfractionStatus] = mapped_column(
        InfractionStatusEnum,
        default=InfractionStatus.ACTIVE,
        server_default=InfractionStatus.ACTIVE.value,
    )
    notified: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=sql.false()
    )

    # Associated Report
    # ...

    # Evidence
    # Add evidence based transcripts? Not sure how, maybe can do some website magic idk guys

    # Relationships
    moderator: Mapped[User] = relationship(
        "User",
        foreign_keys=[moderatorId],
        back_populates="issuedInfracttions",
        lazy="noload",
        init=False,
    )
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[userId],
        back_populates="infractions",
        lazy="noload",
        init=False,
    )
    appeals: Mapped[list["Appeal"]] = relationship(
        "Appeal",
        back_populates="infraction",
        lazy="noload",
        init=False,
    )
    server: Mapped[ServerData] = relationship(
        "ServerData", back_populates="infractions", lazy="noload", init=False
    )

    # Timestamps
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
        Index(
            "Infraction_user_active_idx",
            "userId",
            "type",
            "expiresAt",
            postgresql_where=sql.column("status") == "ACTIVE",
        ),
        Index(
            "Infraction_server_active_idx",
            "serverId",
            "type",
            "expiresAt",
            postgresql_where=sql.column("status") == "ACTIVE",
        ),
    )


class Appeal(Base):
    __tablename__ = "Appeal"

    id: Mapped[str] = mapped_column(
        Text(), primary_key=True, insert_default=lambda: cuid.generate(), init=False
    )
    infractionId: Mapped[str] = mapped_column(
        Text(), ForeignKey("Infraction.id"), nullable=False
    )

    # User
    userId: Mapped[str | None] = mapped_column(Text(), ForeignKey("User.id"))

    # Server
    serverId: Mapped[str | None] = mapped_column(Text(), ForeignKey("ServerData.id"))
    serverName: Mapped[str | None] = mapped_column(Text())

    # Flags
    status: Mapped[AppealStatus] = mapped_column(
        AppealStatusEnum,
        default=AppealStatus.PENDING,
        server_default=AppealStatus.PENDING.value,
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[userId],
        back_populates="appeals",
        lazy="noload",
        init=False,
    )

    server: Mapped[ServerData] = relationship(
        "ServerData",
        foreign_keys=[serverId],
        back_populates="appeals",
        lazy="noload",
        init=False,
    )

    infraction: Mapped[Infraction] = relationship(
        "Infraction",
        foreign_keys=[infractionId],
        back_populates="appeals",
        lazy="noload",
        init=False,
    )

    # Timestamps
    createdAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updatedAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )
    expiresAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), default=None, server_default=sql.null()
    )


class Blacklist(Base):
    __tablename__ = "Blacklist"

    # Primary Fields
    id: Mapped[str] = mapped_column(
        Text(), primary_key=True, insert_default=lambda: cuid.generate(), init=False
    )
    moderatorId: Mapped[str] = mapped_column(
        Text(), ForeignKey("User.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500))

    # User
    userId: Mapped[str | None] = mapped_column(Text(), ForeignKey("User.id"))

    # Server
    serverId: Mapped[str | None] = mapped_column(Text(), ForeignKey("ServerData.id"))
    serverName: Mapped[str | None] = mapped_column(Text())

    # Flags
    status: Mapped[InfractionStatus] = mapped_column(
        InfractionStatusEnum,
        default=InfractionStatus.ACTIVE,
        server_default=InfractionStatus.ACTIVE.value,
    )
    notified: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=sql.false()
    )

    # Relationships
    moderator: Mapped[User] = relationship(
        "User",
        foreign_keys=[moderatorId],
        back_populates="issuedBlacklists",
        lazy="noload",
        init=False,
    )
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[userId],
        back_populates="blacklists",
        lazy="noload",
        init=False,
    )
    server: Mapped[ServerData] = relationship(
        "ServerData", back_populates="blacklists", lazy="noload", init=False
    )

    # Timestamps
    createdAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updatedAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )
    expiresAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), default=None, server_default=sql.null()
    )

    # Indexes
    __table_args__ = (
        Index(
            "Blacklist_user_active_idx",
            "userId",
            "expiresAt",
            postgresql_where=sql.column("status") == "ACTIVE",
        ),
        Index(
            "Blacklist_server_active_idx",
            "serverId",
            "expiresAt",
            postgresql_where=sql.column("status") == "ACTIVE",
        ),
    )
