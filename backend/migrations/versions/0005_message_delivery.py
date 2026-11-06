"""Keep reply content in Message and move professional CI data to its owner.

Preflight every old record before DDL; unknown ownership or inconsistent reports
abort the transaction. SDK checkpoints are intentionally untouched.
"""

import json

import sqlalchemy as sa
from alembic import context, op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def rows(bind, name):
    return [dict(row) for row in bind.execute(sa.text("SELECT * FROM " + name)).mappings()]


def insert(bind, name, values):
    keys = list(values)
    bind.execute(
        sa.text(
            'INSERT INTO "'
            + name
            + '" ('
            + ",".join('"' + key + '"' for key in keys)
            + ") VALUES ("
            + ",".join(":" + key for key in keys)
            + ")"
        ),
        values,
    )


def validate_ci(candidate, report, feedback, run_id):
    if len(json.dumps(candidate, ensure_ascii=False).encode()) > 131072:
        raise RuntimeError("CI data exceeds its known size: " + run_id)
    if feedback is not None and (
        not isinstance(feedback, dict)
        or set(feedback) != {"decision", "note", "created_at"}
        or feedback["decision"] not in ("useful", "needs_improvement")
        or not isinstance(feedback["note"], str)
        or not isinstance(feedback["created_at"], str)
    ):
        raise RuntimeError("Unknown CI feedback format: " + run_id)
    if report is None:
        return
    if (
        not isinstance(report, dict)
        or set(report) != {"summary", "findings", "unknowns", "coverage", "target"}
        or not isinstance(report["summary"], str)
        or not report["summary"].strip()
        or not isinstance(report["findings"], list)
        or not isinstance(report["unknowns"], list)
    ):
        raise RuntimeError("Unknown CI report format: " + run_id)
    sources = candidate.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RuntimeError("CI report has no preserved sources: " + run_id)
    by_id = {
        source["id"]: source
        for source in sources
        if isinstance(source, dict)
        and isinstance(source.get("id"), str)
        and isinstance(source.get("text"), str)
        and isinstance(source.get("job_id"), str)
    }
    if len(by_id) != len(sources):
        raise RuntimeError("Invalid CI sources: " + run_id)
    covered = set()
    for finding in report["findings"]:
        if (
            not isinstance(finding, dict)
            or set(finding)
            != {"job_id", "verdict", "explanation", "evidence", "next_step", "verification"}
            or finding["verdict"] not in ("observed", "likely", "undetermined")
            or not all(
                isinstance(finding[key], str) and finding[key].strip()
                for key in ("job_id", "explanation", "next_step", "verification")
            )
            or not isinstance(finding["evidence"], list)
            or not finding["evidence"]
        ):
            raise RuntimeError("Invalid CI finding: " + run_id)
        for citation in finding["evidence"]:
            if not isinstance(citation, dict) or set(citation) != {
                "source_id",
                "start_line",
                "end_line",
            }:
                raise RuntimeError("Unknown CI citation: " + run_id)
            source = by_id.get(citation["source_id"])
            start, end = citation["start_line"], citation["end_line"]
            if (
                not source
                or source["job_id"] != finding["job_id"]
                or type(start) is not int
                or type(end) is not int
                or not 1 <= start <= end <= len(source["text"].splitlines())
                or end - start >= 80
            ):
                raise RuntimeError("Invalid CI citation range: " + run_id)
        covered.add(finding["job_id"])
    if covered != {source["job_id"] for source in sources}:
        raise RuntimeError("Incomplete CI report coverage: " + run_id)
    if (
        candidate.get("target") != report["target"]
        or candidate.get("coverage") != report["coverage"]
    ):
        raise RuntimeError("Inconsistent CI target or coverage: " + run_id)


