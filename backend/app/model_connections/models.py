"""Persistent connections contain encrypted credentials, never agent instructions."""

from sqlalchemy import Boolean, CheckConstraint, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import IdentityTimestamps


class ModelConnection(IdentityTimestamps, Base):
    __tablename__ = "model_connections"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(model_id)) > 0", name="model_id_not_blank"),
        CheckConstraint("length(encrypted_api_key) > 0", name="credential_not_blank"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="enabled_boolean"), server_default="1"
    )
    capability: Mapped[str] = mapped_column(
        Text,
        CheckConstraint("capability IN ('chat', 'embedding')", name="capability_valid"),
        server_default="chat",
    )
    config_revision: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("config_revision > 0", name="config_revision_positive"),
        server_default="1",
    )
    credential_revision: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("credential_revision > 0", name="credential_revision_positive"),
        server_default="1",
    )
    name: Mapped[str] = mapped_column(Text, unique=True)
    preset_id: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(Text)
    encrypted_api_key: Mapped[str] = mapped_column(Text)
