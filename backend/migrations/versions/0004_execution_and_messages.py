"""Separate durable communication, execution attempts and SDK recovery state.

Existing content is preflighted before any DDL. Offline SQL is for empty databases;
data-bearing upgrades require the online reader and both original database files.
"""

import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import context, op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Frozen DDL is appended below. Never import live application models in a revision.


def stable_id(kind, key):
    return str(uuid5(NAMESPACE_URL, f"niuma-crew:execution-migration:{kind}:{key}"))


def read_legacy_outputs(bind, rows):
    outputs = {}
    selected = [row for row in rows if row["output_checkpoint_id"]]
    if not selected:
        return outputs
    path = Path(bind.engine.url.database).with_suffix(".checkpoints.sqlite")
    if not path.is_file():
        raise RuntimeError("迁移需要原 checkpoint 文件以保留历史正文；业务库未修改。")
    from langgraph.checkpoint.sqlite import SqliteSaver

    try:
        with closing(sqlite3.connect(str(path))) as connection:
            saver = SqliteSaver(connection)
            for row in selected:
                entry = saver.get_tuple(
                    {
                        "configurable": {
                            "thread_id": row["conversation_id"],
                            "checkpoint_ns": "",
                            "checkpoint_id": row["output_checkpoint_id"],
                        }
                    }
                )
                messages = entry.checkpoint["channel_values"].get("messages", []) if entry else []
                message = next(
                    (item for item in messages if item.id == row["output_message_id"]), None
                )
                if message is None or message.type != "ai" or message.tool_calls:
                    raise ValueError("Missing committed output")
                outputs[row["id"]] = str(message.text)
    except Exception as error:
        raise RuntimeError(
            "旧 checkpoint 正文无法完整读取，已停止迁移；请恢复原存档或使用新的空库。"
        ) from error
    return outputs


def insert(bind, table, values):
    columns = ",".join(f'"{key}"' for key in values)
    parameters = ",".join(f":{key}" for key in values)
    bind.execute(sa.text(f'INSERT INTO "{table}" ({columns}) VALUES ({parameters})'), values)


