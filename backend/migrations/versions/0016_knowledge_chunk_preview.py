"""Keep per-library short-section merging overrides, without rewriting existing chunks."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = depends_on = None


def upgrade():
    op.add_column("knowledge_bases", sa.Column("min_section_chars", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("knowledge_bases", "min_section_chars")
