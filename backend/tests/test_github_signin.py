"""Real migrated accounts/sessions with GitHub HTTP responses controlled offline."""

import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from app.auth.config import AuthConfig, GitHubOAuthConfig, load_github_oauth_config
from app.auth.github import OAUTH_COOKIE, OAUTH_COOKIE_PATH, OAUTH_TTL, safe_return_path
from app.auth.models import AuthSession, ExternalIdentity, User
from app.auth.permissions import ROLE_PERMISSIONS
from app.auth.service import token_digest
from app.bootstrap import create_app
from app.errors import InvalidInputError, RateLimitError, ServiceUnavailableError
from app.values import utc_now

HEADERS = {"Origin": "http://localhost:3000", "Content-Type": "application/json"}
GITHUB_CONFIG = GitHubOAuthConfig(
    "test-client", "test-client-secret", "http://localhost:3000/api/auth/github/callback"
)


@pytest.fixture
def github_client(migrated_config):
    config = replace(migrated_config, github_oauth=GITHUB_CONFIG)
    with TestClient(create_app(config), headers=HEADERS, follow_redirects=False) as client:
        upstream = {
            "profile": {"id": 123, "login": "GitHubUser", "email": "not-collected@example.test"},
            "requests": [],
            "used": set(),
        }

        def respond(request):
            upstream["requests"].append(request)
            if request.url == "https://github.com/login/oauth/access_token":
                data = parse_qs(request.content.decode())
                code = data["code"][0]
                if code in upstream["used"]:
                    return httpx.Response(200, json={"error": "bad_verification_code"})
                upstream["used"].add(code)
                return httpx.Response(
                    200, json={"access_token": "gho_test", "refresh_token": "not-stored"}
                )
            assert str(request.url) == "https://api.github.com/user"
            assert request.headers["Authorization"] == "Bearer gho_test"
            return httpx.Response(200, json=upstream["profile"])

        client.app.state.github_oauth.transport = httpx.MockTransport(respond)
        yield client, upstream


def start(client, next_path="/agents?filter=favorites"):
    response = client.post("/api/auth/github", json={"next": next_path})
    assert response.status_code == 200
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query, keep_blank_values=True)
    return query, client.cookies.get(OAUTH_COOKIE)


def complete(client, query, **params):
    return client.get(
        "/api/auth/github/callback",
        params={"state": query["state"][0], "code": str(uuid4()), **params},
    )


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_disabled_provider_keeps_existing_entries_available(migrated_config):
    with TestClient(create_app(migrated_config), headers=HEADERS) as client:
        assert client.get("/api/auth/providers").json() == {"github": {"enabled": False}}
        assert client.post("/api/auth/github", json={}).status_code == 503
        assert client.post("/api/auth/guest", json={}).status_code == 200
        client.app.state.auth.initialize_admin("admin", "admin-password")
        assert (
            client.post(
                "/api/auth/login", json={"username": "admin", "password": "admin-password"}
            ).status_code
            == 200
        )


def test_oauth_input_and_dependency_failures_are_distinct(github_client):
    client, _ = github_client
    oauth = client.app.state.github_oauth
    with pytest.raises(InvalidInputError):
        oauth.context(None, None)
    with pytest.raises(InvalidInputError):
        oauth.identity("", "verifier")

    def unavailable(request):
        raise httpx.ReadTimeout("private-upstream-secret")

    oauth.transport = httpx.MockTransport(unavailable)
    with pytest.raises(ServiceUnavailableError) as raised:
        oauth.identity("valid-code", "verifier")
    assert raised.value.code == "github_failed"
    assert "private-upstream-secret" not in str(raised.value)


