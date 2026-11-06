"""Read a Run's initial checkpoint from its Conversation instead of duplicating it."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("runs", "base_checkpoint_id")


def downgrade() -> None:
    op.add_column("runs", sa.Column("base_checkpoint_id", sa.Text(), nullable=True))
    # 活跃 Run 的会话起点尚未推进，可以回填；已结束 Run 的历史起点不再保留。
    op.execute(
        sa.text(
            """
            UPDATE runs
            SET base_checkpoint_id = (
                SELECT checkpoint_id FROM conversations WHERE conversations.id = runs.conversation_id
            )
            WHERE status IN ('queued', 'running', 'cancelling')
            """
        )
    )
