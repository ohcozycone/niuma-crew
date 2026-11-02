"""Durable create intent and cleanup debt survive process failure."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import IdentityTimestamps, UTCDateTime, UUIDText


class SandboxResource(IdentityTimestamps, Base):
    __tablename__ = "sandbox_resources"
    __table_args__ = (
        CheckConstraint(
            "state IN ('requested','ready','cleanup','destroyed','unknown')", name="state_valid"
        ),
    )
    run_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("runs.id"), unique=True)
    deployment_id: Mapped[str] = mapped_column(Text)
    server_identity: Mapped[str] = mapped_column(Text)
    remote_id: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, default="requested")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    cleanup_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