def upgrade():
    offline = context.is_offline_mode()
    bind = None if offline else op.get_bind()
    rows = (
        []
        if offline
        else list(bind.exec_driver_sql("SELECT * FROM runs ORDER BY created_at,id").mappings())
    )
    conversations = (
        {}
        if offline
        else {
            row["id"]: row for row in bind.exec_driver_sql("SELECT * FROM conversations").mappings()
        }
    )
    actions = (
        []
        if offline
        else list(
            bind.exec_driver_sql("SELECT * FROM run_steps ORDER BY run_id,sequence").mappings()
        )
    )
    outputs = {} if offline else read_legacy_outputs(bind, rows)
    content = {}
    for row in rows:
        content[row["input_message_id"]] = {
            "id": row["input_message_id"],
            "role": "user",
            "content": row["input_text"],
        }
        if outputs.get(row["id"]):
            content[row["output_message_id"]] = {
                "id": row["output_message_id"],
                "role": "assistant",
                "content": outputs[row["id"]],
            }
        if row["status"] == "succeeded" and not outputs.get(row["id"]):
            raise RuntimeError("成功执行缺少可读取正文，已停止迁移。")
    for row in rows:
        if any(key not in content for key in json.loads(row["context_message_ids"])):
            raise RuntimeError("历史上下文不完整，已停止迁移。")
    if offline:
        op.execute("CREATE TEMP TABLE execution_upgrade_guard (count INTEGER CHECK(count = 0))")
        op.execute("INSERT INTO execution_upgrade_guard SELECT count(*) FROM runs")
        op.execute("DROP TABLE execution_upgrade_guard")
    for statement in LEGACY_RUNS + LEGACY_ACTIONS:
        match = re.match(r"CREATE (?:UNIQUE )?INDEX (\w+) ON", statement.strip())
        if match:
            op.drop_index(match[1])
    op.rename_table("run_steps", "legacy_run_steps")
    op.rename_table("runs", "legacy_runs")
    for statement in NEW_SCHEMA:
        op.execute(statement)
    now = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    inserted_messages = set()
    for row in rows:
        conversation = conversations[row["conversation_id"]]
        interrupted = row["status"] in ("queued", "running", "cancelling")
        status = (
            "cancelled"
            if row["status"] == "cancelling"
            else "interrupted"
            if interrupted
            else row["status"]
        )
        error = (
            None
            if status == "cancelled"
            else "runtime_interrupted"
            if interrupted
            else row["error_code"]
        )
        values = {
            key: row[key]
            for key in (
                "id",
                "created_at",
                "updated_at",
                "initiated_by_user_id",
                "initiated_by_session_id",
                "client_request_id",
                "request_hash",
                "retry_of_run_id",
                "model_connection_id",
                "config_snapshot",
                "model_calls",
                "skill_reads",
                "usage",
                "started_at",
                "cancel_requested_at",
            )
        }
        values.update(
            agent_id=conversation["agent_id"],
            owner_user_id=conversation["owner_user_id"],
            origin_kind="conversation",
            operation="conversation.retry" if row["retry_of_run_id"] else "conversation.send",
            trigger="retry" if row["retry_of_run_id"] else "user",
            mode="execute",
            status=status,
            error_code=error,
            revision=row["revision"] + int(interrupted),
            actions_revision=row["steps_revision"],
            checkpoint_id=None,
            progress_payload=row["ci_result"],
            finished_at=now if interrupted else row["finished_at"],
            input_snapshot=json.dumps(
                [content[key] for key in json.loads(row["context_message_ids"])]
                + [content[row["input_message_id"]]],
                ensure_ascii=False,
            ),
        )
        insert(bind, "runs", values)
        if row["input_message_id"] not in inserted_messages:
            insert(
                bind,
                "messages",
                dict(
                    id=row["input_message_id"],
                    conversation_id=row["conversation_id"],
                    sequence=row["input_sequence"],
                    role="user",
                    body=row["input_text"],
                    result_id=None,
                    created_at=row["input_created_at"],
                    updated_at=row["input_created_at"],
                ),
            )
            inserted_messages.add(row["input_message_id"])
        answer = outputs.get(row["id"])
        result_id = stable_id("result", row["id"]) if answer else None
        if answer:
            insert(
                bind,
                "run_results",
                dict(
                    id=result_id,
                    run_id=row["id"],
                    output_key="answer" if status == "succeeded" else "partial",
                    content_type="text/markdown",
                    schema_version=1,
                    content=answer,
                    structured=row["ci_result"] if status == "succeeded" else None,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                ),
            )
        published = status == "succeeded" and bool(answer)
        if published:
            insert(
                bind,
                "messages",
                dict(
                    id=row["output_message_id"],
                    conversation_id=row["conversation_id"],
                    sequence=row["output_sequence"],
                    role="assistant",
                    body=None,
                    result_id=result_id,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                ),
            )
        insert(
            bind,
            "conversation_runs",
            dict(
                run_id=row["id"],
                conversation_id=row["conversation_id"],
                input_message_id=row["input_message_id"],
                response_id=row["output_message_id"],
                response_sequence=row["output_sequence"],
                output_message_id=row["output_message_id"] if published else None,
                active=0,
            ),
        )
        if row["ci_feedback"]:
            insert(bind, "ci_feedback", dict(run_id=row["id"], payload=row["ci_feedback"]))
    for action in actions:
        values = {key: value for key, value in action.items() if key != "step_key"}
        values.update(
            action_key=action["step_key"], call_key=action["step_key"], parent_action_id=None
        )
        if values["status"] in ("running", "interrupted"):
            values.update(
                status="unknown"
                if values["kind"] in ("model_call", "tool_call")
                else "interrupted",
                finished_at=values["finished_at"] or now,
                error_code=values["error_code"] or "runtime_interrupted",
            )
        insert(bind, "run_actions", values)
    op.drop_table("legacy_run_steps")
    op.drop_table("legacy_runs")
    op.drop_column("conversations", "checkpoint_id")


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("执行模型降级需要在线检查空库；已有数据请恢复升级前备份。")
    bind = op.get_bind()
    if (
        bind.exec_driver_sql("SELECT count(*) FROM runs").scalar_one()
        or bind.exec_driver_sql("SELECT count(*) FROM messages").scalar_one()
    ):
        raise RuntimeError(
            "新执行模型已有数据，不支持有损降级；请恢复升级前的业务库与 checkpoint 备份。"
        )
    for name in (
        "ci_feedback",
        "conversation_runs",
        "messages",
        "run_results",
        "run_actions",
        "runs",
    ):
        op.drop_table(name)
    for statement in LEGACY_RUNS + LEGACY_ACTIONS:
        op.execute(statement)
    op.add_column("conversations", sa.Column("checkpoint_id", sa.Text(), nullable=True))


