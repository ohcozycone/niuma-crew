"""Web authorization sessions and serialized OAuth grants for the existing MCP accounts."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx2
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata, OAuthToken

from app.auth.config import normalize_origin
from app.auth.permissions import require_permission
from app.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ServiceError,
    ServiceUnavailableError,
)
from app.mcp.access import own_connection
from app.mcp.adapters.transport import SDKTransport
from app.mcp.connections import connection_read, require_connection
from app.mcp.models import McpService
from app.mcp.oauth_storage import OAuthStorage

# The SDK's exception/debug logs can include authorization URLs and token bodies.
# Application errors expose only stage codes; no SDK raw diagnostics are logged.
logging.getLogger("mcp.client.auth.oauth2").disabled = True


@dataclass
class AuthorizationSession:
    id: str
    connection_id: str
    actor: object = field(repr=False)
    deadline: float
    config_revision: int
    credential_revision: int
    status: str = "preparing"
    authorization_url: str | None = field(default=None, repr=False)
    state_hash: str | None = field(default=None, repr=False)
    future: object = field(default=None, repr=False)
    task: object = field(default=None, repr=False)
    error_code: str | None = None
    error_message: str | None = None

    @property
    def active(self):
        return (
            self.status in {"preparing", "awaiting_consent", "exchanging"}
            and time.time() < self.deadline
        )

    def read(self):
        return {
            "id": self.id,
            "status": self.status,
            "authorization_url": self.authorization_url
            if self.status == "awaiting_consent"
            else None,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class OAuthService:
    def __init__(self, connections, auth, *, transport_factory=None):
        self.connections, self.auth = connections, auth
        self.config = connections.config
        self.transport_factory = transport_factory
        self.sessions = {}
        self.locks = {}
        self.blocked = set()
        self.start_lock = asyncio.Lock()

    def _owned(self, actor, id, require_enabled=False):
        require_permission(actor, "tools:update")
        with self.connections.database.transaction() as db:
            row = own_connection(db, id, actor.user_id)
            if row.auth_type != "oauth":
                raise InvalidInputError(
                    "oauth_configuration_required", "请先选择并保存 OAuth 认证方式。"
                )
            service = db.get(McpService, row.service_id) if row.service_id else None
            if require_enabled and (not row.enabled or (service and not service.enabled)):
                raise InvalidInputError("tool_connection_disabled", "请先启用 MCP 服务和账号连接。")
            return row

    def _validate_actor(self, db, actor):
        current = self.auth.validate_session(db, actor.session_id)
        if current.user_id != actor.user_id:
            raise InvalidInputError("oauth_session_expired", "发起授权的登录会话已失效。")

    def _prune(self):
        for id, session in list(self.sessions.items()):
            if time.time() > session.deadline:
                if session.active or session.status in {
                    "preparing",
                    "awaiting_consent",
                    "exchanging",
                }:
                    session.status = "expired"
                    session.task.cancel()
                if time.time() > session.deadline + 60:
                    del self.sessions[id]

    async def start(self, actor, id, expected_config, expected_credential, origin):
        async with self.start_lock:
            return await self._start(actor, id, expected_config, expected_credential, origin)

    async def _start(self, actor, id, expected_config, expected_credential, origin):
        row = await asyncio.to_thread(self._owned, actor, id, True)
        callback = urlsplit(self.config.oauth_callback_url)
        if normalize_origin(origin) != normalize_origin(f"{callback.scheme}://{callback.netloc}"):
            raise InvalidInputError(
                "oauth_origin_mismatch",
                f"请从 {callback.scheme}://{callback.netloc} 打开平台后连接账号。",
            )
        self._prune()
        for existing in self.sessions.values():
            if existing.connection_id == id and existing.active:
                if existing.actor.session_id == actor.session_id:
                    if (existing.config_revision, existing.credential_revision) != (
                        row.config_revision,
                        row.credential_revision,
                    ):
                        raise ConflictError(
                            "tool_connection_changed", "连接已改变，请取消原授权后重新连接。"
                        )
                    return existing.read()
                raise ConflictError("oauth_session_conflict", "此连接已有进行中的授权。")
        if (row.config_revision, row.credential_revision) != (expected_config, expected_credential):
            raise ConflictError("tool_connection_changed", "连接已改变，请刷新后重试。")
        if (
            sum(session.active for session in self.sessions.values())
            >= self.config.oauth_max_sessions
        ):
            raise ServiceUnavailableError(
                "oauth_capacity_exhausted", "授权等待名额已满，请稍后重试。"
            )
        # Invalidate the previous grant before a new person/account can authorize.
        await self._disconnect(row, "disconnected")
        row = await asyncio.to_thread(self._owned, actor, id, True)
        session = AuthorizationSession(
            str(uuid4()),
            id,
            actor,
            time.time() + self.config.oauth_session_seconds,
            row.config_revision,
            row.credential_revision,
        )
        session.future = asyncio.get_running_loop().create_future()
        self.sessions[session.id] = session
        session.task = asyncio.create_task(self._authorize(session, row))
        self.blocked.discard(id)
        return session.read()

    async def session(self, actor, id, session_id):
        await asyncio.to_thread(self._owned, actor, id)
        self._prune()
        session = self.sessions.get(session_id)
        if (
            not session
            or session.connection_id != id
            or session.actor.session_id != actor.session_id
            or session.actor.user_id != actor.user_id
        ):
            raise NotFoundError("oauth_session_expired", "授权请求已过期，请重新连接。")
        return session

    async def cancel(self, actor, id, session_id):
        session = await self.session(actor, id, session_id)
        if session.active:
            session.status = "cancelled"
            session.task.cancel()
            await asyncio.gather(session.task, return_exceptions=True)
            row = await asyncio.to_thread(self._owned, actor, id)
            if (
                row.oauth_status == "connected"
                and row.config_revision == session.config_revision
                and row.credential_revision == session.credential_revision + 1
            ):
                await self._disconnect(row, "disconnected")

    async def callback(self, actor, *, state, code=None, issuer=None, error=None):
        digest = hashlib.sha256((state or "").encode()).hexdigest()
        self._prune()
        session = next(
            (value for value in self.sessions.values() if value.state_hash == digest), None
        )
        if (
            not session
            or not session.active
            or session.status != "awaiting_consent"
            or actor.user_id != session.actor.user_id
            or actor.session_id != session.actor.session_id
        ):
            raise InvalidInputError("oauth_session_expired", "授权请求已失效，请重新连接。")
        row = await asyncio.to_thread(self._owned, actor, session.connection_id, True)
        if (row.config_revision, row.credential_revision) != (
            session.config_revision,
            session.credential_revision,
        ):
            session.status = "failed"
            session.task.cancel()
            await asyncio.gather(session.task, return_exceptions=True)
            raise ConflictError("tool_connection_changed", "授权期间连接已改变，请重新连接。")
        if error:
            session.status = "cancelled"
            session.task.cancel()
            await asyncio.gather(session.task, return_exceptions=True)
        else:
            if not code or len(code) > 4096 or not state or len(state) > 512:
                raise InvalidInputError("oauth_session_expired", "授权回调参数无效。")
            session.status = "exchanging"
            session.future.set_result(AuthorizationCodeResult(code=code, state=state, iss=issuer))
        return session, row.service_id

    async def _authorize(self, session, row):
        from app.mcp.adapters.http import MCPClient

        storage = None

        async def redirect(url):
            state = parse_qs(urlsplit(url).query).get("state", [None])[0]
            if not state:
                raise InvalidInputError("oauth_incompatible", "服务没有返回标准 OAuth 授权参数。")
            session.state_hash = hashlib.sha256(state.encode()).hexdigest()
            session.authorization_url = url
            session.status = "awaiting_consent"

        async def callback():
            return await session.future

        try:
            storage = OAuthStorage(
                self.connections,
                row,
                callback_url=self.config.oauth_callback_url,
                interactive=True,
                active=lambda: session.active,
                validate=lambda db: self._validate_actor(db, session.actor),
            )
            async with asyncio.timeout(self.config.oauth_session_seconds):
                async with self.locks.setdefault(row.id, asyncio.Lock()):
                    options = row.public_config.get("oauth", {})
                    provider = OAuthClientProvider(
                        row.public_config["url"],
                        OAuthClientMetadata(
                            client_name="NiumaCrew",
                            redirect_uris=[self.config.oauth_callback_url],
                            grant_types=["authorization_code", "refresh_token"],
                            response_types=["code"],
                            token_endpoint_auth_method="none",
                            scope=" ".join(options.get("scopes", [])) or None,
                        ),
                        storage,
                        redirect,
                        callback,
                    )
                    client = MCPClient(
                        row.public_config["url"],
                        {},
                        self.config,
                        transport_factory=self.transport_factory,
                        auth=provider,
                        observer=storage.observe,
                    )
                    async with client.session():
                        pass
                    if storage.row.oauth_status != "connected":
                        raise InvalidInputError(
                            "oauth_incompatible", "此服务没有完成 OAuth 授权，请检查认证方式。"
                        )
                    session.status = "succeeded"
        except asyncio.CancelledError:
            if session.active:
                session.status = "cancelled"
            raise
        except Exception as error:
            if session.status in {"cancelled", "expired"}:
                pass
            elif storage is not None and storage.row.oauth_status == "connected":
                session.status = "succeeded"
            else:
                session.status = "expired" if isinstance(error, TimeoutError) else "failed"
                session.error_code = (
                    error.code if isinstance(error, ServiceError) else "oauth_failed"
                )
                session.error_message = (
                    error.message
                    if isinstance(error, ServiceError)
                    else "未能完成授权，请检查服务支持和客户端配置后重新连接。"
                )
        finally:
            session.authorization_url = None
            session.state_hash = None
            if not session.future.done():
                session.future.cancel()
            session.future = None

    async def _disconnect(self, row, status):
        storage = OAuthStorage(
            self.connections,
            row,
            callback_url=self.config.oauth_callback_url,
            allow_callback_change=True,
        )
        await storage.invalidate(status=status, clear_catalog=True)
        return connection_read(storage.row)

    async def disconnect(self, actor, id, expected_config, expected_credential):
        row = await asyncio.to_thread(self._owned, actor, id)
        if (row.config_revision, row.credential_revision) != (expected_config, expected_credential):
            raise ConflictError("tool_connection_changed", "连接已改变，请刷新后重试。")
        tasks = []
        for session in self.sessions.values():
            if session.connection_id == id and session.active:
                session.status = "cancelled"
                session.task.cancel()
                tasks.append(session.task)
        await asyncio.gather(*tasks, return_exceptions=True)
        if row.oauth_status == "disconnected" and not row.approved_catalog:
            return connection_read(row)
        return await self._disconnect(row, "disconnected")

    @asynccontextmanager
    async def access(self, row):
        if row.id in self.blocked or any(
            session.connection_id == row.id and session.active for session in self.sessions.values()
        ):
            raise InvalidInputError(
                "tool_auth_required", "此账号需要完成授权，请在访问设置中连接账号。"
            )
        async with self.locks.setdefault(row.id, asyncio.Lock()):

            def current():
                with self.connections.database.transaction() as db:
                    value = require_connection(db, row.id)
                    service = db.get(McpService, value.service_id) if value.service_id else None
                    if (
                        not value.enabled
                        or (service and not service.enabled)
                        or value.oauth_status != "connected"
                        or (row.config_revision, row.credential_revision)
                        != (value.config_revision, value.credential_revision)
                    ):
                        raise InvalidInputError(
                            "tool_auth_required", "OAuth 授权已失效，请重新连接账号。"
                        )
                    return value

            fresh = await asyncio.to_thread(current)
            storage = OAuthStorage(
                self.connections, fresh, callback_url=self.config.oauth_callback_url
            )
            tokens = await storage.get_tokens()
            if not tokens:
                raise InvalidInputError("tool_auth_required", "请先连接 OAuth 账号。")
            if (
                storage.payload.get("expires_at") is not None
                and storage.payload["expires_at"] <= time.time() + 60
            ):
                tokens = await self._refresh(storage, tokens)
            # Discovery/result filtering receives this detached record too. Keep
            # its ciphertext current so rotated credentials cannot be echoed.
            row.encrypted_credentials = storage.row.encrypted_credentials
            try:
                yield {"Authorization": "Bearer " + tokens.access_token}
            except InvalidInputError as error:
                if error.code == "tool_auth_required":
                    try:
                        await storage.invalidate()
                    except ConflictError:
                        # A concurrent account/configuration change wins.
                        pass
                raise

    async def _refresh(self, storage, previous):
        endpoint = storage.payload.get("metadata", {}).get("token_endpoint")
        client = await storage.get_client_info()
        if not endpoint or not client or not previous.refresh_token:
            await storage.invalidate()
            raise InvalidInputError("tool_auth_required", "授权需要重新连接。")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": previous.refresh_token,
            "client_id": client.client_id,
            "resource": storage.row.public_config["url"],
        }
        auth = None
        if client.token_endpoint_auth_method == "client_secret_basic":
            auth = httpx2.BasicAuth(client.client_id, client.client_secret or "")
        elif client.token_endpoint_auth_method == "client_secret_post":
            data["client_secret"] = client.client_secret or ""
        elif client.token_endpoint_auth_method not in {None, "none"}:
            raise InvalidInputError("oauth_incompatible", "暂不支持此客户端认证方式。")
        async with httpx2.AsyncClient(
            transport=SDKTransport(
                storage.row.public_config["url"],
                self.config,
                transport_factory=self.transport_factory,
                oauth=True,
            ),
            headers={"Accept-Encoding": "identity"},
            auth=auth,
            timeout=self.config.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
        ) as client_http:
            response = await client_http.post(endpoint, data=data)
            if response.status_code != 200:
                try:
                    terminal = response.json().get("error") == "invalid_grant"
                except ValueError:
                    terminal = False
                if terminal:
                    await storage.invalidate()
                    raise InvalidInputError("tool_auth_required", "授权已失效，请重新连接账号。")
                raise ServiceUnavailableError(
                    "tool_upstream_failed", "OAuth 续期暂时失败，请稍后重试。"
                )
            try:
                tokens = OAuthToken.model_validate(response.json())
            except ValueError:
                raise ServiceUnavailableError(
                    "tool_upstream_failed", "OAuth 续期响应无效。"
                ) from None
        tokens.refresh_token = tokens.refresh_token or previous.refresh_token
        tokens.scope = tokens.scope if tokens.scope is not None else previous.scope
        try:
            await storage.set_tokens(tokens)
        except Exception:
            self.blocked.add(storage.row.id)
            raise
        return tokens

    async def close(self):
        tasks = [
            session.task
            for session in self.sessions.values()
            if session.task and not session.task.done()
        ]
        for session in self.sessions.values():
            if session.active:
                session.status = "cancelled"
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.sessions.clear()
