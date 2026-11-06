"""Retain non-secret installation field descriptions for shared MCP definitions."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "mcp_services", sa.Column("input_fields", sa.JSON(), nullable=False, server_default="[]")
    )


def downgrade():
    op.drop_column("mcp_services", "input_fields")
