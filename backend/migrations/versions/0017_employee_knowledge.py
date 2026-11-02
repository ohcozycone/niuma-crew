"""User-scoped employee knowledge settings and run-scoped immutable evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = depends_on = None
STAMP = sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')")


def upgrade():
    op.create_table(
        "knowledge_employee_settings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=STAMP),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=STAMP),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "agent_id", sa.Text(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("mode", sa.Text(), nullable=False, server_default="on_demand"),
        sa.Column("strategy", sa.Text(), nullable=False, server_default="auto"),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="6"),
        sa.UniqueConstraint("user_id", "agent_id"),
    )
    op.create_table(
        "knowledge_employee_libraries",
        sa.Column(
            "settings_id",
            sa.Text(),
            sa.ForeignKey("knowledge_employee_settings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "knowledge_base_id",
            sa.Text(),
            sa.ForeignKey("knowledge_bases.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_table(
        "knowledge_run_evidence",
        sa.Column(
            "run_id", sa.Text(), sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("evidence_id", sa.Text(), primary_key=True),
        sa.Column("knowledge_base_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("document_version", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("knowledge_run_evidence")
    op.drop_table("knowledge_employee_libraries")
    op.drop_table("knowledge_employee_settings")
