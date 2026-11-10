"""agent_foundations

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_connections",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("provider_key", sa.Text(), nullable=True),
        sa.Column("auth_type", sa.Text(), nullable=False),
        sa.Column("public_config", sa.JSON(), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.Column("approved_catalog", sa.JSON(), nullable=False),
        sa.Column("discovery_candidate", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_revision", sa.Integer(), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("catalog_revision", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Text(), nullable=True),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.Text(),
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.Text(),
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "auth_type IN ('none','bearer','header')", name=op.f("ck_tool_connections_auth_valid")
        ),
        sa.CheckConstraint(
            "kind IN ('native','mcp_http')", name=op.f("ck_tool_connections_kind_valid")
        ),
        sa.CheckConstraint(
            "config_revision > 0 AND credential_revision > 0 AND catalog_revision > 0",
            name=op.f("ck_tool_connections_revisions_positive"),
        ),
        sa.CheckConstraint("enabled IN (0, 1)", name=op.f("ck_tool_connections_enabled_boolean")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_tool_connections_created_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_connections")),
        sa.UniqueConstraint("name", name=op.f("uq_tool_connections_name")),
    )
    op.create_table(
        "agent_tool_grants",
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("tool_connection_id", sa.Text(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("scope_policy", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("granted_by_user_id", sa.Text(), nullable=True),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.Text(),
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.Text(),
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            nullable=False,
        ),
        sa.CheckConstraint("enabled IN (0, 1)", name=op.f("ck_agent_tool_grants_enabled_boolean")),
        sa.CheckConstraint("revision > 0", name=op.f("ck_agent_tool_grants_revision_positive")),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_tool_grants_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.id"],
            name=op.f("fk_agent_tool_grants_granted_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["tool_connection_id"],
            ["tool_connections.id"],
            name=op.f("fk_agent_tool_grants_tool_connection_id_tool_connections"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tool_grants")),
    )
    with op.batch_alter_table("agent_tool_grants", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_agent_tool_grants_agent_id"), ["agent_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_agent_tool_grants_tool_connection_id"),
            ["tool_connection_id"],
            unique=False,
        )
        batch_op.create_index(
            "uq_agent_tool_grants_connection", ["agent_id", "tool_connection_id"], unique=True
        )

    op.create_table(
        "sandbox_resources",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("deployment_id", sa.Text(), nullable=False),
        sa.Column("server_identity", sa.Text(), nullable=False),
        sa.Column("remote_id", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("cleanup_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.Text(),
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.Text(),
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('requested','ready','cleanup','destroyed','unknown')",
            name=op.f("ck_sandbox_resources_state_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_sandbox_resources_run_id_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sandbox_resources")),
        sa.UniqueConstraint("run_id", name=op.f("uq_sandbox_resources_run_id")),
    )
    op.create_table(
        "stored_files",
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("origin_run_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.Text(),
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.Text(),
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('input','source','output')", name=op.f("ck_stored_files_purpose_valid")
        ),
        sa.CheckConstraint("size >= 0", name=op.f("ck_stored_files_size_nonnegative")),
        sa.ForeignKeyConstraint(
            ["origin_run_id"], ["runs.id"], name=op.f("fk_stored_files_origin_run_id_runs")
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name=op.f("fk_stored_files_owner_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_files")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_stored_files_storage_key")),
    )
    with op.batch_alter_table("stored_files", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stored_files_origin_run_id"), ["origin_run_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_stored_files_owner_user_id"), ["owner_user_id"], unique=False
        )

    op.create_table(
        "message_files",
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id"], ["stored_files.id"], name=op.f("fk_message_files_file_id_stored_files")
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name=op.f("fk_message_files_message_id_messages")
        ),
        sa.PrimaryKeyConstraint("message_id", "file_id", name=op.f("pk_message_files")),
    )
    op.add_column(
        "run_actions", sa.Column("result_payload", sa.JSON(none_as_null=True), nullable=True)
    )
    op.add_column("runs", sa.Column("tool_calls", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("tool_calls")

    with op.batch_alter_table("run_actions", schema=None) as batch_op:
        batch_op.drop_column("result_payload")

    op.drop_table("message_files")
    with op.batch_alter_table("stored_files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stored_files_owner_user_id"))
        batch_op.drop_index(batch_op.f("ix_stored_files_origin_run_id"))

    op.drop_table("stored_files")
    op.drop_table("sandbox_resources")
    with op.batch_alter_table("agent_tool_grants", schema=None) as batch_op:
        batch_op.drop_index("uq_agent_tool_grants_connection")
        batch_op.drop_index(batch_op.f("ix_agent_tool_grants_tool_connection_id"))
        batch_op.drop_index(batch_op.f("ix_agent_tool_grants_agent_id"))

    op.drop_table("agent_tool_grants")
    op.drop_table("tool_connections")