def upgrade():
    offline = context.is_offline_mode()
    bind = None if offline else op.get_bind()
    messages = [] if offline else rows(bind, "messages")
    bindings = [] if offline else rows(bind, "conversation_runs")
    runs = [] if offline else rows(bind, "runs")
    results = [] if offline else rows(bind, "run_results")
    feedback = [] if offline else rows(bind, "ci_feedback")
    by_message = {row["id"]: row for row in messages}
    by_run = {row["id"]: row for row in runs}
    by_result = {row["id"]: row for row in results}
    by_binding = {row["run_id"]: row for row in bindings}
    by_output = {(row["run_id"], row["output_key"]): row for row in results}
    by_feedback = {row["run_id"]: decode(row["payload"]) for row in feedback}
    if len(by_output) != len(results):
        raise RuntimeError("Duplicate legacy results; migration stopped")
    for row in runs:
        if row["origin_kind"] != "conversation" or row["id"] not in by_binding:
            raise RuntimeError("Unowned run: " + row["id"])
    for result in results:
        if (
            result["run_id"] not in by_run
            or result["output_key"]
            != ("answer" if by_run[result["run_id"]]["status"] == "succeeded" else "partial")
            or by_run[result["run_id"]]["status"] in ("queued", "running", "cancelling")
        ):
            raise RuntimeError("Unrecognized result: " + result["id"])
    upgraded_messages = []
    for message in messages:
        value = {key: val for key, val in message.items() if key != "result_id"}
        if message["role"] == "assistant":
            result = by_result.get(message["result_id"])
            if (
                not result
                or result["output_key"] != "answer"
                or by_run[result["run_id"]]["status"] != "succeeded"
            ):
                raise RuntimeError("Untrusted assistant message: " + message["id"])
            value["body"] = result["content"]
        upgraded_messages.append(value)
    diagnoses = []
    for binding in bindings:
        run = by_run.get(binding["run_id"])
        user = by_message.get(binding["input_message_id"])
        if (
            not run
            or not user
            or user["role"] != "user"
            or user["conversation_id"] != binding["conversation_id"]
        ):
            raise RuntimeError("Invalid input binding: " + binding["run_id"])
        answer = by_output.get((run["id"], "answer"))
        partial = by_output.get((run["id"], "partial"))
        if run["status"] == "succeeded" and (not answer or not answer["content"].strip()):
            raise RuntimeError("Missing successful answer: " + run["id"])
        existing = by_message.get(binding["response_id"])
        if existing:
            if (
                existing["role"] != "assistant"
                or existing["conversation_id"] != binding["conversation_id"]
                or existing["sequence"] != binding["response_sequence"]
                or existing["result_id"] != (answer or {}).get("id")
            ):
                raise RuntimeError("Conflicting response identity: " + binding["response_id"])
        else:
            if binding["output_message_id"] is not None or run["status"] == "succeeded":
                raise RuntimeError("Missing published reply: " + run["id"])
            upgraded_messages.append(
                dict(
                    id=binding["response_id"],
                    conversation_id=binding["conversation_id"],
                    sequence=binding["response_sequence"],
                    role="assistant",
                    body=(partial or {}).get("content"),
                    created_at=run["created_at"],
                    updated_at=run["finished_at"] or run["updated_at"],
                )
            )
        snapshot = decode(run["config_snapshot"])
        progress = decode(run["progress_payload"]) or {}
        structured = decode(answer["structured"]) if answer else None
        if snapshot.get("ci") or snapshot.get("work", {}).get("kind") == "github_ci_diagnosis":
            for candidate in (progress, structured):
                if candidate and not isinstance(candidate, dict):
                    raise RuntimeError("Unknown CI format: " + run["id"])
            report = (structured or {}).get("report") if run["status"] == "succeeded" else None
            if run["status"] == "succeeded":
                if not isinstance(report, dict) or not all(
                    key in report
                    for key in ("summary", "findings", "unknowns", "coverage", "target")
                ):
                    raise RuntimeError("Unknown CI report schema: " + run["id"])
                if progress.get("report") is not None and progress["report"] != report:
                    raise RuntimeError("Conflicting CI reports: " + run["id"])
            validate_ci(structured or progress, report, by_feedback.get(run["id"]), run["id"])
            payload = dict(structured or progress)
            payload.pop("report", None)
            if report:
                payload["phase"] = "delivered"
            elif payload.get("phase") == "delivered":
                payload["phase"] = "validating"
            if run["id"] in by_feedback and not report:
                raise RuntimeError("Feedback without a delivered report: " + run["id"])
            diagnoses.append(
                dict(
                    run_id=run["id"],
                    progress_payload=json.dumps(payload, ensure_ascii=False),
                    report=json.dumps(report, ensure_ascii=False) if report else None,
                    revision=run["revision"],
                    feedback=json.dumps(by_feedback[run["id"]], ensure_ascii=False)
                    if run["id"] in by_feedback
                    else None,
                )
            )
        elif progress or structured or run["id"] in by_feedback:
            raise RuntimeError("Unowned professional data: " + run["id"])
    if set(by_feedback) - {row["run_id"] for row in diagnoses}:
        raise RuntimeError("Unowned CI feedback")
    identities = [(row["conversation_id"], row["sequence"]) for row in upgraded_messages]
    if len(set(identities)) != len(identities):
        raise RuntimeError("Conflicting message positions; migration stopped before DDL")
    op.execute(
        "ALTER TABLE conversations ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CONSTRAINT ck_conversations_revision_valid CHECK (revision > 0)"
    )
    for name, ddl in NEW_TABLES:
        op.execute(ddl)
    if not offline:
        for message in upgraded_messages:
            insert(bind, "next_messages", message)
        for binding in bindings:
            insert(
                bind,
                "next_conversation_runs",
                dict(
                    run_id=binding["run_id"],
                    conversation_id=binding["conversation_id"],
                    input_message_id=binding["input_message_id"],
                    reply_message_id=binding["response_id"],
                    active=binding["active"],
                ),
            )
        for diagnosis in diagnoses:
            insert(bind, "next_ci_diagnoses", diagnosis)
    op.drop_table("conversation_runs")
    op.drop_table("messages")
    op.drop_table("ci_feedback")
    op.drop_table("run_results")
    for name, _ in NEW_TABLES:
        op.rename_table("next_" + name, name)
    op.create_index(
        "uq_conversation_runs_active",
        "conversation_runs",
        ["conversation_id"],
        unique=True,
        sqlite_where=sa.text("active = 1"),
    )
    op.execute("ALTER TABLE runs DROP COLUMN progress_payload")


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Downgrade requires online emptiness checks")
    bind = op.get_bind()
    if (
        bind.execute(sa.text("SELECT count(*) FROM runs")).scalar()
        or bind.execute(sa.text("SELECT count(*) FROM messages")).scalar()
    ):
        raise RuntimeError(
            "0005 cannot losslessly restore new reply semantics; restore the verified database and checkpoint backup instead"
        )
    op.drop_table("conversation_runs")
    op.drop_table("messages")
    op.drop_table("ci_diagnoses")
    for ddl in OLD_TABLES:
        op.execute(ddl)
    op.execute("ALTER TABLE runs ADD COLUMN progress_payload JSON")
    op.execute("ALTER TABLE conversations DROP COLUMN revision")


