"""The deployment-wide, current organization rules."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import UTC_TIMESTAMP_DEFAULT, UTCDateTime


class OrganizationRules(Base):
    __tablename__ = "organization_rules"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("revision >= 0", name="revision_valid"),
        CheckConstraint("length(instructions) <= 20000", name="instructions_length"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    instructions: Mapped[str] = mapped_column(Text, server_default=text("''"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT
    )
