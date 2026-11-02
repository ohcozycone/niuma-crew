"""First-message acceptance and read-only recovery use real isolated persistence."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from configuration_helpers import patch_current
from test_conversations import setup_agent

from app.auth.permissions import ROLE_PERMISSIONS


def test_first_send_creates_conversation_and_replays_same_request(api_client):
    _, agent, _ = setup_agent(api_client)
    conversation_id, request_id = str(uuid4()), str(uuid4())
    payload = {"agent_id": agent["id"], "client_request_id": request_id, "content": "第一条消息"}
    path = f"/api/conversations/{conversation_id}"
    assert api_client.get(path).status_code == 404
    first = api_client.post(f"{path}/runs", json=payload)
    assert first.status_code == 202, first.text
    run = first.json()
    assert run["conversation_id"] == conversation_id
    assert run["action_count"] == 0 and run["current_activity"] is None
    assert api_client.get(path).json()["agent_id"] == agent["id"]
    repeated = api_client.post(f"{path}/runs", json=payload)
    assert repeated.status_code == 200 and repeated.json()["id"] == run["id"]
    lookup = api_client.get(f"{path}/requests/{request_id}")
    assert lookup.status_code == 200 and lookup.json()["id"] == run["id"]
    assert api_client.get(f"{path}/requests/{uuid4()}").json() is None
    assert len(api_client.get(f"{path}/messages").json()["items"]) == 2
    assert (
        api_client.post(f"{path}/runs", json={**payload, "content": "改变输入"}).status_code == 409
    )


def test_first_send_rejection_rolls_back_new_conversation(api_client):
    _, agent, _ = setup_agent(api_client)
    conversation_id = str(uuid4())
    payload = {"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "不能接受"}
    api_client.app.state.runtime_status.phase = "degraded"
    response = api_client.post(f"/api/conversations/{conversation_id}/runs", json=payload)
    assert response.status_code == 503
    assert api_client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_first_send_duplicate_requests_are_atomic(api_client):
    _, agent, _ = setup_agent(api_client)
    conversation_id = str(uuid4())
    payload = {"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "并发首条"}
    path = f"/api/conversations/{conversation_id}/runs"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: api_client.post(path, json=payload), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 202]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert (
        len(api_client.get(f"/api/conversations/{conversation_id}/messages").json()["items"]) == 2
    )


def test_existing_conversation_cannot_change_agent_on_submission(api_client):
    _, first, conversation = setup_agent(api_client)
    _, other, _ = setup_agent(api_client)
    path = f"/api/conversations/{conversation['id']}/runs"
    response = api_client.post(
        path, json={"agent_id": other["id"], "client_request_id": str(uuid4()), "content": "换员工"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "conversation_agent_conflict"
    assert (
        api_client.get(f"/api/conversations/{conversation['id']}").json()["agent_id"] == first["id"]
    )


def test_invalid_agent_does_not_leave_an_empty_conversation(api_client):
    _, agent, _ = setup_agent(api_client)
    patch_current(api_client, f"/api/agents/{agent['id']}", json={"is_active": False})
    conversation_id = str(uuid4())
    response = api_client.post(
        f"/api/conversations/{conversation_id}/runs",
        json={"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "不可用"},
    )
    assert response.status_code == 409
    assert api_client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_activity_is_actual_running_step_and_history_contains_full_run(api_client):
    _, agent, _ = setup_agent(api_client)
    conversation_id = str(uuid4())
    response = api_client.post(
        f"/api/conversations/{conversation_id}/runs",
        json={"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "读取方法"},
    )
    run_id = response.json()["id"]
    store = api_client.app.state.execution_store
    assert store.claim(run_id)
    store.start_action(run_id, "model:1", "model_call", {"round": 1, "has_tool_calls": True})
    first = api_client.get(f"/api/runs/{run_id}").json()
    assert first["action_count"] == 1
    assert first["current_activity"]["kind"] == "model_call"
    store.finish_action(run_id, "model:1")
    assert api_client.get(f"/api/runs/{run_id}").json()["current_activity"] is None
    store.start_action(run_id, "tool:1", "tool_call", {"tool": "read_file", "name": "整理方法"})
    current = api_client.get(f"/api/runs/{run_id}").json()
    assert current["current_activity"]["tool"] == "read_file" and current["action_count"] == 2
    history = api_client.get(f"/api/conversations/{conversation_id}/messages").json()["items"][-1]
    assert history["run"] == current
    assert history["run"]["started_at"] is not None
    assert len(history["run"]["actions"]) == 2


def test_first_send_requires_create_permission_and_request_lookup_requires_read(
    api_client, monkeypatch
):
    _, agent, _ = setup_agent(api_client)
    monkeypatch.setitem(
        ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"conversations:create"}
    )
    conversation_id = str(uuid4())
    payload = {"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "无创建权限"}
    assert (
        api_client.post(f"/api/conversations/{conversation_id}/runs", json=payload).status_code
        == 403
    )
    assert api_client.get(f"/api/conversations/{conversation_id}").status_code == 404
    monkeypatch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"runs:read"})
    assert (
        api_client.get(
            f"/api/conversations/{conversation_id}/requests/{payload['client_request_id']}"
        ).status_code
        == 403
    )
