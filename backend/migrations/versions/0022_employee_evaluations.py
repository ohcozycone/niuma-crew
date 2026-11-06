"""Add independent employee assessments without changing existing work records."""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = depends_on = None


def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    raise RuntimeError("员工考核历史不支持有损降级，请恢复升级前备份。")


DDL = (
    "\nCREATE TABLE evaluation_batches (\n\tagent_id TEXT NOT NULL, \n\towner_user_id TEXT NOT NULL, \n\tsession_id TEXT, \n\trequest_id TEXT NOT NULL, \n\trequest_hash TEXT NOT NULL, \n\tsuite_id TEXT NOT NULL, \n\tsuite_version TEXT NOT NULL, \n\tgrader_version TEXT NOT NULL, \n\tconfiguration_hash TEXT NOT NULL, \n\tconfiguration_snapshot JSON NOT NULL, \n\ttotal INTEGER NOT NULL, \n\tstatus TEXT NOT NULL, \n\terror_code TEXT, \n\tstarted_at TEXT, \n\tfinished_at TEXT, \n\tid BIGINT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_evaluation_batches PRIMARY KEY (id), \n\tCONSTRAINT uq_evaluation_request UNIQUE (owner_user_id, request_id), \n\tCONSTRAINT ck_evaluation_batches_evaluation_total_valid CHECK (total BETWEEN 1 AND 400), \n\tCONSTRAINT ck_evaluation_batches_evaluation_status_valid CHECK (status IN ('queued','running','cancelling','completed','failed','cancelled')), \n\tCONSTRAINT ck_evaluation_batches_evaluation_finish_valid CHECK ((status IN ('queued','running','cancelling') AND finished_at IS NULL) OR (status IN ('completed','failed','cancelled') AND finished_at IS NOT NULL)), \n\tCONSTRAINT fk_evaluation_batches_agent_id_agents FOREIGN KEY(agent_id) REFERENCES agents (id), \n\tCONSTRAINT fk_evaluation_batches_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_evaluation_batches_session_id_auth_sessions FOREIGN KEY(session_id) REFERENCES auth_sessions (id) ON DELETE SET NULL\n)\n\n",
    "CREATE INDEX ix_evaluation_owner_agent ON evaluation_batches (owner_user_id, agent_id, created_at)",
    "\nCREATE TABLE evaluation_cases (\n\tbatch_id BIGINT NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tquestion_id TEXT NOT NULL, \n\tprompt TEXT NOT NULL, \n\tfunctions JSON NOT NULL, \n\texpected JSON NOT NULL, \n\trun_id BIGINT, \n\tstatus TEXT NOT NULL, \n\tanswer TEXT, \n\tgrading JSON, \n\terror_code TEXT, \n\tfinished_at TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_evaluation_cases PRIMARY KEY (id), \n\tCONSTRAINT uq_evaluation_ordinal UNIQUE (batch_id, ordinal), \n\tCONSTRAINT uq_evaluation_question UNIQUE (batch_id, question_id), \n\tCONSTRAINT ck_evaluation_cases_evaluation_ordinal_positive CHECK (ordinal > 0), \n\tCONSTRAINT ck_evaluation_cases_evaluation_case_status_valid CHECK (status IN ('pending','running','passed','failed','error','cancelled')), \n\tCONSTRAINT fk_evaluation_cases_batch_id_evaluation_batches FOREIGN KEY(batch_id) REFERENCES evaluation_batches (id), \n\tCONSTRAINT uq_evaluation_cases_run_id UNIQUE (run_id), \n\tCONSTRAINT fk_evaluation_cases_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id)\n)\n\n",
    "CREATE INDEX ix_evaluation_case_batch ON evaluation_cases (batch_id, status, ordinal)",
)
