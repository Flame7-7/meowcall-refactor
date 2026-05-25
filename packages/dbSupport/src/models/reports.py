from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func, sql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ReportStatus, ReportStatusEnum, cuid

if TYPE_CHECKING:
    from .servers import ServerData
    from .users import User


class Report(Base):
    __tablename__ = "Report"

    # Primary Fields
    id: Mapped[str] = mapped_column(
        Text(), primary_key=True, insert_default=lambda: cuid.generate(10), init=False
    )
    reporterUserId: Mapped[str] = mapped_column(
        Text(), ForeignKey("User.id"), nullable=False
    )
    reportedUserId: Mapped[str] = mapped_column(
        Text(), ForeignKey("User.id"), nullable=False
    )
    reportedServerId: Mapped[str] = mapped_column(
        Text(), ForeignKey("ServerData.id"), nullable=False
    )
    # messageId: Mapped[str | None] = mapped_column(Text(), nullable=True, default=None, server_default=sql.null())
    reason: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        ReportStatusEnum,
        nullable=False,
        server_default=ReportStatus.PENDING.value,
        default=ReportStatus.PENDING,
    )

    messageId: Mapped[str | None] = mapped_column(
        Text(), nullable=True, default=None, server_default=sql.null()
    )
    actionTaken: Mapped[str] = mapped_column(Text(), nullable=True, default=None)
    resolvedBy: Mapped[str] = mapped_column(
        Text(),
        ForeignKey("User.id"),
        nullable=True,
        default=None,
        server_default=sql.null(),
    )

    # Relationships
    reportedUser: Mapped[User] = relationship(
        "User",
        foreign_keys=[reportedUserId],
        back_populates="reportsReceived",
        lazy="noload",
        init=False,
    )
    reporter: Mapped[User] = relationship(
        "User",
        foreign_keys=[reporterUserId],
        back_populates="reportsSubmit",
        lazy="noload",
        init=False,
    )
    reportedServer: Mapped[ServerData] = relationship(
        "ServerData",
        foreign_keys=[reportedServerId],
        back_populates="reports",
        lazy="noload",
        init=False,
    )
    moderator: Mapped[User] = relationship(
        "User",
        foreign_keys=[resolvedBy],
        back_populates="reportsHandeled",
        lazy="noload",
        init=False,
    )

    # Persistence Data
    reportMessageId: Mapped[str] = mapped_column(
        Text(), nullable=True, default=None, server_default=sql.null()
    )
    reportChannelId: Mapped[str] = mapped_column(
        Text(), nullable=True, default=None, server_default=sql.null()
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
    resolvedAt: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), server_default=sql.null(), init=False
    )
