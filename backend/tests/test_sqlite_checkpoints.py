"""真实 HTTP、SQLite 和新后端进程；模型和工具均为确定性本机替身。"""

import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

QUESTION = "上海住宿标准多少？"
FOLLOWUP = "住三晚呢？"
BACKEND = Path(__file__).resolve().parents[1]


@contextmanager
def server(database: Path, *, pause_after_lookup=False, worker=None, worker_args=()):
    with socket.socket() as listener, (database.parent / f"server-{uuid4()}.log").open("w+") as log:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        entry = [str(worker)] if worker else [str(BACKEND / "tests/support/checkpoint_server.py")]
        command = [
            sys.executable,
            *entry,
            "--db",
            str(database),
            "--fd",
            str(listener.fileno()),
            *worker_args,
        ]
        if pause_after_lookup:
            command.append("--pause-after-lookup")
        process = subprocess.Popen(
            command,
            cwd=BACKEND,
            pass_fds=(listener.fileno(),),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}",
                timeout=2,
                trust_env=False,
            ) as client:
                if worker:
                    from sqlalchemy import URL

                    from app.infrastructure.database.session import Database, DatabaseConfig

                    client.database = Database(
                        DatabaseConfig(URL.create("sqlite+pysqlite", database=str(database)))
                    )
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.02)
                else:
                    raise AssertionError("验证后端启动超时。")
                if process.poll() is not None:
                    log.seek(0)
                    raise AssertionError(log.read())
                try:
                    yield client, process
                finally:
                    if worker:
                        client.database.close()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def history(client, thread_id):
    response = client.get(f"/threads/{thread_id}/history")
    assert response.status_code == 200, response.text
    return response.json()


def wait_history(client, thread_id, *, pending=False):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        value = history(client, thread_id)
        assert value["error"] is None, value
        if pending:
            counters = client.get("/health").json()
            if value["pending_nodes"] == ["model"] and counters["model_calls"] == 2:
                return value
        elif not value["running"] and not value["pending_nodes"]:
            return value
        time.sleep(0.01)
    raise AssertionError(f"等待执行状态超时：{value}")


def send(client, thread_id, text):
    response = client.post(f"/threads/{thread_id}/messages", json={"text": text})
    assert response.status_code == 202, response.text


def test_multiturn_history_reads_and_thread_isolation(tmp_path):
    database = tmp_path / "checkpoints.sqlite"
    thread_id, other = uuid4(), uuid4()
    with server(database) as (client, _):
        assert history(client, thread_id)["messages"] == []
        send(client, thread_id, QUESTION)
        first = wait_history(client, thread_id)
        assert [m["role"] for m in first["messages"]] == ["user", "assistant"]
        assert first["messages"][-1]["text"] == "上海住宿上限为500元/晚。"

        send(client, thread_id, FOLLOWUP)
        complete = wait_history(client, thread_id)
        assert [m["text"] for m in complete["messages"]] == [
            QUESTION,
            "上海住宿上限为500元/晚。",
            FOLLOWUP,
            "按上海每晚500元计算，三晚共1500元。",
        ]
        assert complete["messages"][:2] == first["messages"]
        assert "INTERNAL_POLICY" not in str(complete) and "内部执行文字" not in str(complete)
        counters = client.get("/health").json()
        assert counters["model_calls"] == 3 and counters["tool_calls"] == 1
        for _ in range(3):
            assert history(client, thread_id) == complete
        assert client.get("/health").json() == counters

        send(client, other, FOLLOWUP)
        isolated = wait_history(client, other)
        assert isolated["messages"][-1]["text"] == "尚未读取住宿标准，请先查询。"
        assert history(client, thread_id) == complete
        assert client.post(f"/threads/{thread_id}/resume").status_code == 409
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "checkpoints" in tables and "messages" not in tables


def test_new_backend_process_reads_history_and_continues_conversation(tmp_path):
    database, thread_id = tmp_path / "checkpoints.sqlite", uuid4()
    with server(database) as (client, first_process):
        send(client, thread_id, QUESTION)
        before = wait_history(client, thread_id)
        first_pid = first_process.pid
    with server(database) as (client, second_process):
        assert second_process.pid != first_pid
        assert history(client, thread_id) == before
        assert client.get("/health").json()["model_calls"] == 0
        send(client, thread_id, FOLLOWUP)
        after = wait_history(client, thread_id)
        assert after["messages"][:2] == before["messages"]
        assert after["messages"][-1]["text"] == "按上海每晚500元计算，三晚共1500元。"
        counters = client.get("/health").json()
        assert counters["model_calls"] == 1 and counters["tool_calls"] == 0


def test_killed_backend_resumes_saved_tool_result_without_repeating_tool(tmp_path):
    database, thread_id = tmp_path / "checkpoints.sqlite", uuid4()
    with server(database, pause_after_lookup=True) as (client, first_process):
        send(client, thread_id, QUESTION)
        before = wait_history(client, thread_id, pending=True)
        assert [m["text"] for m in before["messages"]] == [QUESTION]
        assert client.get("/health").json()["tool_calls"] == 1
        assert (
            client.post(f"/threads/{thread_id}/messages", json={"text": FOLLOWUP}).status_code
            == 409
        )
        first_process.kill()
        first_process.wait(timeout=5)
    with server(database) as (client, _):
        restored = history(client, thread_id)
        assert restored["messages"] == before["messages"]
        assert restored["checkpoint_id"] == before["checkpoint_id"]
        assert restored["pending_nodes"] == ["model"] and not restored["running"]
        assert client.get("/health").json()["model_calls"] == 0
        # 恢复只能消费原有 pending nodes，不能把原问题作为新输入再追加一遍。
        assert client.post(f"/threads/{thread_id}/resume").status_code == 202
        complete = wait_history(client, thread_id)
        assert [m["text"] for m in complete["messages"]] == [QUESTION, "上海住宿上限为500元/晚。"]
        counters = client.get("/health").json()
        assert counters["model_calls"] == 1 and counters["tool_calls"] == 0
        assert client.post(f"/threads/{thread_id}/resume").status_code == 409
        assert client.get("/health").json() == counters
