"""Retire the CI experiment while retaining shared conversation and execution history.

The application must be stopped and its database/checkpoints/Skill sources backed
up first. Editable sources for the fixed Skill are archived by deployment; this
migration deliberately performs no filesystem operations.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = depends_on = None

CI_SKILL_ID = "6e69bf0e-84ca-44fd-8afb-d299a63d4381"


def upgrade():
    # Freeze identities and the original state before any status or ownership changes.
    # A queued diagnosis need not have created its professional record yet.
    op.execute(
        """
        CREATE TEMP TABLE _retiring_ci_runs AS
        SELECT runs.id, runs.status,
               (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') AS retired_at,
               EXISTS (
                   SELECT 1 FROM run_actions
                   WHERE run_actions.run_id = runs.id AND run_actions.status = 'running'
               ) AS unfinished_actions,
               EXISTS (
                   SELECT 1 FROM run_actions
                   WHERE run_actions.run_id = runs.id AND run_actions.status = 'running'
                         AND run_actions.kind = 'model_call'
               ) AS unfinished_model
        FROM runs
        WHERE json_type(runs.config_snapshot, '$.ci') = 'object'
           OR json_extract(runs.config_snapshot, '$.work.kind') = 'github_ci_diagnosis'
           OR EXISTS (SELECT 1 FROM ci_diagnoses WHERE ci_diagnoses.run_id = runs.id)
        """
    )
    op.execute(
        """
        CREATE TEMP TABLE _retiring_ci_conversations AS
        SELECT DISTINCT conversation_runs.conversation_id
        FROM conversation_runs JOIN _retiring_ci_runs
             ON _retiring_ci_runs.id = conversation_runs.run_id
        WHERE conversation_runs.active = 1
        """
    )
    # The professional table may be the only surviving discriminator. Keep a
    # minimal tombstone in the existing snapshot before dropping that table, so
    # retry/recovery never interprets the old input as an ordinary Agent request.
    op.execute(
        """
        UPDATE runs
        SET config_snapshot = json_set(config_snapshot, '$.retired_work', 'github_ci_diagnosis')
        WHERE id IN (SELECT id FROM _retiring_ci_runs)
        """
    )
    # An outstanding model request can already have consumed unreported tokens.
    # Preserve that uncertainty rather than claiming zero usage or a confirmed result.
    op.execute(
        """
        UPDATE runs SET usage = json_object(
            'input_tokens', NULL, 'output_tokens', NULL, 'total_tokens', NULL,
            'cached_input_tokens', NULL, 'reasoning_tokens', NULL)
        WHERE id IN (
            SELECT id FROM _retiring_ci_runs
            WHERE status IN ('queued','running','cancelling') AND unfinished_model = 1
        )
        """
    )
    op.execute(
        """
        UPDATE run_actions
        SET status = CASE
                WHEN kind IN ('model_call','tool_call') THEN 'unknown'
                WHEN run_id IN (SELECT id FROM _retiring_ci_runs WHERE status = 'cancelling')
                    THEN 'cancelled'
                ELSE 'interrupted' END,
            error_code = CASE
                WHEN run_id IN (SELECT id FROM _retiring_ci_runs WHERE status = 'cancelling')
                    THEN NULL ELSE 'runtime_interrupted' END,
            finished_at = (SELECT retired_at FROM _retiring_ci_runs WHERE id = run_id),
            updated_at = (SELECT retired_at FROM _retiring_ci_runs WHERE id = run_id)
        WHERE status = 'running' AND run_id IN (
            SELECT id FROM _retiring_ci_runs WHERE status IN ('queued','running','cancelling')
        )
        """
    )
    op.execute(
        """
        UPDATE runs
        SET status = CASE WHEN status = 'cancelling' THEN 'cancelled' ELSE 'interrupted' END,
            error_code = CASE WHEN status = 'cancelling' THEN NULL ELSE 'runtime_interrupted' END,
            finished_at = (SELECT retired_at FROM _retiring_ci_runs WHERE id = runs.id),
            updated_at = (SELECT retired_at FROM _retiring_ci_runs WHERE id = runs.id),
            revision = revision + 1,
            actions_revision = actions_revision + (
                SELECT unfinished_actions FROM _retiring_ci_runs WHERE id = runs.id
            )
        WHERE id IN (
            SELECT id FROM _retiring_ci_runs WHERE status IN ('queued','running','cancelling')
        )
        """
    )
    op.execute(
        """
        UPDATE conversation_runs SET active = 0
        WHERE active = 1 AND run_id IN (SELECT id FROM _retiring_ci_runs)
        """
    )
    op.execute(
        """
        UPDATE conversations
        SET revision = revision + 1,
            updated_at = (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')
        WHERE id IN (SELECT conversation_id FROM _retiring_ci_conversations)
        """
    )
    op.execute(
        f"""
        UPDATE agents
        SET revision = revision + 1,
            updated_at = (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')
        WHERE ci_repository IS NOT NULL
           OR id IN (SELECT agent_id FROM agent_skills WHERE skill_id = '{CI_SKILL_ID}')
        """
    )
    # Migration connections disable FK enforcement during schema changes, so the
    # usual ON DELETE SET NULL does not run. Preserve the action and clear its FK.
    op.execute(f"UPDATE run_actions SET skill_id = NULL WHERE skill_id = '{CI_SKILL_ID}'")
    op.execute(f"DELETE FROM agent_skills WHERE skill_id = '{CI_SKILL_ID}'")
    op.execute(f"DELETE FROM skills WHERE id = '{CI_SKILL_ID}'")
    op.drop_table("ci_diagnoses")
    # SQLite can drop this unindexed, non-key column without rebuilding the
    # referenced agents table or disturbing its existing constraints and indexes.
    op.drop_column("agents", "ci_repository")
    op.execute("DROP TABLE _retiring_ci_conversations")
    op.execute("DROP TABLE _retiring_ci_runs")


def downgrade():
    raise RuntimeError(
        "0012 removes CI reports and configuration irreversibly; "
        "restore the verified database, checkpoint and Skill-source backup instead"
    )
