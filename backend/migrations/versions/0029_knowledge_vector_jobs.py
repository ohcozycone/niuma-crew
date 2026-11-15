"""Durable vector jobs and model/content keyed embedding checkpoints."""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = depends_on = None
STAMP = sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')")


def upgrade():
    op.create_table(
        "knowledge_vector_jobs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=STAMP),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=STAMP),
        sa.Column(
            "knowledge_base_id", sa.Text(), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("client_request_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.Text(), nullable=False),
        sa.Column("config_revision", sa.Integer(), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.Text(), nullable=False),
        sa.Column("previous_generation", sa.Text(), nullable=True),
        sa.Column("embedding_fingerprint", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("reused_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.UniqueConstraint("knowledge_base_id", "client_request_id"),
    )
    for column in ("knowledge_base_id", "status"):
        op.create_index("ix_knowledge_vector_jobs_" + column, "knowledge_vector_jobs", [column])
    op.create_index(
        "uq_knowledge_vector_jobs_active",
        "knowledge_vector_jobs",
        ["knowledge_base_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "knowledge_vector_embeddings",
        sa.Column(
            "knowledge_base_id", sa.Text(), sa.ForeignKey("knowledge_bases.id"), primary_key=True
        ),
        sa.Column("embedding_fingerprint", sa.Text(), primary_key=True),
        sa.Column("content_hash", sa.Text(), primary_key=True),
        sa.Column("vector", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("knowledge_vector_embeddings")
    op.drop_table("knowledge_vector_jobs")
