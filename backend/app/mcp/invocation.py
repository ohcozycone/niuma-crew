"""Invoke approved tool bindings and own MCP clients for each running Agent."""

from __future__ import annotations

import asyncio
import json

from app.errors import ConflictError, InvalidInputError, ServiceUnavailableError
from app.mcp.adapters.http import MCPClient
from app.mcp.adapters.stdio import StdioMCPClient
from app.mcp.catalogs import save_candidate
from app.mcp.contracts import McpOutcome
from app.mcp.policy import authorize_arguments, effective_arguments
from app.values import digest


class ToolInvocationService:
    def __init__(self, connections, *, client_factory=MCPClient, oauth=None):
        self.connections = connections
        self.oauth = oauth
        self.client_factory = client_factory
        self._stdio_limiter = asyncio.Semaphore(connections.config.max_stdio_processes)
        self._run_callers = set()

    @property
    def config(self):
        return self.connections.config

    def client_for_connection(self, row):
        """Construct a transport from an already authorized connection record."""
        if row.kind == "mcp_stdio":
            if not self.config.stdio_enabled:
                raise InvalidInputError("stdio_disabled", "部署尚未开启可信本机 MCP。")
            environment = (
                self.connections.environment_for_execution(row) if row.encrypted_credentials else {}
            )
            return StdioMCPClient(row.public_config, environment, self.config, self._stdio_limiter)
        if row.auth_type == "oauth":
            if self.oauth is None:
                raise InvalidInputError("tool_auth_required", "OAuth 尚未配置。")
            return self.client_factory(
                row.public_config["url"], {}, self.config, access=lambda: self.oauth.access(row)
            )
        headers = {}
        if row.auth_type != "none":
            if not row.encrypted_credentials:
                raise ServiceUnavailableError("tool_credentials_unavailable", "工具凭证尚未配置。")
            secret = self.connections.credentials_for_execution(row)
            headers[
                "Authorization" if row.auth_type == "bearer" else row.public_config["header_name"]
            ] = "Bearer " + secret if row.auth_type == "bearer" else secret
        return self.client_factory(row.public_config["url"], headers, self.config)

    async def call(self, binding, arguments, guard, *, caller) -> McpOutcome:
        if binding.get("auth_required"):
            return McpOutcome(
                "此操作需要你连接自己的 MCP 账号。请打开员工的「我的连接」连接账号，然后重新发送任务；本次没有访问远端。",
                "failed",
                {
                    "content": "请先在员工的我的工具连接中连接本人账号，然后重新发送任务；没有使用其他人的账号。",
                    "code": "tool_auth_required",
                    "agent_id": binding.get("agent_id"),
                },
            )
        arguments = effective_arguments(binding, arguments)
        authorize_arguments(binding, arguments)
        row = await asyncio.to_thread(self.connections.resolve_for_execution, binding)
        try:
            async with asyncio.timeout(
                min(self.config.timeout_seconds, binding.get("timeout_seconds", 30))
            ):
                client = (
                    await caller.client(row)
                    if row.kind == "mcp_stdio"
                    else await asyncio.to_thread(self.client_for_connection, row)
                )
                client.expected_instructions_hash = binding.get("instructions_hash", digest(""))
                content, artifact, status = await client.invoke(
                    binding["tool_name"], arguments, binding["descriptor_hash"], guard
                )
        except asyncio.CancelledError:
            raise
        except InvalidInputError as error:
            if error.code in {"tool_auth_required", "tool_permission_denied"}:
                return McpOutcome(
                    error.message, "failed", {"code": error.code, "content": error.message}
                )
            if error.code == "tool_catalog_changed" and hasattr(error, "catalog"):
                await asyncio.to_thread(
                    save_candidate,
                    self.connections,
                    row,
                    error.catalog,
                    getattr(error, "instructions", ""),
                )
            raise
        except ConflictError:
            raise
        except ServiceUnavailableError:
            raise
        except Exception:
            raise ServiceUnavailableError(
                "tool_upstream_failed", "工具服务调用失败，未取得可确认结果。"
            ) from None
        data = {"content": content, "structured": artifact}
        serialized = json.dumps(data, ensure_ascii=False, default=str)
        if row.encrypted_credentials:
            for secret in await asyncio.to_thread(self.connections.secrets_for_redaction, row):
                serialized = serialized.replace(secret, "[REDACTED]")
                serialized = serialized.replace(
                    json.dumps(secret, ensure_ascii=False)[1:-1], "[REDACTED]"
                )
            data = json.loads(serialized)
        if len(serialized.encode()) > self.config.max_response_bytes:
            raise InvalidInputError("tool_result_too_large", "工具结果超过保存上限。")
        return McpOutcome(serialized, "succeeded" if status == "success" else "failed", data)

    def for_run(self, run_id):
        """Trusted runtime scope; grants and action permits remain enforced by the host."""
        return RunToolCaller(self, run_id)

    async def close(self):
        outcomes = await asyncio.gather(
            *(caller.aclose() for caller in tuple(self._run_callers)), return_exceptions=True
        )
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome


class RunToolCaller:
    def __init__(self, service, run_id):
        self.service, self.run_id = service, run_id
        self.clients = {}
        self.lock = asyncio.Lock()
        self.closed = False

    async def client(self, row):
        key = (row.id, row.config_revision, row.credential_revision)
        async with self.lock:
            if self.closed:
                raise ServiceUnavailableError("stdio_session_closed", "本轮 MCP 会话已关闭。")
            if key not in self.clients:
                self.service._run_callers.add(self)
                self.clients[key] = await asyncio.to_thread(self.service.client_for_connection, row)
            return self.clients[key]

    async def call(self, binding, arguments, guard):
        return await self.service.call(binding, arguments, guard, caller=self)

    async def aclose(self):
        async with self.lock:
            if self.closed:
                return
            self.closed = True
            clients = tuple(self.clients.values())
            self.clients.clear()
        try:
            outcomes = await asyncio.gather(
                *(client.aclose() for client in clients), return_exceptions=True
            )
        finally:
            self.service._run_callers.discard(self)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.aclose()
