"""Build a real pre-0004 database without using the new ORM against an old schema."""

import json
import sqlite3
from uuid import uuid4

from alembic import command
from checkpoint_helpers import publication_graph
from langchain_core.messages import AIMessage, HumanMessage

from app.execution.runtime.checkpoints import CheckpointStore, checkpoint_config


def seed_legacy(config, path, revision="0003"):
    command.upgrade(config, revision)
    owner, agent, conversation = (str(uuid4()) for _ in range(3))
    first, failed, active = (str(uuid4()) for _ in range(3))
    user, answer, partial, next_user, next_answer = (str(uuid4()) for _ in range(5))
    store = CheckpointStore(str(path))
    # These fixtures exercise historical migrations, whose input filename is frozen.
    store.path = path.with_suffix(".checkpoints.sqlite")
    with store.reader() as saver:
        graph = publication_graph(saver)
        state = graph.update_state(
            checkpoint_config(conversation),
            {
                "messages": [
                    HumanMessage(id=user, content="原始问题"),
                    AIMessage(id=answer, content="正式回答"),
                ]
            },
            as_node="publish",
        )
        first_checkpoint = state["configurable"]["checkpoint_id"]
        state = graph.update_state(
            state, {"messages": [AIMessage(id=partial, content="失败片段")]}, as_node="publish"
        )
        partial_checkpoint = state["configurable"]["checkpoint_id"]
    timestamp = "2026-10-25T00:00:00.000000Z"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute(
            "INSERT INTO users (id,username,password_hash,role) VALUES (?,?,?,'admin')",
            (owner, "legacy-owner", "fixture-hash"),
        )
        db.execute(
            "INSERT INTO agents (id,name,avatar_id) VALUES (?,?,'admin')", (agent, "历史员工")
        )
        db.execute(
            "INSERT INTO conversations (id,agent_id,owner_user_id,title,last_message_sequence,checkpoint_id) VALUES (?,?,?,'历史对话',5,?)",
            (conversation, agent, owner, first_checkpoint),
        )

        def insert(table, values):
            columns = ",".join(values)
            db.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )

        snapshot = json.dumps(
            dict(
                schema_version=1,
                agent_id=agent,
                skills=[],
                selected_skill_ids=[],
                context_pair_count=0,
                context_truncated=False,
            )
        )
        for id, output, sequence, status, retry, checkpoint, input_id, text, input_sequence in [
            (first, answer, 2, "succeeded", None, first_checkpoint, user, "原始问题", 1),
            (failed, partial, 3, "failed", first, partial_checkpoint, user, "原始问题", 1),
            (active, next_answer, 5, "running", None, None, next_user, "后续问题", 4),
        ]:
            insert(
                "runs",
                dict(
                    id=id,
                    conversation_id=conversation,
                    input_message_id=input_id,
                    output_message_id=output,
                    input_sequence=input_sequence,
                    output_sequence=sequence,
                    input_text=text,
                    input_created_at=timestamp,
                    initiated_by_user_id=owner,
                    initiated_by_session_id=None,
                    client_request_id=str(uuid4()),
                    request_hash="legacy-request",
                    retry_of_run_id=retry,
                    status=status,
                    finished_at=None if status == "running" else timestamp,
                    started_at=timestamp,
                    model_calls=1,
                    config_snapshot=snapshot,
                    context_message_ids=json.dumps([user, answer] if id == active else []),
                    output_checkpoint_id=checkpoint,
                    ci_result=json.dumps({"report": {"summary": "保留报告"}})
                    if id == first
                    else None,
                    ci_feedback=json.dumps({"accepted": True}) if id == first else None,
                ),
            )
        insert(
            "run_steps",
            dict(
                id=str(uuid4()),
                run_id=active,
                sequence=1,
                step_key="model:1",
                kind="model_call",
                status="running",
                safe_details="{}",
                started_at=timestamp,
            ),
        )
    return dict(
        owner=owner,
        agent=agent,
        conversation=conversation,
        first=first,
        failed=failed,
        active=active,
        user=user,
        answer=answer,
        checkpoint=store.path,
    )
