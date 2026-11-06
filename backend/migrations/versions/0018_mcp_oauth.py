"""Persist OAuth grants on existing MCP accounts without changing their identities."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = depends_on = None


def connection_baseline():
    table = import_module("migrations.versions.0008_stdio_mcp").connection_baseline()
    for constraint in list(table.constraints):
        if constraint.name in {"ck_tool_connections_auth_valid", "ck_tool_connections_kind_valid"}:
            table.constraints.remove(constraint)
    table.append_constraint(
        sa.CheckConstraint(
            "auth_type IN ('none','bearer','header','env')", name="ck_tool_connections_auth_valid"
        )
    )
    table.append_constraint(
        sa.CheckConstraint(
            "kind IN ('native','mcp_http','mcp_stdio')", name="ck_tool_connections_kind_valid"
        )
    )
    table.append_column(
        sa.Column("approved_instructions", sa.Text(), nullable=False, server_default=sa.text("''"))
    )
    return table


def upgrade():
    with op.batch_alter_table(
        "tool_connections", copy_from=connection_baseline() if op.get_context().as_sql else None
    ) as batch:
        batch.add_column(sa.Column("oauth_status", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("oauth_storage_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch.drop_constraint(op.f("ck_tool_connections_auth_valid"), type_="check")
        batch.create_check_constraint(
            op.f("ck_tool_connections_auth_valid"),
            "auth_type IN ('none','bearer','header','env','oauth')",
        )
        batch.create_check_constraint(
            op.f("ck_tool_connections_oauth_revision_positive"), "oauth_storage_revision > 0"
        )
        batch.create_check_constraint(
            op.f("ck_tool_connections_oauth_state_valid"),
            "(auth_type='oauth' AND kind='mcp_http' AND oauth_status IS NOT NULL AND oauth_status IN ('disconnected','connected','reauth_required')) OR (auth_type!='oauth' AND oauth_status IS NULL)",
        )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM tool_connections WHERE auth_type='oauth'")
    ):
        raise RuntimeError("仍有 OAuth 账号，不能降级丢弃授权资料。")
    with op.batch_alter_table("tool_connections") as batch:
        for name in ("oauth_state_valid", "oauth_revision_positive", "auth_valid"):
            batch.drop_constraint(op.f("ck_tool_connections_" + name), type_="check")
        batch.drop_column("oauth_status")
        batch.drop_column("oauth_storage_revision")
        batch.create_check_constraint(
            op.f("ck_tool_connections_auth_valid"), "auth_type IN ('none','bearer','header','env')"
        )
