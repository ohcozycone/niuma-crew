"""Separate durable conversation threads from individual execution attempts."""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = depends_on = None


def upgrade():
    # Nullable fields preserve old fixtures and legacy records; old runs retain
    # their original isolated SDK thread rather than rewriting checkpoint data.
    op.add_column("runs", sa.Column("thread_id", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("base_checkpoint_id", sa.Text(), nullable=True))
    op.execute("ALTER TABLE runs ADD COLUMN base_run_id TEXT REFERENCES runs (id)")
    op.execute("UPDATE runs SET thread_id = id")
    op.create_index(
        "uq_runs_thread_active",
        "runs",
        ["thread_id"],
        unique=True,
        sqlite_where=sa.text(
            "thread_id IS NOT NULL AND status IN ('queued','running','cancelling')"
        ),
    )


def downgrade():
    if op.get_context().as_sql or op.get_bind().scalar(
        sa.text("SELECT count(*) FROM runs WHERE thread_id != id OR base_checkpoint_id IS NOT NULL")
    ):
        raise RuntimeError(
            "Shared thread history cannot be discarded; restore the verified backup."
        )
    op.drop_index("uq_runs_thread_active", table_name="runs")
    op.drop_column("runs", "base_run_id")
    op.drop_column("runs", "base_checkpoint_id")
    op.drop_column("runs", "thread_id")