NEW_TABLES = [
    (
        "messages",
        "CREATE TABLE next_messages (\n\tconversation_id TEXT NOT NULL, \n\tsequence INTEGER NOT NULL, \n\trole TEXT NOT NULL, \n\tbody TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_messages PRIMARY KEY (id), \n\tCONSTRAINT uq_messages_identity UNIQUE (conversation_id, id), \n\tCONSTRAINT uq_messages_sequence UNIQUE (conversation_id, sequence), \n\tCONSTRAINT ck_messages_sequence_valid CHECK (sequence > 0), \n\tCONSTRAINT ck_messages_content_owner CHECK ((role = 'user' AND body IS NOT NULL AND length(trim(body)) > 0) OR role = 'assistant'), \n\tCONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id)\n)",
    ),
    (
        "conversation_runs",
        "CREATE TABLE next_conversation_runs (\n\trun_id TEXT NOT NULL, \n\tconversation_id TEXT NOT NULL, \n\tinput_message_id TEXT NOT NULL, \n\treply_message_id TEXT NOT NULL, \n\tactive BOOLEAN NOT NULL, \n\tCONSTRAINT pk_conversation_runs PRIMARY KEY (run_id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_messages FOREIGN KEY(conversation_id, input_message_id) REFERENCES messages (conversation_id, id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_messages FOREIGN KEY(conversation_id, reply_message_id) REFERENCES messages (conversation_id, id), \n\tCONSTRAINT ck_conversation_runs_messages_distinct CHECK (reply_message_id != input_message_id), \n\tCONSTRAINT ck_conversation_runs_active_valid CHECK (active IN (0,1)), \n\tCONSTRAINT fk_conversation_runs_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tCONSTRAINT uq_conversation_runs_reply_message_id UNIQUE (reply_message_id)\n)",
    ),
    (
        "ci_diagnoses",
        "CREATE TABLE next_ci_diagnoses (\n\trun_id TEXT NOT NULL, \n\tprogress_payload JSON DEFAULT '{}' NOT NULL, \n\treport JSON, \n\trevision INTEGER DEFAULT 1 NOT NULL, \n\tfeedback JSON, \n\tCONSTRAINT pk_ci_diagnoses PRIMARY KEY (run_id), \n\tCONSTRAINT ck_ci_diagnoses_revision_valid CHECK (revision > 0), \n\tCONSTRAINT ck_ci_diagnoses_progress_valid CHECK (json_valid(progress_payload) AND json_type(progress_payload) = 'object'), \n\tCONSTRAINT ck_ci_diagnoses_report_valid CHECK (report IS NULL OR (json_valid(report) AND json_type(report) = 'object')), \n\tCONSTRAINT ck_ci_diagnoses_feedback_valid CHECK (feedback IS NULL OR (json_valid(feedback) AND json_type(feedback) = 'object')), \n\tCONSTRAINT fk_ci_diagnoses_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id)\n)",
    ),
]

