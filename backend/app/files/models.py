"""Immutable bytes are outside SQLite; references remain application controlled."""

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import IdentityTimestamps, NumericID, UUIDText


class StoredFile(IdentityTimestamps, Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint("size >= 0", name="size_nonnegative"),
        CheckConstraint("purpose IN ('input','source','output','evidence')", name="purpose_valid"),
    )
    owner_user_id: Mapped[str] = mapped_column(UUIDText(), ForeignKey("users.id"), index=True)
    origin_run_id: Mapped[str | None] = mapped_column(
        NumericID(), ForeignKey("runs.id"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    purpose: Mapped[str] = mapped_column(Text)
