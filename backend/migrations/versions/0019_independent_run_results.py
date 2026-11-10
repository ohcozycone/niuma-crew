"""Keep execution results independently from application acceptance."""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = depends_on = None


def upgrade():
    op.add_column("runs", sa.Column("result_text", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("result_data", sa.JSON(), nullable=True))
    op.add_column("conversation_runs", sa.Column("handled_at", sa.Text(), nullable=True))
    op.add_column("conversation_runs", sa.Column("acceptance_error", sa.Text(), nullable=True))
    op.add_column(
        "conversation_runs",
        sa.Column("acceptance_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("conversation_runs", sa.Column("next_acceptance_at", sa.Text(), nullable=True))
    # Preserve already published history; no model/tool work is replayed by migration.
    op.execute("""
        UPDATE runs SET result_text = (
            SELECT messages.body FROM conversation_runs
            JOIN messages ON messages.id = conversation_runs.reply_message_id
            WHERE conversation_runs.run_id = runs.id
        ) WHERE status IN ('succeeded','failed','cancelled','interrupted')
    """)
    op.execute("""
        UPDATE conversation_runs SET handled_at = (
            SELECT finished_at FROM runs WHERE runs.id = conversation_runs.run_id
        ) WHERE active = 0
    """)
    op.execute("""
        CREATE TRIGGER runs_result_immutable
        BEFORE UPDATE OF result_text, result_data ON runs
        WHEN OLD.status IN ('succeeded','failed','cancelled','interrupted')
          AND (NEW.result_text IS NOT OLD.result_text OR NEW.result_data IS NOT OLD.result_data)
        BEGIN SELECT RAISE(ABORT, 'Completed execution results are immutable'); END
    """)


def downgrade():
    if op.get_context().as_sql or op.get_bind().scalar(
        sa.text("""
        SELECT COUNT(*) FROM runs r
        LEFT JOIN conversation_runs c ON c.run_id = r.id
        LEFT JOIN messages m ON m.id = c.reply_message_id
        WHERE r.origin_kind != 'conversation'
           OR r.result_data IS NOT NULL
           OR (r.result_text IS NOT NULL AND r.result_text IS NOT m.body)
           OR (r.status IN ('succeeded','failed','cancelled','interrupted') AND c.active = 1)
    """)
    ):
        raise RuntimeError(
            "Independent execution results cannot be discarded; restore the verified database backup."
        )
    op.execute("DROP TRIGGER runs_result_immutable")
    for column in ("next_acceptance_at", "acceptance_attempts", "acceptance_error", "handled_at"):
        op.drop_column("conversation_runs", column)
    op.drop_column("runs", "result_data")
    op.drop_column("runs", "result_text")