def test_callback_limit_keeps_wait_header_and_cleans_temporary_cookie(github_client, monkeypatch):
    client, upstream = github_client
    client.post("/api/auth/guest", json={})
    original = client.cookies.get("app_session")
    query, _ = start(client)

    def limited(*_):
        raise RateLimitError("rate_limited", "请求过于频繁。", retry_after=9)

    monkeypatch.setattr(client.app.state.rate_limiter, "consume", limited)
    response = complete(client, query)
    assert response.status_code == 303
    assert "auth_error=rate_limited" in response.headers["location"]
    assert response.headers["Retry-After"] == "9"
    assert client.cookies.get(OAUTH_COOKIE) is None
    assert client.cookies.get("app_session") == original
    assert not upstream["requests"]


def test_minimal_scopes_pkce_cookie_and_first_login(github_client):
    client, upstream = github_client
    assert client.get("/api/auth/providers").json() == {"github": {"enabled": True}}
    guest = client.post("/api/auth/guest", json={})
    old_token = client.cookies.get("app_session")
    assert guest.status_code == 200
    query, cookie = start(client)
    assert query["scope"] == [""]
    assert query["code_challenge_method"] == ["S256"]
    context = client.app.state.github_oauth.context(cookie, query["state"][0])
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(context["verifier"].encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert query["code_challenge"] == [challenge]
    assert context["verifier"] not in cookie
    response = complete(client, query)
    assert response.status_code == 303
    assert response.headers["location"] == "/agents?filter=favorites"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "SameSite=lax" in response.headers["set-cookie"]
    )
    assert client.cookies.get(OAUTH_COOKIE) is None
    identity = client.get("/api/auth/me").json()
    assert identity["actor"]["user"]["username"] == "GitHubUser"
    assert set(identity["permissions"]) == ROLE_PERMISSIONS["member"]
    payload = parse_qs(upstream["requests"][0].content.decode())
    assert payload["code_verifier"] == [context["verifier"]]
    assert payload["redirect_uri"] == [GITHUB_CONFIG.callback_url]
    with client.app.state.database.transaction() as db:
        user = db.scalar(select(User))
        assert user.role == "member" and user.password_hash is None
        assert db.scalar(select(ExternalIdentity)).provider_user_id == "123"
        assert count(db, User) == count(db, ExternalIdentity) == 1
        assert (
            db.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_digest(old_token))
            ).revoked_at
            is not None
        )
    assert client.get("/api/public/agents").status_code == 200
    for path in ("/api/agents", "/api/model-connections"):
        assert client.get(path).status_code == 403
    assert (
        client.post("/api/agents", json={"name": "forbidden", "avatar_id": "admin"}).status_code
        == 403
    )
    assert client.post("/api/auth/logout", json={}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_repeated_login_rename_and_admin_name_collision(github_client):
    client, upstream = github_client
    service = client.app.state.auth
    service.initialize_admin("admin", "admin-password")
    upstream["profile"]["login"] = "admin"
    query, _ = start(client)
    assert complete(client, query).status_code == 303
    first = client.get("/api/auth/me").json()
    assert set(first["permissions"]) == ROLE_PERMISSIONS["member"]
    first_token = client.cookies.get("app_session")
    upstream["profile"]["login"] = "RenamedUser"
    query, _ = start(client)
    complete(client, query)
    second = client.get("/api/auth/me").json()
    assert first["actor"]["user"]["id"] == second["actor"]["user"]["id"]
    assert second["actor"]["user"]["username"] == "RenamedUser"
    with service.database.transaction() as db:
        assert count(db, User) == 2 and count(db, ExternalIdentity) == 1
        assert db.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest(first_token))
        ).revoked_at
    assert (
        client.post(
            "/api/auth/login", json={"username": "RenamedUser", "password": "admin-password"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin-password"}
        ).status_code
        == 200
    )
    assert "resources:all" in client.get("/api/auth/me").json()["permissions"]
    # Local maintenance never targets the same-named member.
    service.maintain_user("admin", "disable-user")
    with service.database.transaction() as db:
        assert db.scalar(select(User).where(User.role == "member")).is_active


def test_first_member_does_not_block_local_admin_initialization(github_client):
    client, _ = github_client
    query, _ = start(client)
    complete(client, query)
    client.app.state.auth.initialize_admin("admin", "admin-password")
    with pytest.raises(ValueError, match="已经初始化"):
        client.app.state.auth.initialize_admin("another", "admin-password")


def test_two_github_ids_never_merge_by_username(github_client):
    client, upstream = github_client
    query, _ = start(client)
    complete(client, query)
    first_id = client.get("/api/auth/me").json()["actor"]["user"]["id"]
    upstream["profile"]["id"] = 456
    query, _ = start(client)
    complete(client, query)
    assert client.get("/api/auth/me").json()["actor"]["user"]["id"] != first_id


def test_disabled_member_cannot_login_and_existing_session_is_invalid(github_client):
    client, _ = github_client
    query, _ = start(client)
    complete(client, query)
    with client.app.state.database.transaction() as db:
        db.execute(update(User).where(User.role == "member").values(is_active=False))
    assert client.get("/api/auth/me").status_code == 401
    query, _ = start(client)
    response = complete(client, query)
    assert "github_account_disabled" in response.headers["location"]


@pytest.mark.parametrize(
    "failure",
    ["missing-cookie", "tampered-cookie", "state", "expired", "missing-code", "cancelled"],
)
def test_invalid_callbacks_do_not_create_accounts(github_client, failure):
    client, upstream = github_client
    query, cookie = start(client)
    params = {}
    if failure == "missing-cookie":
        client.cookies.clear()
    elif failure == "tampered-cookie":
        client.cookies.set(
            OAUTH_COOKIE, cookie[:-4] + "xxxx", domain="testserver.local", path=OAUTH_COOKIE_PATH
        )
    elif failure == "state":
        query["state"] = ["wrong"]
    elif failure == "expired":
        now = utc_now()
        client.app.state.github_oauth.clock = lambda: now + timedelta(seconds=OAUTH_TTL + 2)
    elif failure == "missing-code":
        params["code"] = ""
    else:
        params["error"] = "access_denied"
    response = complete(client, query, **params)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/signin?auth_error=github_")
    assert client.cookies.get(OAUTH_COOKIE) is None
    assert not upstream["requests"]
    with client.app.state.database.transaction() as db:
        assert count(db, User) == count(db, ExternalIdentity) == count(db, AuthSession) == 0


def test_successful_callback_cannot_be_replayed(github_client):
    client, upstream = github_client
    query, cookie = start(client)
    response = complete(client, query, code="used-code")
    assert response.status_code == 303
    token = client.cookies.get("app_session")
    client.cookies.set(OAUTH_COOKIE, cookie, domain="testserver.local", path=OAUTH_COOKIE_PATH)
    response = complete(client, query, code="used-code")
    assert "github_failed" in response.headers["location"]
    assert client.cookies.get("app_session") == token
    with client.app.state.database.transaction() as db:
        assert count(db, User) == count(db, AuthSession) == 1


@pytest.mark.parametrize(
    "failure", ["redirect", "timeout", "large", "invalid-json", "invalid-profile", "token-error"]
)
def test_upstream_failure_is_sanitized_and_preserves_old_session(github_client, failure):
    client, _ = github_client
    client.post("/api/auth/guest", json={})
    original = client.cookies.get("app_session")

    def respond(request):
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://evil.test/steal"})
        if failure == "timeout":
            raise httpx.ReadTimeout("private-upstream-secret")
        if failure == "large":
            return httpx.Response(200, content=b"x" * 65537)
        if failure == "invalid-json":
            return httpx.Response(200, content=b"private-upstream-secret")
        if failure == "token-error":
            return httpx.Response(200, json={"error": "private-upstream-secret"})
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "gho_test"})
        return httpx.Response(200, json={"id": True, "login": "admin"})

    client.app.state.github_oauth.transport = httpx.MockTransport(respond)
    query, _ = start(client)
    response = complete(client, query)
    assert "github_failed" in response.headers["location"]
    assert "private-upstream-secret" not in response.text + str(response.headers)
    assert client.cookies.get("app_session") == original
    with client.app.state.database.transaction() as db:
        assert count(db, User) == 0


