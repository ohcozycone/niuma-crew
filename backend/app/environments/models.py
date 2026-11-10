from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import IdentityTimestamps, NumericID, UTCDateTime
from app.mcp.models import ToolConnection


class SandboxResource(IdentityTimestamps, Base):
    __tablename__ = "sandbox_resources"
    __table_args__ = (
        CheckConstraint(
            "state IN ('requested','ready','cleanup','destroyed','unknown')", name="state_valid"
        ),
    )
    run_id: Mapped[str] = mapped_column(NumericID(), ForeignKey("runs.id"), unique=True)
    deployment_id: Mapped[str] = mapped_column(Text)
    server_identity: Mapped[str] = mapped_column(Text)
    remote_id: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, default="requested")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    cleanup_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class WorkspaceProfile(ToolConnection):
    """仅保留历史原生连接的 ORM 读取映射，不再提供装配入口。"""

    __mapper_args__ = {"polymorphic_identity": "native"}
