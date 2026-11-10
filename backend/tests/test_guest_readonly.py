from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_knowledge_library import create, process, upload

from app.common.errors import PermissionDeniedError
from app.resources.knowledge.schemas import LibraryUpdate, ProcessingRequest


def test_guest_reads_configuration_but_cannot_mutate_or_call_models(api_client):
    connection = api_client.post(
        "/api/model-connections", json={"name": "可查看的大脑", "api_key": "private-key-fixture"}
    ).json()
    agent = api_client.post(
        "/api/agents", json={"name": "只读员工", "avatar_id": "admin", "system_prompt": "工作方法"}
    ).json()
    paths = [
        "/api/agents",
        f"/api/agents/{agent['id']}/usage",
        f"/api/agents/{agent['id']}",
        "/api/skills",
        "/api/capabilities",
        "/api/model-connections",
        "/api/model-presets",
        "/api/mcp-services",
        "/api/tool-connections",
        "/api/tool-capabilities",
        "/api/organization-rules",
        "/api/configuration-summary",
        "/api/evaluations/suites",
        f"/api/evaluations?agent_id={agent['id']}",
    ]
    with TestClient(api_client.app, headers={"Origin": "http://localhost:3000"}) as guest:
        for path in paths:
            assert guest.get(path).status_code == 401, path
        identity = guest.post("/api/auth/guest", json={}).json()
        assert "resources:read_all" in identity["permissions"]
        assert "resources:all" not in identity["permissions"]
        for path in paths:
            response = guest.get(path)
            assert response.status_code == 200, (path, response.text)
            assert "private-key-fixture" not in response.text
        for method, path in [
            ("POST", "/api/agents"),
            ("PATCH", f"/api/agents/{agent['id']}"),
            ("DELETE", f"/api/agents/{agent['id']}"),
            ("POST", "/api/skills"),
            ("PUT", "/api/organization-rules"),
            ("POST", "/api/tool-connections"),
            ("POST", "/api/mcp-services"),
            ("POST", "/api/evaluations"),
            ("POST", f"/api/model-connections/{connection['id']}/test"),
            ("POST", "/api/conversations"),
        ]:
            assert guest.request(method, path, json={}).status_code == 403, (method, path)
        assert guest.get(f"/api/agents/{agent['id']}").json() == agent


def test_guest_reads_knowledge_and_keyword_search_but_cannot_change_it(api_client):
    kb = create(api_client)["id"]
    doc = upload(api_client, kb).json()["id"]
    process(api_client, kb)
    path = f"/api/knowledge-bases/{kb}"
    knowledge = api_client.app.state
    # 共用应用但使用独立 Cookie，不能继承管理员身份。
    with TestClient(api_client.app, headers={"Origin": "http://localhost:3000"}) as guest:
        guest.post("/api/auth/guest", json={})
        actor = api_client.app.state.auth.resolve(guest.cookies.get("app_session"))
        for url in [
            "/api/knowledge-bases/embedding-connections",
            "/api/knowledge-bases",
            path,
            path + "/documents",
            path + "/processing",
            path + f"/documents/{doc}",
            path + f"/documents/{doc}/original",
        ]:
            response = guest.get(url)
            assert response.status_code == 200, (url, response.text)
        detail = guest.get(path + f"/documents/{doc}").json()
        chunk = detail["chunks"][0]["id"]
        assert guest.get(path + f"/documents/{doc}/chunks/{chunk}").status_code == 200
        result = guest.post(path + "/search", json={"question": "一等座 批准"})
        assert result.status_code == 200 and result.json()["hits"]
        for strategy in ("vector", "hybrid"):
            assert (
                guest.post(
                    path + "/search", json={"question": "批准", "strategy": strategy}
                ).status_code
                == 403
            )
        for method, suffix in [
            ("PATCH", ""),
            ("POST", "/documents"),
            ("DELETE", f"/documents/{doc}"),
            ("POST", "/processing"),
            ("POST", "/vector-index"),
            ("DELETE", "/vector-index"),
        ]:
            assert guest.request(method, path + suffix, json={}).status_code == 403
        with pytest.raises(PermissionDeniedError):
            knowledge.knowledge_libraries.update(
                actor, kb, LibraryUpdate(name="禁止覆盖", description="", expected_revision=1)
            )
        with pytest.raises(PermissionDeniedError):
            knowledge.knowledge_processing.submit(
                actor, kb, ProcessingRequest(client_request_id=uuid4())
            )
        with pytest.raises(PermissionDeniedError):
            knowledge.knowledge_vectors.clear(actor, kb)
        assert guest.post("/api/auth/logout", json={}).status_code == 204
        assert guest.get(path).status_code == 401
