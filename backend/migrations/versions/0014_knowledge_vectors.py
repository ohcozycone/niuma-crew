"""Derived, scope-bound knowledge vectors and their model/source provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "knowledge_vector_indexes",
        sa.Column(
            "knowledge_base_id", sa.Text(), sa.ForeignKey("knowledge_bases.id"), primary_key=True
        ),
        sa.Column(
            "connection_id", sa.Text(), sa.ForeignKey("model_connections.id"), nullable=False
        ),
        sa.Column("config_revision", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Text(), nullable=False),
        sa.Column("source_digest", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_knowledge_vector_indexes_connection_id", "knowledge_vector_indexes", ["connection_id"]
    )
    op.create_table(
        "knowledge_vectors",
        sa.Column("chunk_id", sa.Text(), sa.ForeignKey("knowledge_chunks.id"), primary_key=True),
        sa.Column(
            "knowledge_base_id", sa.Text(), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "json_valid(vector) AND json_type(vector) = 'array' AND json_array_length(vector) = 1024",
            name="vector_valid",
        ),
    )
    op.create_index(
        "ix_knowledge_vectors_knowledge_base_id", "knowledge_vectors", ["knowledge_base_id"]
    )


def downgrade():
    op.drop_table("knowledge_vectors")
    op.drop_table("knowledge_vector_indexes")
