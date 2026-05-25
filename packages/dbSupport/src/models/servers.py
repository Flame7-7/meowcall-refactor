from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    sql,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, cuid

if TYPE_CHECKING:
    from .moderation import Blacklist, Infraction, Appeal
    from .reports import Report


class Connection(Base):
    __tablename__ = "Connection"

    # Primary fields
    id: Mapped[str] = mapped_column(
        Text(), primary_key=True, insert_default=lambda: cuid.generate(), init=False
    )
    channelId: Mapped[str] = mapped_column(Text(), unique=True, nullable=False)
    webhookURL: Mapped[str] = mapped_column(Text())
    serverId: Mapped[str] = mapped_column(Text(), ForeignKey("ServerData.id"))

    # Timestamps
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    lastUpdated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )
    lastActive: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Thread Support
    parentId: Mapped[str | None] = mapped_column(
        Text(), default=None, server_default=sql.null()
    )

    # Relationships

    server: Mapped["ServerData"] = relationship(
        "ServerData", back_populates="connections", lazy="noload", init=False
    )

    # Indexes
    __table_args__ = (
        UniqueConstraint("channelId", "serverId"),
        Index("Connection_serverId_idx", "serverId"),
        Index("Connection_lastActive_idx", "lastActive"),
        Index("Connection_channelId_idx", "channelId"),
    )


class ServerData(Base):
    __tablename__ = "ServerData"

    # Primary Fields
    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    name: Mapped[str] = mapped_column(Text())

    # Relationships

    connections: Mapped[list[Connection]] = relationship(
        "Connection", back_populates="server", lazy="noload", init=False
    )
    infractions: Mapped[list[Infraction]] = relationship(
        "Infraction", back_populates="server", lazy="noload", init=False
    )
    appeals: Mapped[list["Appeal"]] = relationship(
        "Appeal",
        back_populates="server",
        lazy="noload",
        init=False,
    )
    blacklists: Mapped[list[Blacklist]] = relationship(
        "Blacklist", back_populates="server", lazy="noload", init=False
    )
    reports: Mapped[list[Report]] = relationship(
        "Report", back_populates="reportedServer", lazy="noload", init=False
    )

    iconUrl: Mapped[str | None] = mapped_column(
        Text(), default=None, server_default=sql.null()
    )

    customPrefix: Mapped[str | None] = mapped_column(
        Text(), default=None, server_default=sql.null()
    )

    # Timestamps
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), init=False
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        init=False,
    )