def test_start_requires_trusted_origin_and_is_rate_limited(github_client):
    client, _ = github_client
    assert (
        client.post(
            "/api/auth/github", json={}, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    for _ in range(20):
        assert client.post("/api/auth/github", json={}).status_code == 200
    assert client.post("/api/auth/github", json={}).status_code == 429


def test_allowed_alias_cannot_lose_oauth_cookie_on_another_host(github_client):
    client, _ = github_client
    response = client.post("/api/auth/github", json={}, headers={"Origin": "http://127.0.0.1:3000"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "github_origin_mismatch"
    assert client.cookies.get(OAUTH_COOKIE) is None


def test_callback_database_failure_clears_only_temporary_cookie(github_client, monkeypatch):
    client, _ = github_client
    client.post("/api/auth/guest", json={})
    original = client.cookies.get("app_session")
    query, _ = start(client)

    def unavailable(*args):
        raise OperationalError("private-sql", {}, RuntimeError("private-database"))

    monkeypatch.setattr(client.app.state.auth, "github_login", unavailable)
    response = complete(client, query)
    assert "github_failed" in response.headers["location"]
    assert client.cookies.get(OAUTH_COOKIE) is None
    assert client.cookies.get("app_session") == original
    assert "private" not in response.text


def test_production_oauth_and_session_cookies_are_secure(migrated_config):
    origin = "https://app.example.test"
    config = replace(
        migrated_config,
        auth=AuthConfig(allowed_origins=(origin,), cookie_secure=True),
        github_oauth=replace(GITHUB_CONFIG, callback_url=origin + "/api/auth/github/callback"),
    )
    with TestClient(create_app(config), base_url=origin, headers={"Origin": origin}) as client:
        response = client.post("/api/auth/github", json={})
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "Domain=" not in response.headers["set-cookie"]
        assert response.headers["cache-control"] == "no-store"
        query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
        response = client.get(
            "/api/auth/github/callback",
            params={"state": query["state"][0], "error": "access_denied"},
            follow_redirects=False,
        )
        assert "Secure" in response.headers["set-cookie"]
        assert "Max-Age=0" in response.headers["set-cookie"]


def test_concurrent_first_logins_create_one_account(github_client):
    client, _ = github_client
    service = client.app.state.auth
    with ThreadPoolExecutor(max_workers=4) as pool:
        actors = list(
            pool.map(lambda _: service.github_login("789", "Concurrent", None)[0], range(4))
        )
    assert len({actor.user_id for actor in actors}) == 1
    with service.database.transaction() as db:
        assert count(db, User) == count(db, ExternalIdentity) == 1


@pytest.mark.parametrize(
    "value",
    [
        "//evil.test",
        "https://evil.test",
        "/\\evil.test",
        "/signin",
        "/api/auth/logout",
        "/%2f%2fevil.test",
        "/agents\r\nLocation: evil",
    ],
)
def test_return_url_is_confined_to_business_routes(github_client, value):
    client, _ = github_client
    assert safe_return_path(value) == "/"
    query, _ = start(client, value)
    assert complete(client, query).headers["location"] == "/"


@pytest.mark.parametrize(
    "values",
    [
        {"GITHUB_OAUTH_CLIENT_ID": "only-id"},
        {
            "GITHUB_OAUTH_CLIENT_ID": "id",
            "GITHUB_OAUTH_CLIENT_SECRET": "secret",
            "GITHUB_OAUTH_CALLBACK_URL": "https://evil.test/api/auth/github/callback",
        },
        {
            "GITHUB_OAUTH_CLIENT_ID": "id",
            "GITHUB_OAUTH_CLIENT_SECRET": "secret",
            "GITHUB_OAUTH_CALLBACK_URL": "http://localhost:3000/api/auth/github/callback?next=evil",
        },
    ],
)
def test_partial_or_untrusted_configuration_fails_closed(values):
    with pytest.raises(ValueError):
        load_github_oauth_config(values, AuthConfig())
    assert "test-client-secret" not in repr(GITHUB_CONFIG)
