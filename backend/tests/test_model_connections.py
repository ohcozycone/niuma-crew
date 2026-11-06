"""Model connection lifecycle, credential boundaries and provider failure behavior."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Event
from uuid import uuid4

import httpx
import pytest
from configuration_helpers import patch_current
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.auth.models import AuthSession
from app.auth.permissions import ROLE_PERMISSIONS
from app.bootstrap import create_app
from app.infrastructure.credentials import CredentialUnavailableError, CredentialVault
from app.infrastructure.database.transactions import reserve_writer
from app.model_connections.models import ModelConnection
from app.values import utc_now

KEY = "test-only-key-not-a-real-credential"


def create(client, **overrides):
    return client.post(
        "/api/model-connections", json={"name": "Kimi 大脑", "api_key": KEY, **overrides}
    )


def test_creation_survives_another_writer_between_credential_read_and_insert(
    api_client, monkeypatch
):
    service = api_client.app.state.model_connections
    actor = api_client.app.state.auth.resolve(api_client.cookies.get("app_session"))
    prepared, release = Event(), Event()
    original = service._encrypt

    def paused_encrypt(session, key):
        value = original(session, key)
        prepared.set()
        assert release.wait(5)
        return value

    def background_write():
        with service.database.transaction() as db:
            reserve_writer(db, AuthSession.__table__)
            row = db.get(AuthSession, actor.session_id)
            row.last_seen_at = utc_now() + timedelta(seconds=1)

    monkeypatch.setattr(service, "_encrypt", paused_encrypt)
    with ThreadPoolExecutor(max_workers=2) as pool:
        creating = pool.submit(create, api_client)
        try:
            assert prepared.wait(5)
            writing = pool.submit(background_write)
            # Without a reservation this writer commits and makes the creator's
            # read snapshot stale. With it, the writer waits for creation.
            try:
                writing.result(timeout=0.25)
            except TimeoutError:
                pass
        finally:
            release.set()
        response = creating.result(timeout=5)
        writing.result(timeout=5)
    assert response.status_code == 201, response.text


def test_crud_encrypts_never_returns_secret_and_survives_restart(api_client, migrated_config):
    presets = api_client.get("/api/model-presets").json()
    assert [p["id"] for p in presets] == ["kimi-code", "zhipu", "deepseek", "siliconflow-embedding"]
    response = create(api_client)
    assert response.status_code == 201
    item = response.json()
    assert item["base_url"] == "https://api.kimi.com/coding/v1"
    assert item["model_id"] == "kimi-for-coding" and item["has_api_key"] is True
    assert "api_key" not in item and "encrypted_api_key" not in item and KEY not in response.text
    service = api_client.app.state.model_connections
    with service.database.transaction() as db:
        encrypted = db.get(ModelConnection, item["id"]).encrypted_api_key
        assert KEY not in encrypted and encrypted != KEY
    vault_path = migrated_config.model_encryption_key_file
    assert vault_path.stat().st_mode & 0o777 == 0o600
    assert service.resolve(item["id"]).api_key.get_secret_value() == KEY
    assert (
        patch_current(
            api_client, f"/api/model-connections/{item['id']}", json={"name": "新大脑"}
        ).status_code
        == 200
    )
    assert service.resolve(item["id"]).api_key.get_secret_value() == KEY
    assert (
        patch_current(
            api_client,
            f"/api/model-connections/{item['id']}",
            json={"api_key": "replacement-key", "model_id": "k3"},
        ).status_code
        == 200
    )
    with TestClient(create_app(migrated_config)) as reopened:
        reopened.cookies.update(api_client.cookies)
        assert reopened.get(f"/api/model-connections/{item['id']}").json()["name"] == "新大脑"
        assert (
            reopened.app.state.model_connections.resolve(item["id"]).api_key.get_secret_value()
            == "replacement-key"
        )
        assert reopened.app.state.model_connections.resolve(item["id"]).model_id == "k3"
    assert create(api_client, name="新大脑").status_code == 409
    assert api_client.get("/api/model-connections?limit=1").json()["total"] == 1
    assert api_client.delete(f"/api/model-connections/{item['id']}").status_code == 204
    assert api_client.get(f"/api/model-connections/{item['id']}").status_code == 404


@pytest.mark.parametrize(
    "preset_id,base_url,model_id",
    [
        ("zhipu", "https://open.bigmodel.cn/api/paas/v4", "glm-5.3"),
        ("deepseek", "https://api.deepseek.com", "deepseek-flash"),
    ],
)
def test_new_chat_presets_save_resolve_bind_and_check(
    api_client, monkeypatch, preset_id, base_url, model_id
):
    response = create(api_client, name=preset_id, preset_id=preset_id)
    assert response.status_code == 201, response.text
    item = response.json()
    assert (item["model_id"], item["base_url"], item["provider"], item["capability"]) == (
        model_id,
        base_url,
        preset_id,
        "chat",
    )
    assert KEY not in response.text
    config = api_client.app.state.model_connections.resolve(item["id"])
    assert (config.model_id, config.base_url, config.provider) == (model_id, base_url, preset_id)
    assert config.api_key.get_secret_value() == KEY
    agent = api_client.post(
        "/api/agents",
        json={"name": preset_id, "avatar_id": "admin", "model_connection_id": item["id"]},
    )
    assert agent.status_code == 201, agent.text
    original_client = httpx.Client
    status = 200

    def handle(request):
        assert request.method == "GET"
        assert str(request.url) == base_url + "/models"
        assert request.headers["authorization"] == "Bearer " + KEY
        return httpx.Response(status, json={"data": [{"id": model_id}]})

    monkeypatch.setattr(
        "app.model_connections.service.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    check = api_client.post(f"/api/model-connections/{item['id']}/test", json={})
    assert check.json()["ok"] is True
    status = 401
    rejected = api_client.post(f"/api/model-connections/{item['id']}/test", json={})
    assert rejected.json()["ok"] is False
    assert "Kimi" not in rejected.text and KEY not in rejected.text
    custom = create(api_client, name="自定义", preset_id=preset_id, model_id="custom-model")
    assert custom.status_code == 201 and custom.json()["model_id"] == "custom-model"


def test_binding_reuse_preserves_agent_context_and_prevents_deletion(api_client):
    connection = create(api_client).json()
    ids = []
    for name in ("行政", "研发"):
        agent = api_client.post(
            "/api/agents",
            json={
                "name": name,
                "avatar_id": "admin",
                "system_prompt": name,
                "model_connection_id": connection["id"],
            },
        ).json()
        ids.append(agent["id"])
        assert agent["model_connection_id"] == connection["id"]
    used = api_client.get(f"/api/model-connections/{connection['id']}").json()
    assert {e["id"] for e in used["agents"]} == set(ids)
    assert api_client.delete(f"/api/model-connections/{connection['id']}").status_code == 409
    with pytest.raises(IntegrityError):
        with api_client.app.state.database.transaction() as db:
            db.delete(db.get(ModelConnection, connection["id"]))
            db.flush()
    assert (
        patch_current(
            api_client, f"/api/agents/{ids[0]}", json={"model_connection_id": str(uuid4())}
        ).status_code
        == 404
    )
    assert api_client.get(f"/api/agents/{ids[0]}").json()["model_connection_id"] == connection["id"]
    assert (
        patch_current(api_client, f"/api/agents/{ids[0]}", json={"description": "changed"}).json()[
            "model_connection_id"
        ]
        == connection["id"]
    )
    for id in ids:
        updated = patch_current(
            api_client, f"/api/agents/{id}", json={"model_connection_id": None}
        ).json()
        assert updated["model_connection_id"] is None and updated["system_prompt"]
    assert api_client.delete(f"/api/model-connections/{connection['id']}").status_code == 204


@pytest.mark.parametrize(
    "patch",
    [
        {"api_key": ""},
        {"api_key": None},
        {"api_key": "bad key"},
        {"model_id": " "},
        {"model_id": "bad\nmodel"},
        {"base_url": "http://localhost/private"},
        {"preset_id": "unknown"},
    ],
)
def test_invalid_updates_never_echo_secrets_or_change_configuration(api_client, patch):
    item = create(api_client).json()
    response = patch_current(api_client, f"/api/model-connections/{item['id']}", json=patch)
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])
    assert KEY not in response.text
    assert (
        api_client.app.state.model_connections.resolve(item["id"]).api_key.get_secret_value() == KEY
    )


def test_auth_permissions_public_projection_and_assignment_capability(
    api_client, migrated_config, monkeypatch
):
    item = create(api_client).json()
    agent = api_client.post(
        "/api/agents",
        json={"name": "员工", "avatar_id": "admin", "model_connection_id": item["id"]},
    ).json()
    routes = [
        ("GET", "/api/model-presets"),
        ("GET", "/api/model-connections"),
        ("POST", "/api/model-connections"),
        ("GET", f"/api/model-connections/{item['id']}"),
        ("PATCH", f"/api/model-connections/{item['id']}"),
        ("DELETE", f"/api/model-connections/{item['id']}"),
        ("POST", f"/api/model-connections/{item['id']}/test"),
    ]
    with TestClient(
        create_app(migrated_config),
        headers={"Origin": "http://localhost:3000", "Content-Type": "application/json"},
    ) as visitor:
        for method, path in routes:
            assert visitor.request(method, path, json={}).status_code == 401
        visitor.post("/api/auth/guest", json={})
        for method, path in routes:
            assert visitor.request(method, path, json={}).status_code == 403
        public = visitor.get(f"/api/public/agents/{agent['id']}").json()
        assert public["model_configured"] is True
        assert "model_connection_id" not in public
    monkeypatch.setitem(
        ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"agents:assign_model"}
    )
    assert (
        patch_current(
            api_client, f"/api/agents/{agent['id']}", json={"model_connection_id": None}
        ).status_code
        == 403
    )
    assert (
        api_client.post(
            "/api/agents",
            json={"name": "拒绝", "avatar_id": "admin", "model_connection_id": item["id"]},
        ).status_code
        == 403
    )


def test_missing_or_changed_master_key_fails_without_replacing_it(api_client, migrated_config):
    item = create(api_client).json()
    path = migrated_config.model_encryption_key_file
    original = path.read_bytes()
    path.unlink()
    assert create(api_client, name="another").status_code == 503
    assert not path.exists()
    assert api_client.post(f"/api/model-connections/{item['id']}/test", json={}).status_code == 503
    path.write_bytes(Fernet.generate_key())
    assert create(api_client, name="another").status_code == 503
    path.write_bytes(original)
    assert (
        api_client.app.state.model_connections.resolve(item["id"]).api_key.get_secret_value() == KEY
    )


def test_explicit_key_is_not_repr_or_written_to_disk(api_client, migrated_config):
    configured = Fernet.generate_key().decode()
    config = replace(migrated_config, model_encryption_key=configured)
    assert configured not in repr(config)
    with TestClient(
        create_app(config),
        headers={"Origin": "http://localhost:3000", "Content-Type": "application/json"},
    ) as client:
        client.cookies.update(api_client.cookies)
        item = create(client).json()
        assert not migrated_config.model_encryption_key_file.exists()
        assert (
            client.app.state.model_connections.resolve(item["id"]).api_key.get_secret_value() == KEY
        )


def test_parallel_first_use_shares_one_complete_key(tmp_path):
    path = tmp_path / "model.key"

    def encrypt(_):
        return CredentialVault(path).encrypt(KEY, allow_create=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(encrypt, range(8)))
    assert all(CredentialVault(path).decrypt(token) == KEY for token in tokens)
    with pytest.raises(CredentialUnavailableError):
        CredentialVault(path).decrypt("damaged")


@pytest.mark.parametrize(
    "status,payload,success",
    [
        (200, {"data": [{"id": "kimi-for-coding"}]}, True),
        (200, {"data": [{"id": "other"}]}, False),
        (200, [], False),
        (401, {"secret": KEY}, False),
        (403, {}, False),
        (429, {}, False),
        (302, {}, False),
        (500, {}, False),
    ],
)
def test_provider_check_is_bounded_safe_and_does_not_generate(
    api_client, monkeypatch, status, payload, success
):
    item = create(api_client).json()
    original_client = httpx.Client

    def handle(request):
        assert str(request.url) == "https://api.kimi.com/coding/v1/models"
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.headers["user-agent"] == "AgentPlatform/0.1"
        return httpx.Response(
            status, json=payload, headers={"Location": "http://localhost/private"}
        )

    def factory(**kwargs):
        assert kwargs == {"timeout": 8, "follow_redirects": False, "trust_env": False}
        return original_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr("app.model_connections.service.httpx.Client", factory)
    response = api_client.post(f"/api/model-connections/{item['id']}/test", json={})
    assert response.status_code == 200 and response.json()["ok"] is success
    assert KEY not in response.text


def test_provider_timeout_response_limit_and_rate_limit(api_client, monkeypatch):
    item = create(api_client).json()
    original_client = httpx.Client
    attempts = ["timeout", "oversize", "invalid", "network", "ok"]

    def handle(request):
        attempt = attempts.pop(0)
        if attempt == "timeout":
            raise httpx.ReadTimeout(KEY)
        if attempt == "network":
            raise httpx.ConnectError(KEY)
        return httpx.Response(
            200,
            content=(
                b"x" * 1048577
                if attempt == "oversize"
                else b"not-json"
                if attempt == "invalid"
                else b'{"data":[]}'
            ),
        )

    monkeypatch.setattr(
        "app.model_connections.service.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    for _ in range(5):
        response = api_client.post(f"/api/model-connections/{item['id']}/test", json={})
        assert (
            response.status_code == 200 and not response.json()["ok"] and KEY not in response.text
        )
    assert api_client.post(f"/api/model-connections/{item['id']}/test", json={}).status_code == 429


def test_connection_revisions_and_disabled_bindings(api_client):
    item = create(api_client).json()
    path = f"/api/model-connections/{item['id']}"
    changed = api_client.patch(
        path,
        json={"expected_config_revision": 1, "expected_credential_revision": 1, "enabled": False},
    ).json()
    assert changed["config_revision"] == 2 and changed["credential_revision"] == 1
    stale = api_client.patch(
        path,
        json={
            "expected_config_revision": 1,
            "expected_credential_revision": 1,
            "api_key": "replacement-key",
        },
    )
    assert stale.status_code == 409
    assert api_client.get(path).json() == changed
    rejected = api_client.post(
        "/api/agents",
        json={"name": "不可绑定", "avatar_id": "admin", "model_connection_id": item["id"]},
    )
    assert rejected.status_code == 409
    rotated = api_client.patch(
        path,
        json={
            "expected_config_revision": 2,
            "expected_credential_revision": 1,
            "api_key": "replacement-key",
        },
    ).json()
    assert rotated["config_revision"] == 2 and rotated["credential_revision"] == 2
    assert (
        api_client.patch(
            path,
            json={
                "expected_config_revision": 2,
                "expected_credential_revision": 2,
                "enabled": False,
            },
        ).json()["config_revision"]
        == 2
    )