OLD_TABLES = [
    "CREATE TABLE run_results (\n\trun_id TEXT NOT NULL, \n\toutput_key TEXT NOT NULL, \n\tcontent_type TEXT NOT NULL, \n\tschema_version INTEGER NOT NULL, \n\tcontent TEXT NOT NULL, \n\tstructured JSON, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_run_results PRIMARY KEY (id), \n\tCONSTRAINT uq_run_results_output UNIQUE (run_id, output_key), \n\tCONSTRAINT ck_run_results_key_valid CHECK (length(trim(output_key)) > 0), \n\tCONSTRAINT ck_run_results_content_valid CHECK (length(content) > 0), \n\tCONSTRAINT fk_run_results_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id)\n)",
    "CREATE TABLE messages (\n\tconversation_id TEXT NOT NULL, \n\tsequence INTEGER NOT NULL, \n\trole TEXT NOT NULL, \n\tbody TEXT, \n\tresult_id TEXT, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_messages PRIMARY KEY (id), \n\tCONSTRAINT uq_messages_identity UNIQUE (conversation_id, id), \n\tCONSTRAINT uq_messages_sequence UNIQUE (conversation_id, sequence), \n\tCONSTRAINT ck_messages_sequence_valid CHECK (sequence > 0), \n\tCONSTRAINT ck_messages_content_owner CHECK ((role = 'user' AND body IS NOT NULL AND result_id IS NULL) OR (role = 'assistant' AND body IS NULL AND result_id IS NOT NULL)), \n\tCONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tCONSTRAINT uq_messages_result_id UNIQUE (result_id), \n\tCONSTRAINT fk_messages_result_id_run_results FOREIGN KEY(result_id) REFERENCES run_results (id)\n)",
    "CREATE TABLE conversation_runs (\n\trun_id TEXT NOT NULL, \n\tconversation_id TEXT NOT NULL, \n\tinput_message_id TEXT NOT NULL, \n\tresponse_id TEXT NOT NULL, \n\tresponse_sequence INTEGER NOT NULL, \n\toutput_message_id TEXT, \n\tactive BOOLEAN NOT NULL, \n\tCONSTRAINT pk_conversation_runs PRIMARY KEY (run_id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_messages FOREIGN KEY(conversation_id, input_message_id) REFERENCES messages (conversation_id, id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_messages FOREIGN KEY(conversation_id, output_message_id) REFERENCES messages (conversation_id, id), \n\tCONSTRAINT uq_conversation_runs_sequence UNIQUE (conversation_id, response_sequence), \n\tCONSTRAINT ck_conversation_runs_sequence_valid CHECK (response_sequence > 0), \n\tCONSTRAINT ck_conversation_runs_messages_distinct CHECK (response_id != input_message_id), \n\tCONSTRAINT ck_conversation_runs_published_identity CHECK (output_message_id IS NULL OR output_message_id = response_id), \n\tCONSTRAINT ck_conversation_runs_active_valid CHECK (active IN (0,1)), \n\tCONSTRAINT fk_conversation_runs_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id), \n\tCONSTRAINT fk_conversation_runs_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tCONSTRAINT uq_conversation_runs_response_id UNIQUE (response_id)\n)",
    "CREATE UNIQUE INDEX uq_conversation_runs_active ON conversation_runs (conversation_id) WHERE active = 1",
    "CREATE TABLE ci_feedback (\n\trun_id TEXT NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_ci_feedback PRIMARY KEY (run_id), \n\tCONSTRAINT fk_ci_feedback_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (id)\n)",
]
