"""Rebuild derived vector indexes in Chroma; retain documents and keyword indexes."""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = depends_on = None


def upgrade():
    # Vectors are disposable derivatives. There is deliberately no data conversion.
    op.drop_table("knowledge_vectors")
    op.execute("DELETE FROM knowledge_vector_indexes")
    op.add_column(
        "knowledge_vector_indexes", sa.Column("collection_name", sa.Text(), nullable=False)
    )
    op.add_column(
        "knowledge_vector_indexes", sa.Column("embedding_fingerprint", sa.Text(), nullable=False)
    )
    op.create_index(
        "ix_knowledge_vector_indexes_collection_name",
        "knowledge_vector_indexes",
        ["collection_name"],
        unique=True,
    )
    op.create_table(
        "knowledge_vector_memberships",
        sa.Column("chunk_id", sa.Text(), sa.ForeignKey("knowledge_chunks.id"), primary_key=True),
        sa.Column(
            "knowledge_base_id", sa.Text(), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("generation", sa.Text(), nullable=False),
        sa.Column(
            "document_id", sa.Text(), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("document_version", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_knowledge_vector_memberships_knowledge_base_id",
        "knowledge_vector_memberships",
        ["knowledge_base_id"],
    )


def downgrade():
    raise RuntimeError("Chroma 向量索引不支持有损降级，请恢复备份或删除派生索引后重建。")
