"""Connection configuration; employee grants belong to agents."""

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.fields import IdentityTimestamps, UUIDText


class ToolConnection(IdentityTimestamps, Base):
    __tablename__ = "tool_connections"
    __table_args__ = (
        CheckConstraint("account_scope IN ('personal','shared')", name="account_scope_valid"),
        CheckConstraint("kind IN ('native','mcp_http','mcp_stdio')", name="kind_valid"),
        CheckConstraint("auth_type IN ('none','bearer','header','env','oauth')", name="auth_valid"),
        CheckConstraint("oauth_storage_revision > 0", name="oauth_revision_positive"),
        CheckConstraint(
            "(auth_type='oauth' AND kind='mcp_http' AND oauth_status IS NOT NULL AND oauth_status IN ('disconnected','connected','reauth_required')) OR (auth_type!='oauth' AND oauth_status IS NULL)",
            name="oauth_state_valid",
        ),
        CheckConstraint(
            "config_revision > 0 AND credential_revision > 0 AND catalog_revision > 0",
            name="revisions_positive",
        ),
    )
    __mapper_args__ = {"polymorphic_on": "kind", "polymorphic_identity": "connection"}

    service_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("mcp_services.id"))
    account_scope: Mapped[str] = mapped_column(Text, default="personal", server_default="personal")
    tool_annotations: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    annotations_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    provider_key: Mapped[str | None] = mapped_column(Text)
    auth_type: Mapped[str] = mapped_column(Text, default="none")
    public_config: Mapped[dict] = mapped_column(JSON, default=dict)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)
    approved_catalog: Mapped[list] = mapped_column(JSON, default=list)
    approved_instructions: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    discovery_candidate: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    enabled: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="enabled_boolean"), default=True
    )
    config_revision: Mapped[int] = mapped_column(Integer, default=1)
    credential_revision: Mapped[int] = mapped_column(Integer, default=1)
    oauth_status: Mapped[str | None] = mapped_column(Text)
    oauth_storage_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    catalog_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("users.id"))


class McpService(IdentityTimestamps, Base):
    """Reusable endpoint definition; credentials and catalogs stay on connections."""

    __tablename__ = "mcp_services"
    __table_args__ = (
        CheckConstraint("transport IN ('http','stdio')", name="transport_valid"),
        CheckConstraint(
            "(transport='http' AND url IS NOT NULL AND command IS NULL) OR (transport='stdio' AND url IS NULL AND command IS NOT NULL)",
            name="transport_definition_valid",
        ),
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(Text, default="http", server_default="http")
    command: Mapped[str | None] = mapped_column(Text)
    args: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    env_keys: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    input_fields: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    owner_user_id: Mapped[str | None] = mapped_column(UUIDText(), ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class HttpConnection(ToolConnection):
    __mapper_args__ = {"polymorphic_identity": "mcp_http"}


class StdioConnection(ToolConnection):
    __mapper_args__ = {"polymorphic_identity": "mcp_stdio"}