LEGACY_RUNS = (
    "CREATE TABLE runs (\n\tconversation_id TEXT NOT NULL, \n\tinput_message_id TEXT NOT NULL, \n\toutput_message_id TEXT NOT NULL, \n\tinput_sequence INTEGER NOT NULL, \n\toutput_sequence INTEGER NOT NULL, \n\tinput_text TEXT NOT NULL, \n\tinput_created_at TEXT NOT NULL, \n\tcheckpoint_id TEXT, \n\toutput_checkpoint_id TEXT, \n\tmodel_calls INTEGER DEFAULT '0' NOT NULL, \n\tskill_reads INTEGER DEFAULT '0' NOT NULL, \n\tinitiated_by_user_id TEXT NOT NULL, \n\tinitiated_by_session_id TEXT, \n\tclient_request_id TEXT NOT NULL, \n\trequest_hash TEXT NOT NULL, \n\tretry_of_run_id TEXT, \n\tmodel_connection_id TEXT, \n\tstatus TEXT DEFAULT 'queued' NOT NULL, \n\trevision INTEGER DEFAULT 1 NOT NULL, \n\tsteps_revision INTEGER DEFAULT 1 NOT NULL, \n\tconfig_snapshot JSON NOT NULL, \n\tcontext_message_ids JSON NOT NULL, \n\terror_code TEXT, \n\tusage JSON, \n\tci_result JSON CONSTRAINT ck_runs_ci_result_object CHECK (ci_result IS NULL OR (json_valid(ci_result) AND json_type(ci_result) = 'object')), \n\tci_feedback JSON CONSTRAINT ck_runs_ci_feedback_object CHECK (ci_feedback IS NULL OR (json_valid(ci_feedback) AND json_type(ci_feedback) = 'object')), \n\tstarted_at TEXT, \n\tcancel_requested_at TEXT, \n\tfinished_at TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_runs PRIMARY KEY (id), \n\tCONSTRAINT uq_runs_conversation_id UNIQUE (conversation_id, id), \n\tCONSTRAINT uq_runs_initiated_by_user_id UNIQUE (initiated_by_user_id, client_request_id), \n\tCONSTRAINT fk_runs_conversation_id_runs FOREIGN KEY(conversation_id, retry_of_run_id) REFERENCES runs (conversation_id, id), \n\tCONSTRAINT ck_runs_messages_distinct CHECK (input_message_id != output_message_id), \n\tCONSTRAINT ck_runs_sequences_valid CHECK (input_sequence > 0 AND output_sequence > input_sequence), \n\tCONSTRAINT ck_runs_budgets_valid CHECK (model_calls >= 0 AND skill_reads >= 0), \n\tCONSTRAINT ck_runs_status_valid CHECK (status IN ('queued','running','cancelling','succeeded','failed','cancelled','interrupted')), \n\tCONSTRAINT ck_runs_finish_valid CHECK ((status IN ('queued','running','cancelling') AND finished_at IS NULL) OR (status IN ('succeeded','failed','cancelled','interrupted') AND finished_at IS NOT NULL)), \n\tCONSTRAINT ck_runs_revision_valid CHECK (revision > 0), \n\tCONSTRAINT ck_runs_steps_revision_valid CHECK (steps_revision > 0), \n\tCONSTRAINT ck_runs_snapshot_valid CHECK (json_valid(config_snapshot) AND json_type(config_snapshot) = 'object'), \n\tCONSTRAINT ck_runs_context_valid CHECK (json_valid(context_message_ids) AND json_type(context_message_ids) = 'array'), \n\tCONSTRAINT ck_runs_usage_valid CHECK (usage IS NULL OR json_valid(usage)), \n\tCONSTRAINT fk_runs_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tCONSTRAINT uq_runs_output_message_id UNIQUE (output_message_id), \n\tCONSTRAINT fk_runs_initiated_by_user_id_users FOREIGN KEY(initiated_by_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_runs_initiated_by_session_id_auth_sessions FOREIGN KEY(initiated_by_session_id) REFERENCES auth_sessions (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_runs_model_connection_id_model_connections FOREIGN KEY(model_connection_id) REFERENCES model_connections (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_runs_conversation_created ON runs (conversation_id, created_at, id)",
    "CREATE INDEX ix_runs_initiated_by_session_id ON runs (initiated_by_session_id)",
    "CREATE INDEX ix_runs_model_connection_id ON runs (model_connection_id)",
    "CREATE INDEX ix_runs_status_created ON runs (status, created_at, id)",
    "CREATE UNIQUE INDEX uq_runs_active_conversation ON runs (conversation_id) WHERE status IN ('queued','running','cancelling')",
)


