"""正式会话、技能中间件、Runner 及真实后端进程的 checkpoint 回归。"""

import sqlite3
import time
from datetime import timedelta
from pathlib import Path

import pytest
from checkpoint_helpers import checkpoint_values
from configuration_helpers import patch_current, set_submission_limits
from sqlalchemy import select
from test_capability_runtime import setup
from test_conversations import send, wait_run
from test_sqlite_checkpoints import server

from app.agent_runtime.checkpoints import checkpoint_config
from app.auth.models import AuthSession
from app.conversations.models import Message
from app.execution.models import Run, RunAction
from app.infrastructure.database.fields import utc_now

WORKER = Path(__file__).with_name("checkpoint_worker.py")


def arguments(config, skill, *extra):
    return (
        "--key",
        str(config.model_encryption_key_file),
        "--lock",
        str(config.runner_lock_file),
        "--skill",
        skill["id"],
        *extra,
    )


def authorize(client, source):
    client.headers.update(
        {
            "Origin": "http://localhost:3000",
            "Cookie": "; ".join(f"{key}={value}" for key, value in source.cookies.items()),
        }
    )


def wait_state(source, id, predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with source.app.state.database.transaction() as db:
            row = db.get(Run, id)
        if predicate(row):
            return row
        time.sleep(0.01)
    raise AssertionError(f"等待运行状态超时：{row.status}")


def test_formal_multiturn_history_and_queued_startup(api_client, migrated_config):
    skill, _, agent, conversation = setup(api_client)
    run = send(api_client, conversation, "第一问").json()
    other = api_client.post("/api/conversations", json={"agent_id": agent["id"]}).json()
    isolated = send(api_client, other, "第二问").json()
    database = Path(migrated_config.database.url.database)
    with server(database, worker=WORKER, worker_args=arguments(migrated_config, skill)) as (
        client,
        _,
    ):
        authorize(client, api_client)
        first = wait_run(client, run["id"])
        assert first["status"] == "succeeded", first
        assert first["assistant_content"] == "回答一"
        assert wait_run(client, isolated["id"])["assistant_content"] == "缺少历史"
        history = client.get(f"/api/conversations/{conversation['id']}/messages").json()
        assert [m["content"] for m in history["items"]] == ["第一问", "回答一"]
        assert "BODY_MARKER" not in str(history)
    with server(database, worker=WORKER, worker_args=arguments(migrated_config, skill)) as (
        client,
        _,
    ):
        authorize(client, api_client)
        assert client.get(f"/api/conversations/{conversation['id']}/messages").json() == history
        second = send(client, conversation, "第二问").json()
        done = wait_run(client, second["id"])
        assert done["assistant_content"] == "回答二：记得回答一", done
        page = client.get(f"/api/conversations/{conversation['id']}/messages").json()
        assert [m["content"] for m in page["items"]] == [
            "第一问",
            "回答一",
            "第二问",
            "回答二：记得回答一",
        ]
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='messages'").fetchone() == (1,)
        assert "base_checkpoint_id" not in {
            column[1] for column in conn.execute("PRAGMA table_info(runs)")
        }


@pytest.mark.parametrize("prior_success", [False, True])
def test_failed_checkpoint_is_not_the_next_run_start(api_client, migrated_config, prior_success):
    skill, _, _, conversation = setup(api_client)
    database = Path(migrated_config.database.url.database)
    with server(database, worker=WORKER, worker_args=arguments(migrated_config, skill)) as (
        client,
        _,
    ):
        authorize(client, api_client)
        if prior_success:
            seed = send(client, conversation, "起始问").json()
            assert wait_run(client, seed["id"])["status"] == "succeeded"
        with api_client.app.state.database.transaction() as db:
            accepted = list(
                db.scalars(
                    select(Message.id).where(
                        Message.conversation_id == conversation["id"], Message.role == "assistant"
                    )
                )
            )
        failed = send(client, conversation, "失败问题").json()
        assert wait_run(client, failed["id"])["status"] == "failed"
        with api_client.app.state.database.transaction() as db:
            row = db.get(Run, failed["id"])
            assert row.checkpoint_id
            visible_ids = set(
                db.scalars(
                    select(Message.id).where(
                        Message.conversation_id == conversation["id"], Message.role == "assistant"
                    )
                )
            )
            assert visible_ids == set(accepted) | {failed["output_message_id"]}
            assert db.get(Message, failed["output_message_id"]).body is None

        history = client.get(f"/api/conversations/{conversation['id']}/messages").json()
    with server(database, worker=WORKER, worker_args=arguments(migrated_config, skill)) as (
        client,
        _,
    ):
        authorize(client, api_client)
        assert client.get(f"/api/conversations/{conversation['id']}/messages").json() == history
        next_run = send(client, conversation, "第二问").json()
        done = wait_run(client, next_run["id"])
        expected = "回答二：记得回答一" if prior_success else "缺少历史"
        assert done["status"] == "succeeded" and done["assistant_content"] == expected, done
        with api_client.app.state.checkpoints.reader() as saver:
            entries = list(
                saver.list(checkpoint_config(next_run["id"]), filter={"app_run_id": next_run["id"]})
            )
        assert entries[-1].parent_config is None
        with api_client.app.state.database.transaction() as db:
            inputs = db.get(Run, next_run["id"]).input_snapshot
            assert all(item["content"] != "失败问题" for item in inputs)


@pytest.mark.parametrize("stop", ["kill", "terminate"])
@pytest.mark.parametrize("prior_success", [False, True])
def test_formal_runner_recovers_after_tool_and_keeps_budgets(
    api_client, migrated_config, stop, prior_success
):
    skill, _, _, conversation = setup(api_client)
    database = Path(migrated_config.database.url.database)
    if prior_success:
        with server(database, worker=WORKER, worker_args=arguments(migrated_config, skill)) as (
            client,
            _,
        ):
            authorize(client, api_client)
            seed = send(client, conversation, "起始问").json()
            assert wait_run(client, seed["id"])["status"] == "succeeded"
    run = send(api_client, conversation, "第一问").json()

    def second_model_started(row):
        if row.model_calls != 2 or row.skill_reads != 1 or row.checkpoint_id is None:
            return False
        # Budget reservation commits before action creation; kill only after the action exists.
        with api_client.app.state.database.transaction() as db:
            return (
                db.scalar(
                    select(RunAction.id).where(
                        RunAction.run_id == row.id,
                        RunAction.action_key == "model:2",
                        RunAction.status == "running",
                    )
                )
                is not None
            )

    with server(
        database,
        worker=WORKER,
        worker_args=arguments(migrated_config, skill),
        pause_after_lookup=True,
    ) as (_, process):
        before = wait_state(
            api_client,
            run["id"],
            second_model_started,
        )
        started_at = before.started_at
        getattr(process, stop)()
        process.wait(timeout=5)
    with server(database, worker=WORKER, worker_args=arguments(migrated_config, skill)) as (
        client,
        _,
    ):
        authorize(client, api_client)
        done = wait_run(client, run["id"])
        assert done["status"] == "succeeded" and done["assistant_content"] == "回答一", done
        with api_client.app.state.database.transaction() as db:
            row = db.get(Run, run["id"])
            assert row.started_at == started_at
            assert row.model_calls == 3 and row.skill_reads == 1
        steps = client.get(f"/api/runs/{run['id']}/actions").json()["items"]
        assert len([s for s in steps if s["kind"] == "tool_call"]) == 1
        assert any(s["kind"] == "model_call" and s["status"] == "unknown" for s in steps)
        expected = ["起始问", "回答一"] if prior_success else []
        assert [
            m["content"]
            for m in client.get(f"/api/conversations/{conversation['id']}/messages").json()["items"]
        ] == [*expected, "第一问", "回答一"]


def test_final_checkpoint_repairs_run_without_model_replay(api_client, migrated_config):
    skill, _, _, conversation = setup(api_client)
    run = send(api_client, conversation, "第一问").json()
    database = Path(migrated_config.database.url.database)

    def complete_checkpoint(row):
        if not row.checkpoint_id:
            return False
        values = checkpoint_values(api_client.app.state.checkpoints, row.id, row.checkpoint_id)
        return values.get("completed_run_id") == row.id

    with server(
        database,
        worker=WORKER,
        worker_args=arguments(migrated_config, skill, "--pause-before-commit"),
    ) as (_, process):
        before = wait_state(api_client, run["id"], complete_checkpoint)
        assert before.status == "running"
        assert api_client.get(f"/api/runs/{before.id}").json()["result"] is None
        process.kill()
        process.wait(timeout=5)
    # 模拟 SDK 已提交，而业务存档引用尚未更新的另一个崩溃间隙。
    with api_client.app.state.database.transaction() as db:
        row = db.get(Run, run["id"])
        row.checkpoint_id = None
    with server(
        database, worker=WORKER, worker_args=arguments(migrated_config, skill, "--forbid-model")
    ) as (client, _):
        authorize(client, api_client)
        done = wait_run(client, run["id"])
        assert done["status"] == "succeeded" and done["assistant_content"] == "回答一", done
        with api_client.app.state.database.transaction() as db:
            assert db.get(Run, run["id"]).model_calls == before.model_calls


@pytest.mark.parametrize(
    "block,status,code",
    [
        ("budget", "failed", "agent_budget_exceeded"),
        ("skill", "failed", "skill_access_revoked"),
        ("connection", "failed", "model_configuration_changed"),
        ("session", "cancelled", "actor_session_invalid"),
        ("cancel", "cancelled", None),
        ("timeout", "failed", "run_timeout"),
    ],
)
def test_restart_rechecks_permissions_limits_and_stop(
    api_client, migrated_config, block, status, code
):
    skill, connection, _, conversation = setup(api_client)
    if block == "budget":
        service = api_client.app.state.conversation_commands
        set_submission_limits(service, max_model_calls=2)
    run = send(api_client, conversation, "第一问").json()
    database = Path(migrated_config.database.url.database)
    with server(
        database,
        worker=WORKER,
        worker_args=arguments(migrated_config, skill),
        pause_after_lookup=True,
    ) as (_, process):
        wait_state(api_client, run["id"], lambda row: row.model_calls == 2)
        process.kill()
        process.wait(timeout=5)
    if block == "skill":
        patch_current(api_client, f"/api/skills/{skill['id']}", json={"is_active": False})
    elif block == "connection":
        patch_current(
            api_client, f"/api/model-connections/{connection['id']}", json={"model_id": "changed"}
        )
    elif block == "cancel":
        assert api_client.post(f"/api/runs/{run['id']}/cancel", json={}).status_code == 200
    elif block in ("session", "timeout"):
        with api_client.app.state.database.transaction() as db:
            row = db.get(Run, run["id"])
            if block == "session":
                db.get(AuthSession, row.initiated_by_session_id).revoked_at = utc_now()
            else:
                row.started_at = utc_now() - timedelta(
                    seconds=row.config_snapshot["run_timeout"] + 1
                )
        if block == "session":
            assert (
                api_client.post(
                    "/api/auth/login", json={"username": "admin", "password": "test-password-auth"}
                ).status_code
                == 200
            )
    with server(
        database, worker=WORKER, worker_args=arguments(migrated_config, skill, "--forbid-model")
    ) as (client, _):
        authorize(client, api_client)
        done = wait_run(client, run["id"])
        assert done["status"] == status, done
        assert (done["error"]["code"] if done["error"] else None) == code, done
        assert done["assistant_content"] == ""
        with api_client.app.state.database.transaction() as db:
            assert db.get(Run, run["id"]).model_calls == 2
