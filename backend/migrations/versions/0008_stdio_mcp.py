"""Trusted stdio definitions and approved MCP server guidance."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = depends_on = None


def service_baseline():
    return sa.Table(
        "mcp_services",
        sa.MetaData(),
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Text(), sa.ForeignKey("users.id")),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *[
            sa.Column(
                key,
                sa.Text(),
                nullable=False,
                server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')"),
            )
            for key in ("created_at", "updated_at")
        ],
    )


def connection_baseline():
    # Reuse only an immutable historical table, never the current application's ORM.
    table = import_module("migrations.versions.0007_mcp_accounts").connection_baseline()
    for constraint in list(table.constraints):
        if constraint.name == "uq_tool_connections_name":
            table.constraints.remove(constraint)
    table.append_column(
        sa.Column(
            "service_id",
            sa.Text(),
            sa.ForeignKey("mcp_services.id", name="fk_tool_connections_service_id_mcp_services"),
        )
    )
    table.append_column(
        sa.Column("account_scope", sa.Text(), nullable=False, server_default="personal")
    )
    table.append_column(
        sa.Column("tool_annotations", sa.JSON(), nullable=False, server_default="{}")
    )
    table.append_column(
        sa.Column("annotations_revision", sa.Integer(), nullable=False, server_default="1")
    )
    table.append_constraint(
        sa.CheckConstraint(
            "account_scope IN ('personal','shared')", name="ck_tool_connections_account_scope_valid"
        )
    )
    return table


def upgrade():
    with op.batch_alter_table(
        "mcp_services", copy_from=service_baseline() if op.get_context().as_sql else None
    ) as batch:
        batch.alter_column("url", existing_type=sa.Text(), nullable=True)
        batch.add_column(sa.Column("transport", sa.Text(), nullable=False, server_default="http"))
        batch.add_column(sa.Column("command", sa.Text()))
        batch.add_column(sa.Column("args", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("env_keys", sa.JSON(), nullable=False, server_default="[]"))
        batch.create_check_constraint("transport_valid", "transport IN ('http','stdio')")
        batch.create_check_constraint(
            "transport_definition_valid",
            "(transport='http' AND url IS NOT NULL AND command IS NULL) OR (transport='stdio' AND url IS NULL AND command IS NOT NULL)",
        )
    with op.batch_alter_table(
        "tool_connections", copy_from=connection_baseline() if op.get_context().as_sql else None
    ) as batch:
        batch.drop_constraint(op.f("ck_tool_connections_kind_valid"), type_="check")
        batch.drop_constraint(op.f("ck_tool_connections_auth_valid"), type_="check")
        batch.create_check_constraint("kind_valid", "kind IN ('native','mcp_http','mcp_stdio')")
        batch.create_check_constraint("auth_valid", "auth_type IN ('none','bearer','header','env')")
        batch.add_column(
            sa.Column(
                "approved_instructions", sa.Text(), nullable=False, server_default=sa.text("''")
            )
        )


def downgrade():
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT COUNT(*) FROM tool_connections WHERE kind='mcp_stdio'")
    ).scalar():
        raise RuntimeError("先移除 stdio 连接，再降级，避免静默丢失账号或员工许可。")
    if connection.execute(
        sa.text("SELECT COUNT(*) FROM mcp_services WHERE transport='stdio'")
    ).scalar():
        raise RuntimeError("先移除 stdio 服务，再降级。")
    with op.batch_alter_table("tool_connections") as batch:
        batch.drop_constraint(op.f("ck_tool_connections_kind_valid"), type_="check")
        batch.drop_constraint(op.f("ck_tool_connections_auth_valid"), type_="check")
        batch.create_check_constraint("kind_valid", "kind IN ('native','mcp_http')")
        batch.create_check_constraint("auth_valid", "auth_type IN ('none','bearer','header')")
        batch.drop_column("approved_instructions")
    with op.batch_alter_table("mcp_services") as batch:
        batch.drop_constraint(op.f("ck_mcp_services_transport_definition_valid"), type_="check")
        batch.drop_constraint(op.f("ck_mcp_services_transport_valid"), type_="check")
        for name in ("env_keys", "args", "command", "transport"):
            batch.drop_column(name)
        batch.alter_column("url", existing_type=sa.Text(), nullable=False)
