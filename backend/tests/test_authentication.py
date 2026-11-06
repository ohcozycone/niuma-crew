"""Authentication, projection and authorization boundaries against real migrated SQLite."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from configuration_helpers import patch_current
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.api.rate_limit import RateLimiter
from app.auth.config import AuthConfig
from app.auth.models import AuthSession, User
from app.auth.permissions import ROLE_PERMISSIONS
from app.auth.service import AuthService, token_digest
from app.bootstrap import create_app
from app.errors import AuthenticationError, RateLimitError
from app.values import utc_now

HEADERS = {"Origin": "http://localhost:3000", "Content-Type": "application/json"}
PASSWORD = "test-password-auth"


def browser(config):
    return TestClient(create_app(config), headers=HEADERS)


def login(client, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": "admin", "password": password})


@pytest.mark.parametrize("length", [8, 20])
def test_password_boundaries_support_creation_reset_and_login(migrated_config, length):
    with browser(migrated_config) as client:
        service = client.app.state.auth
        service.initialize_admin("admin", "a" * length)
        assert login(client, "a" * length).status_code == 200
        service.maintain_user("admin", "reset-password", "b" * length)
        assert client.get("/api/auth/me").status_code == 401
        assert login(client, "a" * length).status_code == 401
        assert login(client, "b" * length).status_code == 200


@pytest.mark.parametrize("length", [7, 21])
def test_invalid_password_length_preserves_account_and_session(migrated_config, length):
    with browser(migrated_config) as client:
        service = client.app.state.auth
        with pytest.raises(ValueError, match="8～20"):
            service.initialize_admin("admin", "a" * length)
        with service.database.transaction() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 0
        service.initialize_admin("admin", PASSWORD)
        assert login(client).status_code == 200
        with pytest.raises(ValueError, match="8～20"):
            service.maintain_user("admin", "reset-password", "b" * length)
        assert client.get("/api/auth/me").status_code == 200
        assert login(client).status_code == 200


def test_session_cookie_logout_rotation_and_restart(api_client, migrated_config):
    original = api_client.cookies.get("app_session")
    with browser(migrated_config) as guest:
        response = guest.post("/api/auth/guest", json={})
        token = guest.cookies.get("app_session")
        assert response.json()["actor"] == {"kind": "guest", "user": None}
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=lax" in response.headers["set-cookie"]
        assert "Max-Age=" in response.headers["set-cookie"]
        assert "token" not in response.text
        assert guest.post("/api/auth/guest", json={}).headers.get("set-cookie") is None
        assert guest.cookies.get("app_session") == token
        assert login(guest).status_code == 200
        assert guest.cookies.get("app_session") != token
        database = guest.app.state.database
        with database.transaction() as db:
            stored = db.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_digest(token))
            )
            assert stored.revoked_at is not None
            assert db.scalar(select(User)).password_hash.startswith("$argon2id$")
        # Guest entry never downgrades an already signed-in account.
        assert guest.post("/api/auth/guest", json={}).json()["actor"]["kind"] == "user"
        current = guest.cookies.get("app_session")
        assert guest.post("/api/auth/logout", json={}).status_code == 204
        guest.cookies.set("app_session", current)
        assert guest.get("/api/auth/me").status_code == 401
        assert guest.post("/api/auth/logout", json={}).status_code == 204
    with browser(migrated_config) as reopened:
        reopened.cookies.set("app_session", original)
        assert reopened.get("/api/auth/me").json()["actor"]["user"]["username"] == "admin"


def test_guest_reads_same_records_without_private_configuration(api_client, migrated_config):
    skill = api_client.post(
        "/api/skills", json={"name": "摘要", "instructions": "PRIVATE_INSTRUCTIONS"}
    ).json()
    agent = api_client.post(
        "/api/agents",
        json={
            "name": "员工",
            "avatar_id": "admin",
            "system_prompt": "PRIVATE_PROMPT",
            "is_active": False,
            "is_favorite": True,
            "skill_assignments": [{"skill_id": skill_id} for skill_id in [skill["id"]]],
        },
    ).json()
    with browser(migrated_config) as guest:
        assert guest.get("/api/public/agents").status_code == 401
        guest.post("/api/auth/guest", json={})
        response = guest.get(
            "/api/public/agents", params={"is_active": False, "skill_id": skill["id"]}
        )
        assert response.headers["cache-control"] == "no-store"
        public = response.json()["items"][0]
        assert public["id"] == agent["id"] and public["model_configured"] is False
        assert public["is_favorite"] is True
        assert public["skill_ids"] == [skill["id"]]
        assert (
            public["resource_counts"]
            == agent["resource_counts"]
            == {"skills": 1, "tools": 0, "knowledge_bases": 0}
        )
        assert set(public) == {
            "id",
            "code",
            "name",
            "avatar_id",
            "category",
            "description",
            "role_label",
            "is_active",
            "is_favorite",
            "example_tasks",
            "deliverables",
            "skill_ids",
            "model_configured",
            "resource_counts",
        }
        assert guest.get(f"/api/public/agents/{agent['id']}").json() == public
        for path in ("/api/public/skills", f"/api/public/skills/{skill['id']}"):
            result = guest.get(path)
            assert result.status_code == 200
            assert "instructions" not in result.text
        assert guest.get(f"/api/public/agents/{uuid4()}").status_code == 404
        assert guest.get("/api/public/agents?limit=0").status_code == 422
        assert guest.get("/api/public/agents?offset=10").json()["total"] == 1
        assert guest.get("/api/public/agents?is_active=true").json()["total"] == 0


@pytest.mark.parametrize("kind,status", [("anonymous", 401), ("guest", 403)])
def test_all_management_entrypoints_deny_unprivileged_access(
    api_client, migrated_config, kind, status
):
    agent = api_client.post("/api/agents", json={"name": "不可修改", "avatar_id": "admin"}).json()
    skill = api_client.post("/api/skills", json={"name": "不可删除"}).json()
    agent_path = f"/api/agents/{agent['id']}"
    skill_path = f"/api/skills/{skill['id']}"
    calls = [
        ("GET", "/api/agents", None),
        ("GET", agent_path, None),
        ("POST", "/api/agents", {"name": "非法", "avatar_id": "admin"}),
        ("PATCH", agent_path, {"is_active": False, "is_favorite": True}),
        (
            "PATCH",
            agent_path,
            {"skill_assignments": [{"skill_id": skill_id} for skill_id in [skill["id"]]]},
        ),
        ("DELETE", agent_path, {}),
        ("GET", "/api/skills", None),
        ("GET", skill_path, None),
        ("POST", "/api/skills", {"name": "非法"}),
        ("PATCH", skill_path, {"name": "非法"}),
        ("DELETE", skill_path, {}),
    ]
    with browser(migrated_config) as visitor:
        if kind == "guest":
            visitor.post("/api/auth/guest", json={})
        for method, path, payload in calls:
            response = visitor.request(method, path, json=payload)
            assert response.status_code == status, (method, path, response.text)
    assert api_client.get(agent_path).json() == agent
    assert api_client.get(skill_path).json() == skill


def test_assignment_permission_also_applies_to_patch_and_create(api_client, monkeypatch):
    agent = api_client.post("/api/agents", json={"name": "员工", "avatar_id": "admin"}).json()
    monkeypatch.setitem(
        ROLE_PERMISSIONS, "admin", ROLE_PERMISSIONS["admin"] - {"agents:assign_skills"}
    )
    assert (
        patch_current(
            api_client,
            f"/api/agents/{agent['id']}",
            json={"skill_assignments": [{"skill_id": skill_id} for skill_id in []]},
        ).status_code
        == 403
    )
    assert (
        api_client.post(
            "/api/agents",
            json={
                "name": "员工",
                "avatar_id": "admin",
                "skill_assignments": [{"skill_id": skill_id} for skill_id in []],
            },
        ).status_code
        == 403
    )
    assert (
        patch_current(
            api_client, f"/api/agents/{agent['id']}", json={"name": "允许改名"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "https://localhost:3000",
        "http://localhost:3000.evil.test",
        "http://localhost:3000/path",
        "http://evil.test",
    ],
)
def test_csrf_protection_includes_login_guest_logout_and_business_writes(api_client, origin):
    headers = {"Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = origin
    # Replace, rather than merge, the fixture's trusted Origin.
    api_client.headers.clear()
    for path, payload in [
        ("/api/auth/login", {"username": "admin", "password": PASSWORD}),
        ("/api/auth/guest", {}),
        ("/api/auth/logout", {}),
        ("/api/skills", {"name": "blocked"}),
    ]:
        response = api_client.post(path, json=payload, headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "invalid_origin"


def test_credentials_validation_never_echoes_secrets(api_client):
    assert (
        login(api_client, "wrong").json()
        == api_client.post(
            "/api/auth/login", json={"username": "missing", "password": "wrong"}
        ).json()
    )
    secret = "sensitive-not-to-echo"
    response = api_client.post(
        "/api/auth/login", json={"username": {}, "password": secret, "extra": secret}
    )
    assert response.status_code == 422 and secret not in response.text
    assert (
        api_client.post(
            "/api/auth/login", content="{}", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )
    assert api_client.post("/api/auth/login", content="x" * 9000).status_code == 413


def test_absolute_idle_revocation_and_account_maintenance(api_client, migrated_config):
    service = api_client.app.state.auth
    token = api_client.cookies.get("app_session")
    now = utc_now()
    fixed = AuthService(
        service.database,
        replace(service.config, max_age_seconds=100, idle_timeout_seconds=10),
        lambda: now,
    )
    actor, short = fixed.login("admin", PASSWORD, None)
    now += timedelta(seconds=11)
    with pytest.raises(AuthenticationError):
        fixed.resolve(short)
    assert service.resolve(token).user_id == actor.user_id
    fixed.maintain_user("admin", "disable-user")
    assert api_client.get("/api/auth/me").status_code == 401
    assert login(api_client).status_code == 401
    fixed.maintain_user("admin", "enable-user")
    assert api_client.get("/api/auth/me").status_code == 401
    assert login(api_client).status_code == 200
    fixed.maintain_user("admin", "reset-password", "new-test-password")
    assert api_client.get("/api/auth/me").status_code == 401
    assert login(api_client).status_code == 401
    assert login(api_client, "new-test-password").status_code == 200
    with pytest.raises(ValueError, match="已经初始化"):
        fixed.initialize_admin("another", PASSWORD)
    # Absolute expiry still applies when activity was recorded just before it.
    fresh, short = fixed.login("admin", "new-test-password", None)
    now = fresh.expires_at
    with service.database.transaction() as db:
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == fresh.session_id)
            .values(last_seen_at=now - timedelta(seconds=1))
        )
    with pytest.raises(AuthenticationError):
        fixed.resolve(short)
    assert fixed.cleanup() >= 1


def test_guest_absolute_expiry_and_user_idle_touch(api_client):
    base = api_client.app.state.auth
    now = utc_now()
    service = AuthService(
        base.database,
        replace(
            base.config, max_age_seconds=100, idle_timeout_seconds=10, guest_max_age_seconds=15
        ),
        lambda: now,
    )
    user, token = service.login("admin", PASSWORD, None)
    guest, guest_token = service.guest(None)
    now += timedelta(seconds=5)
    assert service.resolve(token).user_id == user.user_id
    now += timedelta(seconds=6)
    assert service.resolve(token).user_id == user.user_id  # idle activity was persisted
    assert service.resolve(guest_token).session_id == guest.session_id
    now += timedelta(seconds=5)
    with pytest.raises(AuthenticationError):
        service.resolve(guest_token)


def test_cli_initialization_and_password_reset_do_not_echo_credentials(
    migrated_config, monkeypatch, capsys
):
    from app.auth import cli

    monkeypatch.setattr(cli, "load_config", lambda: migrated_config)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: PASSWORD)
    monkeypatch.setattr("sys.argv", ["auth", "create-admin", "Admin"])
    cli.main()
    assert PASSWORD not in capsys.readouterr().out
    with browser(migrated_config) as client:
        assert login(client).status_code == 200
        monkeypatch.setattr("sys.argv", ["auth", "revoke-sessions", "admin"])
        cli.main()
        assert client.get("/api/auth/me").status_code == 401


def test_rate_limiter_is_bounded_and_forwarded_headers_do_not_bypass_it(migrated_config):
    with browser(migrated_config) as client:
        for i in range(20):
            assert (
                client.post(
                    "/api/auth/guest", json={}, headers={"X-Forwarded-For": f"192.0.2.{i}"}
                ).status_code
                == 200
            )
        blocked = client.post("/api/auth/guest", json={})
        assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
        with client.app.state.database.transaction() as db:
            assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
    now = 0
    limiter = RateLimiter(lambda: now, capacity=1)
    limiter.consume("one", 1, 10)
    with pytest.raises(RateLimitError):
        limiter.consume("two", 1, 10)
    now = 11
    limiter.consume("two", 1, 10)


@pytest.mark.parametrize(
    "values",
    [
        {"allowed_origins": ()},
        {"allowed_origins": ("http://example.com",)},
        {"allowed_origins": ("https://example.com/path",), "cookie_secure": True},
        {"cookie_secure": True},
        {"idle_timeout_seconds": 0},
        {"max_age_seconds": 10},
    ],
)
def test_invalid_auth_configuration_fails_closed(values):
    with pytest.raises(ValueError):
        AuthConfig(**values)


def test_secure_cookie_and_production_api_docs(migrated_config):
    config = replace(
        migrated_config,
        auth=AuthConfig(allowed_origins=("https://app.example",), cookie_secure=True),
    )
    with TestClient(
        create_app(config),
        base_url="https://app.example",
        headers={"Origin": "https://app.example"},
    ) as client:
        response = client.post("/api/auth/guest", json={})
        assert "; Secure" in response.headers["set-cookie"]
        assert client.get("/api/auth/me").status_code == 200
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