LEGACY_ACTIONS = (
    "CREATE TABLE run_steps (\n\trun_id TEXT NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tstep_key TEXT NOT NULL, \n\tkind TEXT NOT NULL, \n\tstatus TEXT DEFAULT 'running' NOT NULL, \n\tskill_id TEXT, \n\tsafe_details JSON DEFAULT '{}' NOT NULL, \n\toutput_text TEXT DEFAULT '' NOT NULL, \n\treasoning_text TEXT DEFAULT '' NOT NULL, \n\treasoning_truncated BOOLEAN DEFAULT 0 NOT NULL, \n\tresult_ref TEXT, \n\terror_code TEXT, \n\tstarted_at TEXT NOT NULL, \n\tfinished_at TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_run_steps PRIMARY KEY (id), \n\tCONSTRAINT ck_run_steps_reasoning_truncated_boolean CHECK (reasoning_truncated IN (0, 1)), \n\tCONSTRAINT uq_run_steps_sequence UNIQUE (run_id, sequence), \n\tCONSTRAINT uq_run_steps_key UNIQUE (run_id, step_key), \n\tCONSTRAINT ck_run_steps_sequence_positive CHECK (sequence > 0), \n\tCONSTRAINT ck_run_steps_step_key_not_blank CHECK (length(trim(step_key)) > 0), \n\tCONSTRAINT ck_run_steps_kind_valid CHECK (kind IN ('skill_activation','model_call','tool_call','knowledge','validation')), \n\tCONSTRAINT ck_run_steps_status_valid CHECK (status IN ('running','succeeded','failed','cancelled','interrupted')), \n\tCONSTRAINT ck_run_steps_finish_valid CHECK ((status = 'running' AND finished_at IS NULL) OR (status != 'running' AND finished_at IS NOT NULL)), \n\tCONSTRAINT ck_run_steps_safe_details_object CHECK (json_valid(safe_details) AND json_type(safe_details) = 'object'), \n\tCONSTRAINT fk_run_steps_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_run_steps_skill_id_skills FOREIGN KEY(skill_id) REFERENCES skills (id) ON DELETE SET NULL\n)",
)


