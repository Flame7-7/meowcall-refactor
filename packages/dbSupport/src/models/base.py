import enum

from cuid2 import Cuid
from sqlalchemy import Enum
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(MappedAsDataclass, DeclarativeBase):
    pass


cuid = Cuid()


class MessageStatus(enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"


MessageStatusEnum = Enum(MessageStatus, name="MessageStatus", create_type=True)


class UserphoneCallStatus(enum.Enum):
    WAITING = "WAITING"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


UserphoneCallStatusEnum = Enum(
    UserphoneCallStatus, name="UserphoneCallStatus", create_type=True
)


class InfractionStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    APPEALED = "APPEALED"


InfractionStatusEnum = Enum(InfractionStatus, name="InfractionStatus", create_type=True)


class AppealStatus(enum.Enum):
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    ACCEPTED = "ACCEPTED"


AppealStatusEnum = Enum(AppealStatus, name="AppealStatus", create_type=True)


class ReportStatus(enum.Enum):
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


ReportStatusEnum = Enum(ReportStatus, name="ReportStatus", create_type=True)

# Type Enums


class InfractionType(enum.Enum):
    BAN = "BAN"
    MUTE = "MUTE"
    WARNING = "WARNING"


InfractionTypeEnum = Enum(InfractionType, name="InfractionType", create_type=True)

# Data Enums


class Badges(enum.Enum):
    DEVELOPER = "DEVELOPER"
    STAFF = "STAFF"
    PREMIUM = "PREMIUM"
    VOTER = "VOTER"


BadgesEnum = Enum(Badges, name="Badges", create_type=True)
