"""Own tool accounts, credential revisions and approved connection references."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, InvalidInputError, NotFoundError, ServiceUnavailableError
from app.infrastructure.credentials import CredentialUnavailableError, CredentialVault
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.mcp.access import own_connection
from app.mcp.config import ToolConfig
from app.mcp.models import HttpConnection, McpService, StdioConnection, ToolConnection
from app.mcp.network import validate_endpoint
from app.mcp.schemas import ToolConnectionCreate, ToolConnectionPatch, ToolConnectionRead
from app.values import digest


def valid_header(name):
    return (
        isinstance(name, str)
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,63}", name)
        and name.lower()
        not in {
            "host",
            "cookie",
            "content-length",
            "content-type",
            "proxy-authorization",
            "connection",
            "transfer-encoding",
            "authorization",
            "accept",
            "accept-encoding",
            "origin",
            "referer",
        }
        and not name.lower().startswith(("proxy-", "sec-"))
    )


def connection_read(row) -> ToolConnectionRead:
    return ToolConnectionRead(
        **{
            key: getattr(row, key)
            for key in ToolConnectionRead.model_fields
            if key != "has_credential"
        },
        has_credential=(row.oauth_status == "connected")
        if row.auth_type == "oauth"
        else bool(row.encrypted_credentials),
    )


def require_connection(db, id: str) -> ToolConnection:
    row = db.get(ToolConnection, id)
    if row is None:
        raise NotFoundError("tool_connection_not_found", "工具连接不存在。")
    return row


def compatible_stdio_definition(service, config):
    return (
        config.get("command") == service.command
        and config.get("args") == service.args
        and not (set(config.get("env_keys", [])) - set(service.env_keys))
    )


def assert_connection(db, binding: dict) -> ToolConnection:
    row = require_connection(db, binding["connection_id"])
    descriptor = next(
        (item for item in row.approved_catalog if item["name"] == binding["tool_name"]), None
    )
    if (
        not row.enabled
        or (row.auth_type == "oauth" and row.oauth_status != "connected")
        or row.config_revision != binding["config_revision"]
        or row.credential_revision != binding["credential_revision"]
        or (row.service_id is not None and not db.get(McpService, row.service_id).enabled)
        or descriptor is None
        or descriptor["descriptor_hash"] != binding["descriptor_hash"]
        or digest(row.approved_instructions) != binding.get("instructions_hash", digest(""))
    ):
        raise ConflictError(
            "tool_access_revoked", "工具连接、凭证或目录已改变，本轮停止使用该工具。"
        )
    return row


class ToolConnectionService:
    def __init__(
        self,
        database: Database,
        vault: CredentialVault,
        config: ToolConfig,
        *,
        check_references: Callable[[Session, list[str]], None],
    ):
        self.database, self.vault, self.config = database, vault, config
        self.check_references = check_references

    def _validate_config(self, kind, provider, auth_type, config):
        if kind == "mcp_stdio":
            from app.mcp.definitions import validate_stdio

            if provider is not None or set(config) != {"command", "args", "env_keys"}:
                raise InvalidInputError(
                    "tool_configuration_invalid", "stdio 连接必须引用已登记的完整程序定义。"
                )
            validate_stdio(
                config.get("command"), config.get("args"), config.get("env_keys"), self.config
            )
            if auth_type != ("env" if config["env_keys"] else "none"):
                raise InvalidInputError(
                    "tool_credentials_invalid", "stdio 认证方式须与声明的环境变量一致。"
                )
        else:
            if provider is not None or set(config) - {"url", "header_name", "oauth"}:
                raise InvalidInputError(
                    "tool_configuration_invalid", "MCP 连接仅接受 URL 和认证请求头名称。"
                )
            validate_endpoint(config.get("url", ""))
            if auth_type == "header" and not valid_header(config.get("header_name")):
                raise InvalidInputError("tool_configuration_invalid", "认证请求头名称无效。")
            if auth_type not in {"none", "bearer", "header", "oauth"}:
                raise InvalidInputError("tool_credentials_invalid", "HTTP 不支持环境变量认证。")
            oauth = config.get("oauth", {})
            if (
                not isinstance(oauth, dict)
                or set(oauth) - {"scopes", "client_id"}
                or (oauth and auth_type != "oauth")
            ):
                raise InvalidInputError(
                    "tool_configuration_invalid", "OAuth 配置仅接受 scopes 和 Client ID。"
                )
            if (
                not isinstance(oauth.get("scopes", []), list)
                or any(
                    not isinstance(scope, str)
                    or not scope
                    or len(scope) > 128
                    or any(c.isspace() for c in scope)
                    for scope in oauth.get("scopes", [])
                )
                or len(oauth.get("scopes", [])) > 32
            ):
                raise InvalidInputError(
                    "tool_configuration_invalid", "OAuth scopes 必须为有效权限名称列表。"
                )
            if "client_id" in oauth and (
                not isinstance(oauth["client_id"], str) or not 1 <= len(oauth["client_id"]) <= 1024
            ):
                raise InvalidInputError("tool_configuration_invalid", "OAuth Client ID 无效。")

    def create(self, actor: Actor, data: ToolConnectionCreate) -> ToolConnectionRead:
        require_permission(actor, "tools:update")
        user_id = actor.user_id
        if data.kind == "native":
            raise InvalidInputError("tool_configuration_invalid", "原生工作区由环境配置管理。")
        self._validate_config(data.kind, data.provider_key, data.auth_type, data.public_config)
        if data.kind != "mcp_stdio" and data.environment:
            raise InvalidInputError("tool_credentials_invalid", "只有 stdio 连接使用环境变量凭据。")
        if data.kind == "mcp_stdio" and data.credential:
            raise InvalidInputError("tool_credentials_invalid", "stdio 请使用环境变量凭据。")
        if data.oauth_client_secret and (
            data.auth_type != "oauth" or not data.public_config.get("oauth", {}).get("client_id")
        ):
            raise InvalidInputError(
                "tool_credentials_invalid", "Client Secret 需要 OAuth 和预注册 Client ID。"
            )
        if data.auth_type == "oauth" and data.credential:
            raise InvalidInputError(
                "tool_credentials_invalid", "OAuth 请通过浏览器授权，不填写 Token。"
            )
        if data.auth_type != "oauth" and (data.auth_type != "none") != bool(
            data.credential or data.environment
        ):
            raise InvalidInputError("tool_credentials_invalid", "认证方式与凭证不匹配。")
        encrypted = (
            self.encrypt_oauth(
                {"version": 1, "client_secret": data.oauth_client_secret.get_secret_value()}
            )
            if data.oauth_client_secret
            else self._encrypt_environment(data.environment, data.public_config.get("env_keys", []))
            if data.kind == "mcp_stdio"
            else self._encrypt(data.credential.get_secret_value())
            if data.credential
            else None
        )
        try:
            with self.database.transaction() as db:
                reserve_writer(db, ToolConnection.__table__)
                service_id = data.service_id
                if data.kind in {"mcp_http", "mcp_stdio"}:
                    service = db.get(McpService, service_id) if service_id else None
                    if service_id and (
                        service is None
                        or not service.enabled
                        or service.transport != ("stdio" if data.kind == "mcp_stdio" else "http")
                        or (
                            not compatible_stdio_definition(service, data.public_config)
                            if data.kind == "mcp_stdio"
                            else service.url != data.public_config.get("url")
                        )
                    ):
                        raise InvalidInputError(
                            "mcp_service_invalid", "连接必须引用已启用且地址一致的 MCP 服务。"
                        )
                    if service is None:
                        if data.kind == "mcp_stdio":
                            raise InvalidInputError(
                                "mcp_service_invalid", "stdio 连接必须引用管理员登记的程序。"
                            )
                        from app.mcp.definitions import check_unique_service, matching_service

                        service = matching_service(db, "http", data.public_config["url"])
                        if service is None:
                            check_unique_service(db, data.name, "http", data.public_config["url"])
                            service = McpService(
                                name=data.name,
                                description="",
                                url=data.public_config["url"],
                                owner_user_id=user_id,
                            )
                            db.add(service)
                            db.flush()
                    service_id = service.id
                    if data.account_scope == "shared" and service.owner_user_id != user_id:
                        raise InvalidInputError(
                            "shared_connection_denied", "只有服务创建者可以配置共用账号。"
                        )
                row = (StdioConnection if data.kind == "mcp_stdio" else HttpConnection)(
                    **data.model_dump(
                        exclude={
                            "credential",
                            "environment",
                            "service_id",
                            "account_scope",
                            "oauth_client_secret",
                        }
                    ),
                    service_id=service_id,
                    account_scope=data.account_scope,
                    encrypted_credentials=encrypted,
                    oauth_status="disconnected" if data.auth_type == "oauth" else None,
                    created_by_user_id=user_id,
                    approved_catalog=[],
                )
                db.add(row)
                db.flush()
                return connection_read(row)
        except IntegrityError as error:
            from app.infrastructure.database.errors import is_unique_violation

            if is_unique_violation(error, table="tool_connections", columns=("name",)):
                raise ConflictError(
                    "tool_connection_name_conflict", "工具连接名称已存在。"
                ) from None
            raise

    def _encrypt(self, value: str):
        if not value or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise InvalidInputError(
                "tool_credentials_invalid", "凭证必须为无空白的可打印 ASCII 字符。"
            )
        with self.database.transaction() as db:
            existing = db.scalar(
                select(ToolConnection.id)
                .where(ToolConnection.encrypted_credentials.is_not(None))
                .limit(1)
            )
        try:
            return self.vault.encrypt(value, allow_create=existing is None)
        except CredentialUnavailableError:
            raise ServiceUnavailableError(
                "tool_credentials_unavailable", "工具加密主密钥不可用，请恢复密钥备份。"
            ) from None

    def encrypt_oauth(self, value: dict) -> str:
        """Encrypt structured OAuth material without using the static-token validator."""
        with self.database.transaction() as db:
            existing = db.scalar(
                select(ToolConnection.id)
                .where(ToolConnection.encrypted_credentials.is_not(None))
                .limit(1)
            )
        try:
            return self.vault.encrypt(json.dumps(value), allow_create=existing is None)
        except CredentialUnavailableError:
            raise ServiceUnavailableError(
                "tool_credentials_unavailable", "工具加密主密钥不可用，请恢复密钥备份。"
            ) from None

    def _encrypt_environment(self, environment, keys):
        values = {key: value.get_secret_value() for key, value in environment.items()}
        if set(values) != set(keys) or any(
            not value
            or len(value) > 4096
            or "\x00" in value
            or any(token in value for token in ("${", "{{"))
            for value in values.values()
        ):
            raise InvalidInputError(
                "tool_credentials_invalid",
                "请填写全部声明的环境变量，替换空值和模板占位，不能增加其他变量。",
            )
        encoded = json.dumps(values, ensure_ascii=True, separators=(",", ":")).replace(
            " ", "\\u0020"
        )
        if len(encoded.encode()) > 32768:
            raise InvalidInputError("tool_credentials_invalid", "环境变量凭据总量不能超过 32 KiB。")
        return self._encrypt(encoded) if values else None

    def list(self, actor: Actor) -> list[ToolConnectionRead]:
        require_permission(actor, "tools:read")
        user_id = actor.user_id
        with self.database.transaction() as db:
            return [
                connection_read(row)
                for row in db.scalars(
                    select(ToolConnection)
                    .where(ToolConnection.kind != "native")
                    .where(
                        (ToolConnection.created_by_user_id == user_id)
                        | (ToolConnection.account_scope == "shared")
                    )
                    .order_by(ToolConnection.created_at, ToolConnection.id)
                )
            ]

    def update(self, actor: Actor, id: str, data: ToolConnectionPatch) -> ToolConnectionRead:
        require_permission(actor, "tools:update")
        user_id = actor.user_id
        fields = data.model_fields_set
        with self.database.transaction() as db:
            reserve_writer(db, ToolConnection.__table__)
            row = own_connection(db, id, user_id)
            if (row.config_revision, row.credential_revision) != (
                data.expected_config_revision,
                data.expected_credential_revision,
            ):
                raise ConflictError("tool_connection_changed", "连接已被修改，请刷新后重试。")
            config = dict(data.public_config if "public_config" in fields else row.public_config)
            auth = data.auth_type if "auth_type" in fields else row.auth_type
            if row.kind == "mcp_stdio":
                if "credential" in fields:
                    raise InvalidInputError(
                        "tool_credentials_invalid", "stdio 请填写环境变量凭据。"
                    )
                if auth == "none":
                    config["env_keys"] = []
                elif "environment" in fields:
                    config["env_keys"] = list(data.environment)
                service = db.get(McpService, row.service_id)
                if service is None or not compatible_stdio_definition(service, config):
                    raise InvalidInputError(
                        "mcp_service_invalid", "只能使用已登记的程序和允许的环境变量字段。"
                    )
            elif row.service_id and config.get("url") != row.public_config.get("url"):
                raise InvalidInputError(
                    "mcp_service_invalid", "更换地址请建立新的服务与连接，避免复用旧账号许可。"
                )
            self._validate_config(row.kind, row.provider_key, auth, config)
            if "oauth_client_secret" in fields and (
                auth != "oauth" or not config.get("oauth", {}).get("client_id")
            ):
                raise InvalidInputError(
                    "tool_credentials_invalid", "Client Secret 需要 OAuth 和预注册 Client ID。"
                )
            if auth == "oauth" and "credential" in fields:
                raise InvalidInputError(
                    "tool_credentials_invalid", "OAuth 请通过浏览器授权，不填写 Token。"
                )
            if "environment" in fields and row.kind != "mcp_stdio":
                raise InvalidInputError("tool_credentials_invalid", "此连接不支持环境变量凭据。")
            if data.clear_credential and ("credential" in fields or "environment" in fields):
                raise InvalidInputError("tool_credentials_invalid", "不能同时更新和清除凭证。")
            if auth == "none" and (
                "credential" in fields or ("environment" in fields and data.environment)
            ):
                raise InvalidInputError("tool_credentials_invalid", "无需认证时不能提交密钥。")
            encrypted = row.encrypted_credentials
            if auth != row.auth_type:
                encrypted = None
            if "oauth_client_secret" in fields:
                encrypted = self.encrypt_oauth(
                    {"version": 1, "client_secret": data.oauth_client_secret.get_secret_value()}
                )
            if "credential" in fields:
                encrypted = self._encrypt(data.credential.get_secret_value())
            if "environment" in fields:
                encrypted = self._encrypt_environment(data.environment, config["env_keys"])
            if data.clear_credential or auth == "none":
                encrypted = None
            enabled = data.enabled if "enabled" in fields else row.enabled
            if enabled and auth not in {"none", "oauth"} and not encrypted:
                raise InvalidInputError("tool_credentials_invalid", "请填写此访问方式需要的凭据。")
            credential_changed = (
                bool(fields & {"credential", "environment", "oauth_client_secret"})
                or data.clear_credential
                or auth != row.auth_type
            )
            config_changed = config != row.public_config or any(
                key in fields for key in ("name", "enabled", "auth_type")
            )
            if credential_changed:
                row.credential_revision += 1
            if config_changed:
                row.config_revision += 1
            if credential_changed or config != row.public_config:
                row.approved_catalog = []
                row.approved_instructions = ""
                row.catalog_revision += 1
            if credential_changed or config_changed:
                row.discovery_candidate = None
            if credential_changed or config != row.public_config:
                row.oauth_storage_revision += 1
                if auth == "oauth":
                    if (
                        row.auth_type == "oauth"
                        and encrypted
                        and "oauth_client_secret" not in fields
                    ):
                        payload = json.loads(self._decrypt(row))
                        payload.pop("tokens", None)
                        payload.pop("expires_at", None)
                        if config.get("oauth", {}).get("client_id") != row.public_config.get(
                            "oauth", {}
                        ).get("client_id"):
                            payload.pop("client_info", None)
                            payload.pop("client_secret", None)
                        encrypted = self.encrypt_oauth(payload)
                    row.oauth_status = "disconnected"
                else:
                    row.oauth_status = None
            row.encrypted_credentials, row.auth_type, row.public_config = encrypted, auth, config
            if "name" in fields:
                row.name = data.name
            row.enabled = enabled
            db.flush()
            return connection_read(row)

    def delete(
        self,
        actor: Actor,
        id: str,
        expected_config_revision,
        expected_credential_revision,
    ) -> None:
        require_permission(actor, "tools:update")
        user_id = actor.user_id
        with self.database.transaction() as db:
            reserve_writer(db, ToolConnection.__table__)
            row = own_connection(db, id, user_id)
            if (row.config_revision, row.credential_revision) != (
                expected_config_revision,
                expected_credential_revision,
            ):
                raise ConflictError("tool_connection_changed", "连接已被修改，请刷新后重试。")
            self.check_references(db, [id])
            db.delete(row)

    def resolve_for_execution(self, binding: dict) -> ToolConnection:
        """Trusted runtime lookup after the employee grant authorized this binding."""
        with self.database.transaction() as db:
            return assert_connection(db, binding)

    def _decrypt(self, row: ToolConnection) -> str:
        if not row.encrypted_credentials:
            raise ServiceUnavailableError("tool_credentials_unavailable", "工具凭证尚未配置。")
        try:
            return self.vault.decrypt(row.encrypted_credentials)
        except CredentialUnavailableError:
            raise ServiceUnavailableError(
                "tool_credentials_unavailable", "工具主密钥无法读取，请恢复对应密钥。"
            ) from None

    def credentials_for_execution(self, row: ToolConnection) -> str:
        """Return a secret only to the trusted transport, never a management response."""
        return self._decrypt(row)

    def environment_for_execution(self, row: ToolConnection) -> dict[str, str]:
        if not row.encrypted_credentials:
            return {}
        try:
            values = json.loads(self._decrypt(row))
            if not isinstance(values, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in values.items()
            ):
                raise ValueError()
            return values
        except (ValueError, TypeError):
            raise ServiceUnavailableError(
                "tool_credentials_unavailable", "工具环境凭据无法读取，请重新保存凭据。"
            ) from None

    def secrets_for_redaction(self, row: ToolConnection) -> list[str]:
        """Trusted result filtering uses the same credential failure mapping as transports."""
        if row.auth_type == "oauth":
            payload = json.loads(self._decrypt(row))
            values = [
                payload.get("client_secret"),
                payload.get("client_info", {}).get("client_secret"),
                payload.get("client_info", {}).get("registration_access_token"),
            ]
            values.extend(
                payload.get("tokens", {}).get(key)
                for key in ("access_token", "refresh_token", "id_token")
            )
            return [value for value in values if isinstance(value, str) and value]
        return (
            list(self.environment_for_execution(row).values())
            if row.auth_type == "env"
            else [self._decrypt(row)]
        )