NEW_SCHEMA = (
    "CREATE TABLE runs (\n\tagent_id TEXT NOT NULL, \n\towner_user_id TEXT NOT NULL, \n\tinitiated_by_user_id TEXT NOT NULL, \n\tinitiated_by_session_id TEXT, \n\torigin_kind TEXT NOT NULL, \n\toperation TEXT NOT NULL, \n\t\"trigger\" TEXT NOT NULL, \n\tmode TEXT NOT NULL, \n\tclient_request_id TEXT NOT NULL, \n\trequest_hash TEXT NOT NULL, \n\tretry_of_run_id TEXT, \n\tmodel_connection_id TEXT, \n\tconfig_snapshot JSON NOT NULL, \n\tinput_snapshot JSON NOT NULL, \n\tcheckpoint_id TEXT, \n\tstatus TEXT DEFAULT 'queued' NOT NULL, \n\trevision INTEGER DEFAULT 1 NOT NULL, \n\tactions_revision INTEGER DEFAULT 1 NOT NULL, \n\tmodel_calls INTEGER DEFAULT 0 NOT NULL, \n\tskill_reads INTEGER DEFAULT 0 NOT NULL, \n\terror_code TEXT, \n\tusage JSON, \n\tprogress_payload JSON, \n\tstarted_at TEXT, \n\tcancel_requested_at TEXT, \n\tfinished_at TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_runs PRIMARY KEY (id), \n\tCONSTRAINT uq_runs_request UNIQUE (initiated_by_user_id, operation, client_request_id), \n\tCONSTRAINT uq_runs_retry_identity UNIQUE (owner_user_id, agent_id, origin_kind, id), \n\tCONSTRAINT fk_runs_owner_user_id_runs FOREIGN KEY(owner_user_id, agent_id, origin_kind, retry_of_run_id) REFERENCES runs (owner_user_id, agent_id, origin_kind, id), \n\tCONSTRAINT ck_runs_status_valid CHECK (status IN ('queued','running','cancelling','succeeded','failed','cancelled','interrupted')), \n\tCONSTRAINT ck_runs_finish_valid CHECK ((status IN ('queued','running','cancelling') AND finished_at IS NULL) OR (status IN ('succeeded','failed','cancelled','interrupted') AND finished_at IS NOT NULL)), \n\tCONSTRAINT ck_runs_budgets_valid CHECK (model_calls >= 0 AND skill_reads >= 0), \n\tCONSTRAINT ck_runs_revision_valid CHECK (revision > 0 AND actions_revision > 0), \n\tCONSTRAINT ck_runs_snapshot_valid CHECK (json_valid(config_snapshot) AND json_type(config_snapshot) = 'object'), \n\tCONSTRAINT ck_runs_input_valid CHECK (json_valid(input_snapshot) AND json_type(input_snapshot) = 'array'), \n\tCONSTRAINT ck_runs_usage_valid CHECK (usage IS NULL OR json_valid(usage)), \n\tCONSTRAINT fk_runs_agent_id_agents FOREIGN KEY(agent_id) REFERENCES agents (id), \n\tCONSTRAINT fk_runs_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_runs_initiated_by_user_id_users FOREIGN KEY(initiated_by_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_runs_initiated_by_session_id_auth_sessions FOREIGN KEY(initiated_by_session_id) REFERENCES auth_sessions (id) ON DELETE SET NULL, \n\tCONSTRAINT fk_runs_model_connection_id_model_connections FOREIGN KEY(model_connection_id) REFERENCES model_connections (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_runs_initiated_by_session_id ON runs (initiated_by_session_id)",
    "CREATE INDEX ix_runs_model_connection_id ON runs (model_connection_id)",
    "CREATE INDEX ix_runs_owner_user_id ON runs (owner_user_id)",
    "CREATE INDEX ix_runs_status_created ON runs (status, created_at, id)",
    "CREATE TABLE run_actions (\n\trun_id TEXT NOT NULL, \n\tsequence INTEGER NOT NULL, \n\taction_key TEXT NOT NULL, \n\tcall_key TEXT NOT NULL, \n\tparent_action_id TEXT, \n\tkind TEXT NOT NULL, \n\tstatus TEXT DEFAULT 'running' NOT NULL, \n\tskill_id TEXT, \n\tsafe_details JSON DEFAULT '{}' NOT NULL, \n\toutput_text TEXT DEFAULT '' NOT NULL, \n\treasoning_text TEXT DEFAULT '' NOT NULL, \n\treasoning_truncated BOOLEAN DEFAULT 0 NOT NULL, \n\tresult_ref TEXT, \n\terror_code TEXT, \n\tstarted_at TEXT NOT NULL, \n\tfinished_at TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_run_actions PRIMARY KEY (id), \n\tCONSTRAINT uq_run_actions_sequence UNIQUE (run_id, sequence), \n\tCONSTRAINT uq_run_actions_key UNIQUE (run_id, action_key), \n\tCONSTRAINT ck_run_actions_sequence_positive CHECK (sequence > 0), \n\tCONSTRAINT ck_run_actions_key_valid CHECK (length(trim(action_key)) > 0), \n\tCONSTRAINT ck_run_actions_kind_valid CHECK (kind IN ('skill_activation','model_call','tool_call','knowledge','validation')), \n\tCONSTRAINT ck_run_actions_status_valid CHECK (status IN ('running','succeeded','failed','cancelled','interrupted','unknown')), \n\tCONSTRAINT ck_run_actions_finish_valid CHECK ((status = 'running' AND finished_at IS NULL) OR (status != 'running' AND finished_at IS NOT NULL)), \n\tCONSTRAINT ck_run_actions_details_valid CHECK (json_valid(safe_details) AND json_type(safe_details) = 'object'), \n\tCONSTRAINT ck_run_actions_reasoning_boolean CHECK (reasoning_truncated IN (0, 1)), \n\tCONSTRAINT fk_run_actions_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id), \n\tCONSTRAINT fk_run_actions_parent_action_id_run_actions FOREIGN KEY(parent_action_id) REFERENCES run_actions (id), \n\tCONSTRAINT fk_run_actions_skill_id_skills FOREIGN KEY(skill_id) REFERENCES skills (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_run_actions_call ON run_actions (run_id, call_key)",
    "CREATE TABLE run_results (\n\trun_id TEXT NOT NULL, \n\toutput_key TEXT NOT NULL, \n\tcontent_type TEXT NOT NULL, \n\tschema_version INTEGER NOT NULL, \n\tcontent TEXT NOT NULL, \n\tstructured JSON, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_run_results PRIMARY KEY (id), \n\tCONSTRAINT uq_run_results_output UNIQUE (run_id, output_key), \n\tCONSTRAINT ck_run_results_key_valid CHECK (length(trim(output_key)) > 0), \n\tCONSTRAINT ck_run_results_content_valid CHECK (length(content) > 0), \n\tCONSTRAINT fk_run_results_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id)\n)",
    "CREATE TABLE messages (\n\tconversation_id TEXT NOT NULL, \n\tsequence INTEGER NOT NULL, \n\trole TEXT NOT NULL, \n\tbody TEXT, \n\tresult_id TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_messages PRIMARY KEY (id), \n\tCONSTRAINT uq_messages_identity UNIQUE (conversation_id, id), \n\tCONSTRAINT uq_messages_sequence UNIQUE (conversation_id, sequence), \n\tCONSTRAINT ck_messages_sequence_valid CHECK (sequence > 0), \n\tCONSTRAINT ck_messages_content_owner CHECK ((role = 'user' AND body IS NOT NULL AND result_id IS NULL) OR (role = 'assistant' AND body IS NULL AND result_id IS NOT NULL)), \n\tCONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tCONSTRAINT uq_messages_result_id UNIQUE (result_id), \n\tCONSTRAINT fk_messages_result_id_run_results FOREIGN KEY(result_id) REFERENCES run_results (id)\n)",
    "CREATE TABLE conversation_runs (\n\trun_id TEXT NOT NULL, \n\tconversation_id TEXT NOT NULL, \n\tinput_message_id TEXT NOT NULL, \n\tresponse_id TEXT NOT NULL, \n\tresponse_sequence INTEGER NOT NULL, \n\toutput_message_id TEXT, \n\tactive BOOLEAN NOT NULL, \n\tCONSTRAINT pk_conversation_runs PRIMARY KEY (run_id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_messages FOREIGN KEY(conversation_id, input_message_id) REFERENCES messages (conversation_id, id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_messages FOREIGN KEY(conversation_id, output_message_id) REFERENCES messages (conversation_id, id), \n\tCONSTRAINT uq_conversation_runs_sequence UNIQUE (conversation_id, response_sequence), \n\tCONSTRAINT ck_conversation_runs_sequence_valid CHECK (response_sequence > 0), \n\tCONSTRAINT ck_conversation_runs_messages_distinct CHECK (response_id != input_message_id), \n\tCONSTRAINT ck_conversation_runs_published_identity CHECK (output_message_id IS NULL OR output_message_id = response_id), \n\tCONSTRAINT ck_conversation_runs_active_valid CHECK (active IN (0,1)), \n\tCONSTRAINT fk_conversation_runs_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tCONSTRAINT uq_conversation_runs_response_id UNIQUE (response_id)\n)",
    "CREATE UNIQUE INDEX uq_conversation_runs_active ON conversation_runs (conversation_id) WHERE active = 1",
    "CREATE TABLE ci_feedback (\n\trun_id TEXT NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_ci_feedback PRIMARY KEY (run_id), \n\tCONSTRAINT fk_ci_feedback_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id)\n)",
)
