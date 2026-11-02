"""Separate original upload from durable per-document keyword processing."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = depends_on = None
STAMP = sa.text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')")


def identity_columns():
    return [
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=STAMP),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=STAMP),
    ]


def upgrade():
    op.add_column(
        "knowledge_bases", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("knowledge_bases", sa.Column("chunk_size", sa.Integer(), nullable=True))
    op.add_column("knowledge_bases", sa.Column("chunk_overlap", sa.Integer(), nullable=True))
    op.add_column(
        "knowledge_documents",
        sa.Column("processing_state", sa.Text(), nullable=False, server_default="pending"),
    )
    op.add_column("knowledge_documents", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("active_job_id", sa.Text(), nullable=True))
    op.add_column(
        "knowledge_documents",
        sa.Column("processing_rules", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.execute(
        "UPDATE knowledge_documents SET processing_state='ready', "
        "processing_rules=json_object('chunk_size', 800, 'chunk_overlap', 120) "
        "WHERE json_extract(snapshot, '$.version') IS NOT NULL"
    )
    # The legacy table used the same convention name for two distinct unique keys.
    # Give them stable names while retaining all rows, indexes and FK references.
    meta = sa.MetaData()
    sa.Table("knowledge_bases", meta, sa.Column("id", sa.Text(), primary_key=True))
    sa.Table("stored_files", meta, sa.Column("id", sa.Text(), primary_key=True))
    documents = sa.Table(
        "knowledge_documents",
        meta,
        *identity_columns(),
        sa.Column(
            "knowledge_base_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_bases.id",
                name="fk_knowledge_documents_knowledge_base_id_knowledge_bases",
            ),
            nullable=False,
        ),
        sa.Column("client_request_id", sa.Text(), nullable=False),
        sa.Column(
            "file_id",
            sa.Text(),
            sa.ForeignKey("stored_files.id", name="fk_knowledge_documents_file_id_stored_files"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("lexical_version", sa.Text(), nullable=False),
        sa.Column("processing_state", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("processing_error", sa.Text()),
        sa.Column("active_job_id", sa.Text()),
        sa.Column("processing_rules", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_documents"),
        sa.UniqueConstraint(
            "knowledge_base_id", "client_request_id", name="uq_knowledge_documents_request"
        ),
        sa.UniqueConstraint(
            "knowledge_base_id", "content_hash", name="uq_knowledge_documents_content"
        ),
        sa.UniqueConstraint("file_id", name="uq_knowledge_documents_file_id"),
        sa.CheckConstraint(
            "json_valid(snapshot) AND json_type(snapshot) = 'object'",
            name="ck_knowledge_documents_snapshot_object",
        ),
    )
    sa.Index("ix_knowledge_documents_knowledge_base_id", documents.c.knowledge_base_id)
    with op.batch_alter_table("knowledge_documents", recreate="always", copy_from=documents):
        pass
    op.create_table(
        "knowledge_processing_batches",
        *identity_columns(),
        sa.Column(
            "knowledge_base_id", sa.Text(), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("client_request_id", sa.Text(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.UniqueConstraint("knowledge_base_id", "client_request_id"),
    )
    op.create_index(
        "ix_knowledge_processing_batches_knowledge_base_id",
        "knowledge_processing_batches",
        ["knowledge_base_id"],
    )
    op.create_table(
        "knowledge_processing_items",
        *identity_columns(),
        sa.Column(
            "batch_id", sa.Text(), sa.ForeignKey("knowledge_processing_batches.id"), nullable=False
        ),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    for column in ("batch_id", "document_id", "status"):
        op.create_index(
            "ix_knowledge_processing_items_" + column, "knowledge_processing_items", [column]
        )


def downgrade():
    op.drop_table("knowledge_processing_items")
    op.drop_table("knowledge_processing_batches")
    for column in ("processing_rules", "active_job_id", "processing_error", "processing_state"):
        op.drop_column("knowledge_documents", column)
    for column in ("chunk_overlap", "chunk_size", "revision"):
        op.drop_column("knowledge_bases", column)
