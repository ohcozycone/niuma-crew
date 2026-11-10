"""Persistent user-owned knowledge libraries and transactional FTS5."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = depends_on = None
STAMP = sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')")


def identity_columns():
    return [
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=STAMP),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=STAMP),
    ]


def upgrade():
    op.create_table(
        "knowledge_bases",
        *identity_columns(),
        sa.Column("owner_user_id", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_request_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 100", name="name_valid"),
        sa.UniqueConstraint("owner_user_id", "client_request_id"),
    )
    op.create_index("ix_knowledge_bases_owner_user_id", "knowledge_bases", ["owner_user_id"])
    op.create_table(
        "knowledge_documents",
        *identity_columns(),
        sa.Column(
            "knowledge_base_id", sa.Text(), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("client_request_id", sa.Text(), nullable=False),
        sa.Column(
            "file_id", sa.Text(), sa.ForeignKey("stored_files.id"), nullable=False, unique=True
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("lexical_version", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "json_valid(snapshot) AND json_type(snapshot) = 'object'", name="snapshot_object"
        ),
        sa.UniqueConstraint("knowledge_base_id", "client_request_id"),
        sa.UniqueConstraint("knowledge_base_id", "content_hash"),
    )
    op.create_index(
        "ix_knowledge_documents_knowledge_base_id", "knowledge_documents", ["knowledge_base_id"]
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "document_id", sa.Text(), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint("position >= 0", name="position_nonnegative"),
        sa.CheckConstraint(
            "json_valid(snapshot) AND json_type(snapshot) = 'object'", name="snapshot_object"
        ),
        sa.UniqueConstraint("document_id", "position"),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.execute(
        "CREATE VIRTUAL TABLE knowledge_fts USING fts5(chunk_id UNINDEXED, knowledge_base_id UNINDEXED, tokens, tokenize='unicode61')"
    )


def downgrade():
    op.execute("DROP TABLE knowledge_fts")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_bases")
