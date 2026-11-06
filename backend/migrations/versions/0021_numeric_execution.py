"""Create the numeric conversation schema on an empty database; no legacy conversion."""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = depends_on = None


def upgrade():
    if not op.get_context().as_sql:
        for name in TABLES:
            if name != "identifier_sequence" and op.get_bind().scalar(
                sa.text(f'SELECT count(*) FROM "{name}"')
            ):
                raise RuntimeError("数字标识结构仅支持空库，请停止服务并按重建指南清理旧运行数据。")
    for name in reversed(TABLES):
        if name != "identifier_sequence":
            op.execute(f'DROP TABLE "{name}"')
    for statement in DDL:
        op.execute(statement)
    op.execute("INSERT INTO identifier_sequence (id, next_value) VALUES (1, 100000000000)")
    op.execute("""CREATE TRIGGER runs_result_immutable
        BEFORE UPDATE OF result_text, result_data ON runs
        WHEN OLD.status IN ('succeeded','failed','cancelled','interrupted')
          AND (NEW.result_text IS NOT OLD.result_text OR NEW.result_data IS NOT OLD.result_data)
        BEGIN SELECT RAISE(ABORT, 'Completed execution results are immutable'); END""")


def downgrade():
    raise RuntimeError("数字标识结构不支持有损降级；请使用目标版本空库重建。")


TABLES = [
    "identifier_sequence",
    "conversations",
    "runs",
    "knowledge_run_evidence",
    "messages",
    "run_actions",
    "sandbox_resources",
    "stored_files",
    "conversation_runs",
    "message_files",
]

