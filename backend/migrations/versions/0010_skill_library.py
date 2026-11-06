"""Associate portable editable Skill directories without changing existing IDs."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = depends_on = None


def upgrade():
    op.add_column("skills", sa.Column("source_path", sa.Text(), nullable=True))
    op.create_index("ix_skills_source_path", "skills", ["source_path"], unique=True)


def downgrade():
    op.drop_index("ix_skills_source_path", table_name="skills")
    op.drop_column("skills", "source_path")
