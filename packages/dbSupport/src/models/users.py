from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    sql,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Badges, BadgesEnum, Base, cuid

if TYPE_CHECKING:
    from .moderation import Appeal, Blacklist, Infraction
    from .reports import Report


class User(Base):
    __tablename__ = "User"

    # Primary Fields
    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    name: Mapped[str | None] = mapped_column(Text())
    image: Mapped[str | None] = mapped_column(Text())

    # Relationships
    infractions: Mapped[ARRAY[Infraction]] = relationship(
        "Infraction",
        foreign_keys="Infraction.userId",
        back_populates="user",
        lazy="noload",
        init=False,
    )
    issuedInfracttions: Mapped[ARRAY[Infraction]] = relationship(
        "Infraction",
        foreign_keys="Infraction.moderatorId",
        back_populates="moderator",
        lazy="noload",
        init=False,
    )
    appeals: Mapped[list["Appeal"]] = relationship(
        "Appeal",
        foreign_keys="Appeal.userId",
        back_populates="user",
        lazy="noload",
        init=False,
    )
    blacklists: Mapped[ARRAY[Blacklist]] = relationship(
        "Blacklist",
        foreign_keys="Blacklist.userId",
        back_populates="user",
        lazy="noload",
        init=False,
    )
    issuedBlacklists: Mapped[ARRAY[Blacklist]] = relationship(
        "Blacklist",
        foreign_keys="Blacklist.moderatorId",
        back_populates="moderator",
        lazy="noload",
        init=False,
    )
    reportsSubmit: Mapped[ARRAY[Report]] = relationship(
        "Report",
        foreign_keys="Report.reporterUserId",
        back_populates="reporter",
        lazy="noload",
        init=False,
    )
    reportsReceived: Mapped[ARRAY[Report]] = relationship(
        "Report",
        foreign_keys="Report.reportedUserId",
        back_populates="reportedUser",
        lazy="noload",
        init=False,
    )
    reportsHandeled: Mapped[ARRAY[Report]] = relationship(
        "Report",
        foreign_keys="Report.resolvedBy",
        back_populates="moderator",
        lazy="noload",
        init=False,
    )
    accounts: Mapped[list["Account"]] = relationship(
        "Account",
        back_populates="user",
        lazy="noload",
        init=False,
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="user",
        lazy="noload",
        init=False,
    )

    # Boolean Flags
    useServerNickname: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=sql.false()
    )
    useServerProfile: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=sql.false()
    )
    useAutoTranslate: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=sql.false()
    )
    hideBadges: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=sql.false()
    )

    # Numeric Fields
    voteCount: Mapped[int] = mapped_column(
        Integer(), default=0, server_default=text("0")
    )
    messageCount: Mapped[int] = mapped_column(
        Integer(), default=0, server_default=text("0")
    )
    callCount: Mapped[int] = mapped_column(
        Integer(), default=0, server_default=text("0")
    )

    # Data
    locale: Mapped[str | None] = mapped_column(Text(), default="en")
    badges: Mapped[list[Badges]] = mapped_column(
        ARRAY(BadgesEnum), default=list, server_default=text("'{}'::\"Badges\"[]")
    )

    # Timestamps
    lastVoted: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, server_default=sql.null()
    )
    lastMessageAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, server_default=sql.null()
    )
    createdAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updatedAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )

    # Indexes
    __table_args__ = (
        Index("User_voteCount_idx", "voteCount"),
        Index("User_lastVoted_idx", "lastVoted"),
        Index("User_messageCount_idx", "messageCount"),
    )


class Account(Base):
    __tablename__ = "Account"

    id: Mapped[str] = mapped_column(
        Text(), primary_key=True, insert_default=lambda: cuid.generate(), init=False
    )
    accountId: Mapped[str] = mapped_column(Text(), nullable=False)
    providerId: Mapped[str] = mapped_column(Text(), nullable=False)
    userId: Mapped[str] = mapped_column(
        Text(), ForeignKey("User.id", ondelete="CASCADE"), nullable=False
    )
    user: Mapped[User] = relationship("User", back_populates="accounts")
    accessToken: Mapped[str | None] = mapped_column(Text(), nullable=True)
    refreshToken: Mapped[str | None] = mapped_column(Text(), nullable=True)
    idToken: Mapped[str | None] = mapped_column(Text(), nullable=True)
    accessTokenExpiresAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refreshTokenExpiresAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scope: Mapped[str | None] = mapped_column(Text(), nullable=True)
    password: Mapped[str | None] = mapped_column(Text(), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Session(Base):
    __tablename__ = "Session"

    id: Mapped[str] = mapped_column(
        Text(), primary_key=True, insert_default=lambda: cuid.generate(), init=False
    )
    expiresAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token: Mapped[str] = mapped_column(Text(), unique=True, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    ipAddress: Mapped[str | None] = mapped_column(Text(), nullable=True)
    userAgent: Mapped[str | None] = mapped_column(Text(), nullable=True)
    userId: Mapped[str] = mapped_column(
        Text(), ForeignKey("User.id", ondelete="CASCADE"), nullable=False
    )
    user: Mapped[User] = relationship("User", back_populates="sessions")
