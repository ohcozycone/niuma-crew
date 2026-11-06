"""First-message acceptance and read-only recovery use real isolated persistence."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from configuration_helpers import patch_current
from run_helpers import active_step, read_reply
from test_conversations import setup_agent

from app.auth.permissions import ROLE_PERMISSIONS


def test_first_send_creates_conversation_and_replays_same_request(api_client):
    _, agent, _ = setup_agent(api_client)
    request_id = str(uuid4())
    payload = {"agent_id": agent["id"], "client_request_id": request_id, "content": "第一条消息"}
    first = api_client.post("/api/conversations", json=payload)
    assert first.status_code == 202, first.text
    value = first.json()
    conversation_id = value["conversation"]["id"]
    path = f"/api/conversations/{conversation_id}"
    run = value["response"]
    assert len(conversation_id) == 12 and run["conversation_id"] == conversation_id
    assert len(run["steps"]) == 0 and active_step(run) is None
    assert api_client.get(path + "/snapshot").json()["conversation"]["agent_id"] == agent["id"]
    repeated = api_client.post("/api/conversations", json=payload)
    assert repeated.status_code == 200 and repeated.json()["response"]["id"] == run["id"]
    lookup = api_client.get(f"/api/conversations/requests/{request_id}")
    assert lookup.status_code == 200 and lookup.json()["response"]["id"] == run["id"]
    assert api_client.get(f"/api/conversations/requests/{uuid4()}").json() is None
    assert len(api_client.get(f"{path}/messages").json()["items"]) == 2
    assert (
        api_client.post("/api/conversations", json={**payload, "content": "改变输入"}).status_code
        == 409
    )


def test_first_send_rejection_rolls_back_new_conversation(api_client):
    _, agent, _ = setup_agent(api_client)
    before = api_client.get("/api/conversations").json()["total"]
    payload = {"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "不能接受"}
    api_client.app.state.runtime_status.phase = "degraded"
    response = api_client.post("/api/conversations", json=payload)
    assert response.status_code == 503
    assert api_client.get("/api/conversations").json()["total"] == before
    assert (
        api_client.get(f"/api/conversations/requests/{payload['client_request_id']}").json() is None
    )


def test_first_send_duplicate_requests_are_atomic(api_client):
    _, agent, _ = setup_agent(api_client)
    payload = {"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "并发首条"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: api_client.post("/api/conversations", json=payload), range(2))
        )
    assert sorted(response.status_code for response in responses) == [200, 202]
    assert responses[0].json()["response"]["id"] == responses[1].json()["response"]["id"]
    conversation_id = responses[0].json()["conversation"]["id"]
    assert (
        len(api_client.get(f"/api/conversations/{conversation_id}/messages").json()["items"]) == 2
    )


def test_existing_conversation_cannot_change_agent_on_submission(api_client):
    _, first, conversation = setup_agent(api_client)
    _, other, _ = setup_agent(api_client)
    path = f"/api/conversations/{conversation['id']}/messages"
    response = api_client.post(
        path, json={"agent_id": other["id"], "client_request_id": str(uuid4()), "content": "换员工"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "conversation_agent_conflict"
    assert (
        api_client.get(f"/api/conversations/{conversation['id']}" + "/snapshot").json()[
            "conversation"
        ]["agent_id"]
        == first["id"]
    )


def test_invalid_agent_does_not_leave_an_empty_conversation(api_client):
    _, agent, _ = setup_agent(api_client)
    patch_current(api_client, f"/api/agents/{agent['id']}", json={"is_active": False})
    before = api_client.get("/api/conversations").json()["total"]
    response = api_client.post(
        "/api/conversations",
        json={"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "不可用"},
    )
    assert response.status_code == 409
    assert api_client.get("/api/conversations").json()["total"] == before


def test_activity_is_actual_running_step_and_history_contains_full_run(api_client):
    _, agent, _ = setup_agent(api_client)
    response = api_client.post(
        "/api/conversations",
        json={"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "读取方法"},
    )
    conversation_id = response.json()["conversation"]["id"]
    run_id = response.json()["response"]["id"]
    store = api_client.app.state.run_worker.store
    assert store.claim(run_id)
    store.start_action(
        run_id,
        "model:1",
        "model_call",
        {"round": 1, "has_tool_calls": True},
    )
    first = read_reply(api_client, run_id)
    assert len(first["steps"]) == 1
    assert active_step(first)["kind"] == "model_call"
    store.finish_action(run_id, "model:1")
    assert active_step(read_reply(api_client, run_id)) is None
    store.start_action(
        run_id,
        "tool:1",
        "tool_call",
        {"tool": "read_file", "name": "整理方法"},
    )
    current = read_reply(api_client, run_id)
    assert (
        active_step(current)["safe_details"]["tool"] == "read_file" and len(current["steps"]) == 2
    )
    history = api_client.get(f"/api/conversations/{conversation_id}/messages").json()["items"][-1]
    assert history == current
    assert history["started_at"] is not None
    assert len(history["steps"]) == 2


def test_first_send_requires_create_permission_and_request_lookup_requires_read(
    api_client, monkeypatch
):
    _, agent, _ = setup_agent(api_client)
    monkeypatch.setitem(
        ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"conversations:create"}
    )
    before = api_client.get("/api/conversations").json()["total"]
    payload = {"agent_id": agent["id"], "client_request_id": str(uuid4()), "content": "无创建权限"}
    assert api_client.post("/api/conversations", json=payload).status_code == 403
    assert api_client.get("/api/conversations").json()["total"] == before
    monkeypatch.setitem(ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"runs:read"})
    assert (
        api_client.get(f"/api/conversations/requests/{payload['client_request_id']}").status_code
        == 403
    )
