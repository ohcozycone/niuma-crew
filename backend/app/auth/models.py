"""Users and opaque server-side sessions. No credentials in business tables."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import (
    UTC_TIMESTAMP_DEFAULT,
    IdentityTimestamps,
    UTCDateTime,
    UUIDText,
)
from app.values import new_uuid


class User(IdentityTimestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(trim(username)) > 0", name="username_not_blank"),
        CheckConstraint("role IN ('admin', 'member')", name="role_valid"),
        CheckConstraint(
            "(role = 'admin' AND password_hash IS NOT NULL) OR "
            "(role = 'member' AND password_hash IS NULL)",
            name="credential_valid",
        ),
        Index(
            "uq_users_admin_username", "username", unique=True, sqlite_where=text("role = 'admin'")
        ),
    )
    username: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="is_active_boolean"), server_default=text("1")
    )


class ExternalIdentity(IdentityTimestamps, Base):
    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id"),
        UniqueConstraint("user_id", "provider"),
        CheckConstraint("provider = 'github'", name="provider_valid"),
        CheckConstraint("length(trim(provider_user_id)) > 0", name="subject_not_blank"),
    )
    user_id: Mapped[str] = mapped_column(
        UUIDText(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(Text)
    provider_user_id: Mapped[str] = mapped_column(Text)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'user' AND user_id IS NOT NULL) OR (kind = 'guest' AND user_id IS NULL)",
            name="identity_valid",
        ),
        CheckConstraint("expires_at > created_at", name="expiry_valid"),
    )
    id: Mapped[str] = mapped_column(UUIDText(), primary_key=True, default=new_uuid)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str | None] = mapped_column(
        UUIDText(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
