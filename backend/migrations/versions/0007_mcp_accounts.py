"""MCP definitions, explicit account scopes and personal usage bindings."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = depends_on = None


def connection_baseline():
    # Frozen 0006 table definition for offline SQL generation; never import live ORM.
    metadata = sa.MetaData()
    return sa.Table(
        "tool_connections",
        metadata,
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("provider_key", sa.Text()),
        sa.Column("auth_type", sa.Text(), nullable=False),
        sa.Column("public_config", sa.JSON(), nullable=False),
        sa.Column("encrypted_credentials", sa.Text()),
        sa.Column("approved_catalog", sa.JSON(), nullable=False),
        sa.Column("discovery_candidate", sa.JSON(none_as_null=True)),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *[
            sa.Column(key, sa.Integer(), nullable=False)
            for key in ("config_revision", "credential_revision", "catalog_revision")
        ],
        sa.Column("created_by_user_id", sa.Text()),
        sa.Column("id", sa.Text(), primary_key=True),
        *[
            sa.Column(
                key,
                sa.Text(),
                nullable=False,
                server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            )
            for key in ("created_at", "updated_at")
        ],
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_tool_connections_created_by_user_id_users",
        ),
        sa.UniqueConstraint("name", name="uq_tool_connections_name"),
        sa.CheckConstraint("kind IN ('native','mcp_http')", name="ck_tool_connections_kind_valid"),
        sa.CheckConstraint(
            "auth_type IN ('none','bearer','header')", name="ck_tool_connections_auth_valid"
        ),
        sa.CheckConstraint(
            "config_revision > 0 AND credential_revision > 0 AND catalog_revision > 0",
            name="ck_tool_connections_revisions_positive",
        ),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_tool_connections_enabled_boolean"),
    )


def upgrade():
    op.create_table(
        "mcp_services",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Text(), sa.ForeignKey("users.id")),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
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
    )
    with op.batch_alter_table(
        "tool_connections", copy_from=connection_baseline() if op.get_context().as_sql else None
    ) as batch:
        batch.add_column(sa.Column("service_id", sa.Text()))
        batch.add_column(
            sa.Column("account_scope", sa.Text(), nullable=False, server_default="personal")
        )
        batch.add_column(
            sa.Column("tool_annotations", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("annotations_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch.create_foreign_key(
            "fk_tool_connections_service_id_mcp_services", "mcp_services", ["service_id"], ["id"]
        )
        batch.create_check_constraint(
            "account_scope_valid", "account_scope IN ('personal','shared')"
        )
        batch.drop_constraint("uq_tool_connections_name", type_="unique")
    op.execute("UPDATE tool_connections SET account_scope='shared' WHERE kind='native'")
    op.execute(
        "INSERT INTO mcp_services (id,name,description,url,owner_user_id,revision,enabled,created_at,updated_at) SELECT id,name,'',json_extract(public_config,'$.url'),created_by_user_id,1,enabled,created_at,updated_at FROM tool_connections WHERE kind='mcp_http'"
    )
    op.execute("UPDATE tool_connections SET service_id=id WHERE kind='mcp_http'")
    op.execute(
        "ALTER TABLE agents ADD COLUMN created_by_user_id TEXT CONSTRAINT fk_agents_created_by_user_id_users REFERENCES users(id)"
    )
    op.add_column(
        "agent_tool_grants",
        sa.Column("account_mode", sa.Text(), nullable=False, server_default="personal"),
    )
    op.execute(
        "UPDATE agent_tool_grants SET account_mode='shared' WHERE tool_connection_id IN (SELECT id FROM tool_connections WHERE kind='native')"
    )
    op.create_table(
        "personal_tool_bindings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "grant_id",
            sa.Text(),
            sa.ForeignKey("agent_tool_grants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.Text(),
            sa.ForeignKey("tool_connections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
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
    )
    op.create_index(
        "uq_personal_tool_binding", "personal_tool_bindings", ["user_id", "grant_id"], unique=True
    )


def downgrade():
    op.drop_table("personal_tool_bindings")
    with op.batch_alter_table("agent_tool_grants") as batch:
        batch.drop_column("account_mode")
    with op.batch_alter_table("agents") as batch:
        batch.drop_column("created_by_user_id")
    with op.batch_alter_table("tool_connections") as batch:
        batch.drop_constraint("fk_tool_connections_service_id_mcp_services", type_="foreignkey")
        batch.drop_constraint(op.f("ck_tool_connections_account_scope_valid"), type_="check")
        batch.drop_column("service_id")
        batch.drop_column("account_scope")
        batch.drop_column("tool_annotations")
        batch.drop_column("annotations_revision")
        batch.create_unique_constraint("uq_tool_connections_name", ["name"])
    op.drop_table("mcp_services")
