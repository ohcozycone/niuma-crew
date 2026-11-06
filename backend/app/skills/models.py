"""Persist the current definition of a reusable skill."""

from sqlalchemy import JSON, Boolean, CheckConstraint, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import IdentityTimestamps
from app.values import required_text


class Skill(IdentityTimestamps, Base):
    __tablename__ = "skills"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)

    revision: Mapped[int] = mapped_column(
        Integer, CheckConstraint("revision > 0", name="revision_positive"), server_default="1"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="is_active_boolean"), server_default="1"
    )
    configuration_schema: Mapped[dict] = mapped_column(
        JSON,
        CheckConstraint(
            "json_valid(configuration_schema) AND json_type(configuration_schema) = 'object'",
            name="configuration_schema_object",
        ),
        default=dict,
        server_default="{}",
    )
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, server_default="其他")
    description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    instructions: Mapped[str] = mapped_column(Text, server_default=text("''"))
    input_description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    output_description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    example: Mapped[str] = mapped_column(Text, server_default=text("''"))
    skill_md: Mapped[str] = mapped_column(Text, server_default=text("''"))
    source_path: Mapped[str | None] = mapped_column(Text, unique=True, index=True, nullable=True)
    package_manifest: Mapped[list] = mapped_column(
        JSON,
        CheckConstraint(
            "json_valid(package_manifest) AND json_type(package_manifest) = 'array'",
            name="package_manifest_array",
        ),
        default=list,
        server_default="[]",
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        return required_text(value)