DDL = [
    "\nCREATE TABLE identifier_sequence (\n\tid INTEGER NOT NULL, \n\tnext_value INTEGER NOT NULL, \n\tCONSTRAINT pk_identifier_sequence PRIMARY KEY (id), \n\tCONSTRAINT ck_identifier_sequence_singleton CHECK (id = 1), \n\tCONSTRAINT ck_identifier_sequence_range_valid CHECK (next_value BETWEEN 100000000000 AND 1000000000000)\n)\n\n",
    "\nCREATE TABLE conversations (\n\trevision INTEGER DEFAULT 1 NOT NULL, \n\tagent_id TEXT NOT NULL, \n\towner_user_id TEXT NOT NULL, \n\ttitle TEXT NOT NULL, \n\tlast_message_sequence INTEGER DEFAULT 0 NOT NULL, \n\tid BIGINT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_conversations PRIMARY KEY (id), \n\tCONSTRAINT ck_conversations_numeric_id_range CHECK (id BETWEEN 100000000000 AND 999999999999), \n\tCONSTRAINT ck_conversations_title_length CHECK (length(title) BETWEEN 1 AND 100), \n\tCONSTRAINT ck_conversations_sequence_valid CHECK (last_message_sequence >= 0), \n\tCONSTRAINT ck_conversations_revision_valid CHECK (revision > 0), \n\tCONSTRAINT fk_conversations_agent_id_agents FOREIGN KEY(agent_id) REFERENCES agents (id), \n\tCONSTRAINT fk_conversations_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)\n\n",
    "CREATE INDEX ix_conversations_agent_updated ON conversations (agent_id, updated_at, id)",
    "CREATE INDEX ix_conversations_owner_user_id ON conversations (owner_user_id)",
    "CREATE INDEX ix_conversations_updated ON conversations (updated_at, id)",
    "\nCREATE TABLE runs (\n\tagent_id TEXT NOT NULL, \n\towner_user_id TEXT NOT NULL, \n\tinitiated_by_user_id TEXT NOT NULL, \n\tinitiated_by_session_id TEXT, \n\torigin_kind TEXT NOT NULL, \n\toperation TEXT NOT NULL, \n\t\"trigger\" TEXT NOT NULL, \n\tmode TEXT NOT NULL, \n\tclient_request_id TEXT NOT NULL, \n\trequest_hash TEXT NOT NULL, \n\tretry_of_run_id BIGINT, \n\tmodel_connection_id TEXT, \n\tconfig_snapshot JSON NOT NULL, \n\tinput_snapshot JSON NOT NULL, \n\tthread_id TEXT NOT NULL, \n\tbase_checkpoint_id TEXT, \n\tbase_run_id BIGINT, \n\tcheckpoint_id TEXT, \n\tresult_text TEXT, \n\tresult_data JSON, \n\tstatus TEXT DEFAULT 'queued' NOT NULL, \n\trevision INTEGER DEFAULT 1 NOT NULL, \n\tactions_revision INTEGER DEFAULT 1 NOT NULL, \n\tmodel_calls INTEGER DEFAULT 0 NOT NULL, \n\tskill_reads INTEGER DEFAULT 0 NOT NULL, \n\ttool_calls INTEGER DEFAULT 0 NOT NULL, \n\terror_code TEXT, \n\tusage JSON, \n\tstarted_at TEXT, \n\tcancel_requested_at TEXT, \n\tfinished_at TEXT, \n\tid BIGINT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_runs PRIMARY KEY (id), \n\tCONSTRAINT ck_runs_numeric_id_range CHECK (id BETWEEN 100000000000 AND 999999999999), \n\tCONSTRAINT uq_runs_request UNIQUE (initiated_by_user_id, operation, client_request_id), \n\tCONSTRAINT uq_runs_retry_identity UNIQUE (owner_user_id, agent_id, origin_kind, id), \n\tCONSTRAINT fk_runs_owner_user_id_runs FOREIGN KEY(owner_user_id, agent_id, origin_kind, retry_of_run_id) REFERENCES runs (owner_user_id, agent_id, origin_kind, id), \n\tCONSTRAINT ck_runs_status_valid CHECK (status IN ('queued','running','cancelling','succeeded','failed','cancelled','interrupted')), \n\tCONSTRAINT ck_runs_finish_valid CHECK ((status IN ('queued','running','cancelling') AND finished_at IS NULL) OR (status IN ('succeeded','failed','cancelled','interrupted') AND finished_at IS NOT NULL)), \n\tCONSTRAINT ck_runs_budgets_valid CHECK (model_calls >= 0 AND skill_reads >= 0), \n\tCONSTRAINT ck_runs_revision_valid CHECK (revision > 0 AND actions_revision > 0), \n\tCONSTRAINT ck_runs_snapshot_valid CHECK (json_valid(config_snapshot) AND json_type(config_snapshot) = 'object'), \n\tCONSTRAINT ck_runs_input_valid CHECK (json_valid(input_snapshot) AND json_type(input_snapshot) = 'array'), \n\tCONSTRAINT ck_runs_usage_valid CHECK (usage IS NULL OR json_valid(usage)), \n\tCONSTRAINT fk_runs_agent_id_agents FOREIGN KEY(agent_id) REFERENCES agents (id), \n\tCONSTRAINT fk_runs_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_runs_initiated_by_user_id_users FOREIGN KEY(initiated_by_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_runs_initiated_by_session_id_auth_sessions FOREIGN KEY(initiated_by_session_id) REFERENCES auth_sessions (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_runs_model_connection_id_model_connections FOREIGN KEY(model_connection_id) REFERENCES model_connections (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_runs_base_run_id_runs FOREIGN KEY(base_run_id) REFERENCES runs (id)\n)\n\n",
    "CREATE INDEX ix_runs_initiated_by_session_id ON runs (initiated_by_session_id)",
    "CREATE INDEX ix_runs_model_connection_id ON runs (model_connection_id)",
    "CREATE INDEX ix_runs_owner_user_id ON runs (owner_user_id)",
    "CREATE INDEX ix_runs_status_created ON runs (status, created_at, id)",
    "CREATE UNIQUE INDEX uq_runs_thread_active ON runs (thread_id) WHERE thread_id IS NOT NULL AND status IN ('queued','running','cancelling')",
    "\nCREATE TABLE knowledge_run_evidence (\n\trun_id BIGINT NOT NULL, \n\tevidence_id TEXT NOT NULL, \n\tknowledge_base_id TEXT NOT NULL, \n\tdocument_id TEXT NOT NULL, \n\tdocument_version TEXT NOT NULL, \n\tchunk_id TEXT NOT NULL, \n\tsnapshot JSON NOT NULL, \n\tCONSTRAINT pk_knowledge_run_evidence PRIMARY KEY (run_id, evidence_id), \n\tCONSTRAINT fk_knowledge_run_evidence_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE messages (\n\tconversation_id BIGINT NOT NULL, \n\tsequence INTEGER NOT NULL, \n\trole TEXT NOT NULL, \n\tbody TEXT, \n\tid BIGINT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_messages PRIMARY KEY (id), \n\tCONSTRAINT ck_messages_numeric_id_range CHECK (id BETWEEN 100000000000 AND 999999999999), \n\tCONSTRAINT uq_messages_identity UNIQUE (conversation_id, id), \n\tCONSTRAINT uq_messages_sequence UNIQUE (conversation_id, sequence), \n\tCONSTRAINT ck_messages_sequence_valid CHECK (sequence > 0), \n\tCONSTRAINT ck_messages_content_owner CHECK ((role = 'user' AND body IS NOT NULL AND length(trim(body)) > 0) OR role = 'assistant'), \n\tCONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id)\n)\n\n",
    "\nCREATE TABLE run_actions (\n\trun_id BIGINT NOT NULL, \n\tsequence INTEGER NOT NULL, \n\taction_key TEXT NOT NULL, \n\tcall_key TEXT NOT NULL, \n\tparent_action_id TEXT, \n\tkind TEXT NOT NULL, \n\tstatus TEXT DEFAULT 'running' NOT NULL, \n\tskill_id TEXT, \n\tsafe_details JSON DEFAULT '{}' NOT NULL, \n\toutput_text TEXT DEFAULT '' NOT NULL, \n\treasoning_text TEXT DEFAULT '' NOT NULL, \n\treasoning_truncated BOOLEAN DEFAULT 0 NOT NULL, \n\tresult_ref TEXT, \n\tresult_payload JSON, \n\terror_code TEXT, \n\tstarted_at TEXT NOT NULL, \n\tfinished_at TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_run_actions PRIMARY KEY (id), \n\tCONSTRAINT uq_run_actions_sequence UNIQUE (run_id, sequence), \n\tCONSTRAINT uq_run_actions_key UNIQUE (run_id, action_key), \n\tCONSTRAINT ck_run_actions_sequence_positive CHECK (sequence > 0), \n\tCONSTRAINT ck_run_actions_key_valid CHECK (length(trim(action_key)) > 0), \n\tCONSTRAINT ck_run_actions_kind_valid CHECK (kind IN ('skill_activation','model_call','tool_call','knowledge','validation')), \n\tCONSTRAINT ck_run_actions_status_valid CHECK (status IN ('running','succeeded','failed','cancelled','interrupted','unknown')), \n\tCONSTRAINT ck_run_actions_finish_valid CHECK ((status = 'running' AND finished_at IS NULL) OR (status != 'running' AND finished_at IS NOT NULL)), \n\tCONSTRAINT ck_run_actions_details_valid CHECK (json_valid(safe_details) AND json_type(safe_details) = 'object'), \n\tCONSTRAINT ck_run_actions_reasoning_boolean CHECK (reasoning_truncated IN (0, 1)), \n\tCONSTRAINT fk_run_actions_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id), \n\tCONSTRAINT fk_run_actions_parent_action_id_run_actions FOREIGN KEY(parent_action_id) REFERENCES run_actions (id), \n\tCONSTRAINT fk_run_actions_skill_id_skills FOREIGN KEY(skill_id) REFERENCES skills (id) ON DELETE SET NULL\n)\n\n",
    "CREATE INDEX ix_run_actions_call ON run_actions (run_id, call_key)",
    "\nCREATE TABLE sandbox_resources (\n\trun_id BIGINT NOT NULL, \n\tdeployment_id TEXT NOT NULL, \n\tserver_identity TEXT NOT NULL, \n\tremote_id TEXT, \n\tstate TEXT NOT NULL, \n\texpires_at TEXT NOT NULL, \n\tcleanup_attempts INTEGER NOT NULL, \n\tlast_error TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_sandbox_resources PRIMARY KEY (id), \n\tCONSTRAINT ck_sandbox_resources_state_valid CHECK (state IN ('requested','ready','cleanup','destroyed','unknown')), \n\tCONSTRAINT uq_sandbox_resources_run_id UNIQUE (run_id), \n\tCONSTRAINT fk_sandbox_resources_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id)\n)\n\n",
    "\nCREATE TABLE stored_files (\n\towner_user_id TEXT NOT NULL, \n\torigin_run_id BIGINT, \n\tname TEXT NOT NULL, \n\tmedia_type TEXT NOT NULL, \n\tsize INTEGER NOT NULL, \n\tcontent_hash TEXT NOT NULL, \n\tstorage_key TEXT NOT NULL, \n\tpurpose TEXT NOT NULL, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_stored_files PRIMARY KEY (id), \n\tCONSTRAINT ck_stored_files_size_nonnegative CHECK (size >= 0), \n\tCONSTRAINT ck_stored_files_purpose_valid CHECK (purpose IN ('input','source','output')), \n\tCONSTRAINT fk_stored_files_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_stored_files_origin_run_id_runs FOREIGN KEY(origin_run_id) REFERENCES runs (id), \n\tCONSTRAINT uq_stored_files_storage_key UNIQUE (storage_key)\n)\n\n",
    "CREATE INDEX ix_stored_files_origin_run_id ON stored_files (origin_run_id)",
    "CREATE INDEX ix_stored_files_owner_user_id ON stored_files (owner_user_id)",
    "\nCREATE TABLE conversation_runs (\n\trun_id BIGINT NOT NULL, \n\tconversation_id BIGINT NOT NULL, \n\tinput_message_id BIGINT NOT NULL, \n\thandled_at TEXT, \n\tacceptance_error TEXT, \n\tacceptance_attempts INTEGER DEFAULT '0' NOT NULL, \n\tnext_acceptance_at TEXT, \n\tactive BOOLEAN NOT NULL, \n\tCONSTRAINT pk_conversation_runs PRIMARY KEY (run_id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_messages FOREIGN KEY(conversation_id, input_message_id) REFERENCES messages (conversation_id, id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_messages FOREIGN KEY(conversation_id, run_id) REFERENCES messages (conversation_id, id), \n\tCONSTRAINT ck_conversation_runs_messages_distinct CHECK (run_id != input_message_id), \n\tCONSTRAINT ck_conversation_runs_active_valid CHECK (active IN (0,1)), \n\tCONSTRAINT fk_conversation_runs_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id)\n)\n\n",
    "CREATE UNIQUE INDEX uq_conversation_runs_active ON conversation_runs (conversation_id) WHERE active = 1",
    "\nCREATE TABLE message_files (\n\tmessage_id BIGINT NOT NULL, \n\tfile_id TEXT NOT NULL, \n\tCONSTRAINT pk_message_files PRIMARY KEY (message_id, file_id), \n\tCONSTRAINT fk_message_files_message_id_messages FOREIGN KEY(message_id) REFERENCES messages (id), \n\tCONSTRAINT fk_message_files_file_id_stored_files FOREIGN KEY(file_id) REFERENCES stored_files (id)\n)\n\n",
]
