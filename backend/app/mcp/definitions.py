"""Shared MCP endpoint definitions and inert official-config import."""

import json
import os
import re
from urllib.parse import urlsplit

from sqlalchemy import select

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.errors import ConflictError, InvalidInputError, PermissionDeniedError
from app.infrastructure.database.transactions import reserve_writer
from app.mcp.access import service_manager
from app.mcp.models import McpService
from app.mcp.network import validate_endpoint


def service_identity(transport, url=None, command=None, args=None):
    if transport == "http":
        parsed = urlsplit(url)
        port = parsed.port
        authority = (parsed.hostname or "").lower()
        if port and port != (443 if parsed.scheme == "https" else 80):
            authority += f":{port}"
        return (transport, parsed.scheme.lower(), authority, parsed.path or "/", parsed.query)
    argv = list(args or [])
    # npm's consent flags do not identify a different service. Keep package versions
    # and all business arguments: different versions/targets may expose different tools.
    if command in {"npx", "bunx"}:
        while argv and argv[0] in {"-y", "--yes"}:
            argv.pop(0)
        command = "npm-package"
    return (transport, command, tuple(argv))


def matching_service(db, transport, url=None, command=None, args=None):
    identity = service_identity(transport, url, command, args)
    return next(
        (
            row
            for row in db.scalars(select(McpService))
            if service_identity(row.transport, row.url, row.command, row.args) == identity
        ),
        None,
    )


def check_unique_service(db, name, transport, url=None, command=None, args=None, exclude=None):
    normalized = " ".join(name.split()).casefold()
    identity = service_identity(transport, url, command, args)
    for row in db.scalars(select(McpService)):
        if row.id == exclude:
            continue
        if service_identity(row.transport, row.url, row.command, row.args) == identity:
            raise ConflictError(
                "mcp_service_exists", f"此 MCP 已接入为“{row.name}”，请使用已有服务。"
            )
        if " ".join(row.name.split()).casefold() == normalized:
            raise ConflictError("mcp_service_name_conflict", "MCP 服务名称已存在，请使用其他名称。")


def runtime_environment_key(key):
    upper = key.upper()
    return (
        upper
        in {
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "SHELL",
            "ENV",
            "BASH_ENV",
            "ZDOTDIR",
            "IFS",
            "CDPATH",
            "TMP",
            "TEMP",
            "TMPDIR",
            "BROWSER",
            "RUBYOPT",
            "RUBYLIB",
            "PERL5OPT",
            "PERL5LIB",
            "JAVA_TOOL_OPTIONS",
            "JDK_JAVA_OPTIONS",
            "CLASSPATH",
            "DOTNET_STARTUP_HOOKS",
            "REQUESTS_CA_BUNDLE",
            "CURL_CA_BUNDLE",
        }
        or upper.startswith(
            ("PYTHON", "NODE_", "BUN_", "LD_", "DYLD_", "NPM_", "PIP_", "GIT_", "SSL_")
        )
        or upper.endswith("_PROXY")
    )


def service_read(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "name",
            "description",
            "transport",
            "url",
            "command",
            "args",
            "env_keys",
            "input_fields",
            "owner_user_id",
            "revision",
            "enabled",
        )
    }


class McpDefinitionService:
    def __init__(self, database, config, *, check_references):
        self.database, self.config = database, config
        self.check_references = check_references

    def list(self, actor: Actor):
        require_permission(actor, "tools:read")
        with self.database.transaction() as db:
            return [
                service_read(row)
                for row in db.scalars(
                    select(McpService).order_by(McpService.created_at.desc(), McpService.id)
                )
            ]

    def create(self, actor: Actor, data):
        require_permission(actor, "tools:update")
        user_id = actor.user_id
        names = [field.name for field in data.input_fields]
        if len(names) != len(set(names)) or (
            data.transport == "stdio" and set(names) - set(data.env_keys)
        ):
            raise InvalidInputError("mcp_input_invalid", "输入字段必须唯一且与接入配置一致。")
        if data.transport == "http" and names:
            from app.mcp.connections import valid_header

            if len(names) > 1 or (
                names[0].lower() != "authorization" and not valid_header(names[0])
            ):
                raise InvalidInputError("mcp_input_invalid", "当前 HTTP 仅支持一个认证头字段。")
        if data.transport == "stdio":
            if actor.role != "admin":
                raise PermissionDeniedError(
                    "stdio_registration_denied", "仅管理员可以登记本机 MCP 程序。"
                )
            validate_stdio(data.command, data.args, data.env_keys, self.config)
            if data.url is not None:
                raise InvalidInputError("tool_configuration_invalid", "stdio 不使用服务 URL。")
        else:
            validate_endpoint(data.url or "")
            if data.command is not None or data.args or data.env_keys:
                raise InvalidInputError("tool_configuration_invalid", "HTTP 服务不能包含程序配置。")
        with self.database.transaction() as db:
            reserve_writer(db, McpService.__table__)
            check_unique_service(db, data.name, data.transport, data.url, data.command, data.args)
            row = McpService(**data.model_dump(), owner_user_id=user_id)
            db.add(row)
            db.flush()
            return service_read(row)

    def update(self, actor: Actor, id, data):
        require_permission(actor, "tools:update")
        user_id = actor.user_id
        with self.database.transaction() as db:
            reserve_writer(db, McpService.__table__)
            row = service_manager(db, id, user_id)
            if row.transport == "stdio" and actor.role != "admin":
                raise PermissionDeniedError(
                    "stdio_registration_denied", "仅管理员可以修改本机 MCP 程序。"
                )
            if row.revision != data.expected_revision:
                raise ConflictError("mcp_service_changed", "服务定义已修改，请刷新。")
            if "name" in data.model_fields_set and data.name != row.name:
                check_unique_service(
                    db, data.name, row.transport, row.url, row.command, row.args, row.id
                )
            if "env_keys" in data.model_fields_set:
                from app.mcp.models import ToolConnection

                if row.transport != "stdio":
                    raise InvalidInputError(
                        "tool_configuration_invalid", "只有 stdio 服务使用环境变量字段。"
                    )
                validate_stdio(row.command, row.args, data.env_keys, self.config)
                row.input_fields = [
                    field for field in row.input_fields if field["name"] in data.env_keys
                ]
                if any(
                    set(account.public_config["env_keys"]) - set(data.env_keys)
                    for account in db.scalars(
                        select(ToolConnection).where(ToolConnection.service_id == row.id)
                    )
                ):
                    raise ConflictError(
                        "mcp_environment_in_use",
                        "有连接正在使用这些凭据字段，请先修改相应访问设置。",
                    )
            for key, value in data.model_dump(
                exclude_unset=True, exclude={"expected_revision"}
            ).items():
                setattr(row, key, value)
            row.revision += 1
            db.flush()
            return service_read(row)

    def delete(self, actor: Actor, id, expected_revision):
        require_permission(actor, "tools:update")
        user_id = actor.user_id
        from app.mcp.models import ToolConnection

        with self.database.transaction() as db:
            reserve_writer(db, McpService.__table__)
            row = service_manager(db, id, user_id)
            if row.revision != expected_revision:
                raise ConflictError("mcp_service_changed", "服务定义已修改，请刷新。")
            accounts = list(
                db.scalars(select(ToolConnection).where(ToolConnection.service_id == id))
            )
            if any(account.created_by_user_id != user_id for account in accounts):
                raise ConflictError(
                    "mcp_service_in_use", "其他用户已配置此服务，请先停用；不能删除他人的连接。"
                )
            self.check_references(db, [account.id for account in accounts])
            for account in accounts:
                db.delete(account)
            db.flush()
            db.delete(row)

    def import_config(self, actor: Actor, data):
        require_permission(actor, "tools:update")
        # Validate the supported subset before constructing any SDK transport.
        try:
            raw = json.loads(data.configuration)
            if (
                isinstance(raw, dict)
                and isinstance(raw.get("name"), str)
                and ("packages" in raw or "remotes" in raw)
            ):
                return self._registry_preview(raw)
            if (
                not isinstance(raw, dict)
                or set(raw) != {"mcpServers"}
                or not isinstance(raw["mcpServers"], dict)
                or not 1 <= len(raw["mcpServers"]) <= 16
            ):
                raise ValueError()
            for value in raw["mcpServers"].values():
                if isinstance(value, dict) and "command" in value:
                    if (
                        set(value) - {"command", "args", "env", "transport", "type"}
                        or value.get("transport", value.get("type", "stdio")) != "stdio"
                    ):
                        raise ValueError()
                    env = value.get("env", {})
                    if not isinstance(env, dict) or any(
                        not isinstance(v, str) or len(v) > 4096 or "\x00" in v for v in env.values()
                    ):
                        raise ValueError()
                    validate_stdio(value["command"], value.get("args", []), list(env), self.config)
                    continue
                if (
                    not isinstance(value, dict)
                    or set(value) - {"url", "transport", "headers", "type"}
                    or value.get("transport", value.get("type", "http"))
                    not in {"http", "streamable-http"}
                ):
                    raise ValueError()
                if (
                    not isinstance(value.get("url"), str)
                    or not isinstance(value.get("headers", {}), dict)
                    or len(value.get("headers", {})) > 1
                ):
                    raise ValueError()
                validate_endpoint(value["url"])
                if any(token in value["url"] for token in ("${", "{{")):
                    raise ValueError()
        except InvalidInputError:
            raise
        except Exception:
            raise InvalidInputError(
                "mcp_config_unsupported",
                "支持远程 HTTP 或已开启的可信 stdio 配置；不支持 SSE、OAuth、变量引用或 shell 命令。",
            ) from None
        entries = []
        for name, value in raw["mcpServers"].items():
            if "command" in value:
                keys = list(value.get("env", {}))
                entries.append(
                    dict(
                        name=name,
                        transport="stdio",
                        url=None,
                        command=value["command"],
                        args=value.get("args", []),
                        env_keys=keys,
                        auth_type="env" if keys else "none",
                        header_name=None,
                        has_credential=any(
                            secret and not any(token in secret for token in ("${", "{{"))
                            for secret in value.get("env", {}).values()
                        ),
                        host=None,
                    )
                )
                continue
            headers = value.get("headers", {})
            auth_type, header_name = "none", None
            if headers:
                key, secret = next(iter(headers.items()))
                if not isinstance(secret, str):
                    raise InvalidInputError(
                        "mcp_config_unsupported", "认证头必须提供字符串或待填写占位符。"
                    )
                if key.lower() == "authorization":
                    if secret and not secret.startswith("Bearer "):
                        raise InvalidInputError(
                            "mcp_config_unsupported", "Authorization 仅支持 Bearer Token。"
                        )
                    auth_type = "bearer"
                else:
                    from app.mcp.connections import valid_header

                    if not valid_header(key):
                        raise InvalidInputError("mcp_config_unsupported", "不支持此认证头名称。")
                    auth_type, header_name = "header", key
            # Secrets are intentionally never returned by this preview endpoint.
            entries.append(
                dict(
                    name=name,
                    transport="http",
                    command=None,
                    args=[],
                    env_keys=[],
                    url=value["url"],
                    auth_type=auth_type,
                    header_name=header_name,
                    has_credential=bool(headers),
                    host=urlsplit(value["url"]).hostname,
                )
            )
        return {"entries": entries}

    def _registry_preview(self, raw):
        """Normalize supported Registry installations without downloading or executing."""
        entries, warnings = [], []
        title = raw.get("title") or raw["name"]
        description = raw.get("description", "")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title) > 200
            or not isinstance(description, str)
            or len(description) > 4000
        ):
            raise ValueError()
        if any(
            not isinstance(raw.get(key, []), list) or len(raw.get(key, [])) > 16
            for key in ("remotes", "packages")
        ):
            raise ValueError()

        def fields(values):
            if not isinstance(values, list) or len(values) > 32:
                raise ValueError()
            result = []
            for item in values:
                if (
                    not isinstance(item, dict)
                    or item.get("variables")
                    or item.get("value") is not None
                    or item.get("default") is not None
                ):
                    raise InvalidInputError(
                        "mcp_config_unsupported",
                        "此描述包含固定值、默认值或参数模板，请使用服务方的客户端配置。",
                    )
                from app.mcp.schemas import McpInputField

                result.append(
                    McpInputField(
                        name=item.get("name", ""),
                        description=item.get("description", ""),
                        is_required=item.get("isRequired", False),
                        is_secret=item.get("isSecret", False),
                    ).model_dump()
                )
            return result

        for remote in raw.get("remotes", []):
            if remote.get("type") != "streamable-http":
                warnings.append("已跳过当前不支持的远程传输。")
                continue
            inputs = fields(remote.get("headers", []))
            if len(inputs) > 1:
                raise InvalidInputError(
                    "mcp_config_unsupported", "当前不支持多个远程请求头，请使用受支持的认证方式。"
                )
            url = remote.get("url", "")
            validate_endpoint(url)
            from app.mcp.connections import valid_header

            if (
                inputs
                and inputs[0]["name"].lower() != "authorization"
                and not valid_header(inputs[0]["name"])
            ):
                raise ValueError()
            key = inputs[0]["name"] if inputs else None
            entries.append(
                dict(
                    name=title,
                    description=description,
                    transport="http",
                    url=url,
                    command=None,
                    args=[],
                    env_keys=[],
                    auth_type="bearer"
                    if key and key.lower() == "authorization"
                    else "header"
                    if key
                    else "none",
                    header_name=key,
                    has_credential=False,
                    input_fields=inputs,
                )
            )
        for package in raw.get("packages", []):
            if (
                package.get("registryType") != "npm"
                or package.get("transport", {}).get("type") != "stdio"
            ):
                warnings.append("已跳过当前不支持的本地程序包格式。")
                continue
            if not self.config.stdio_enabled:
                warnings.append("当前部署未开启 stdio，已跳过本地安装方式。")
                continue
            identifier, version = package.get("identifier", ""), package.get("version", "")
            if (
                not isinstance(identifier, str)
                or not re.fullmatch(r"(?:@[a-z0-9._-]+/)?[a-z0-9._-]+", identifier)
                or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version)
            ):
                raise InvalidInputError(
                    "mcp_config_unsupported", "npm 服务描述需要明确的包名与固定版本。"
                )
            if (
                package.get("runtimeArguments")
                or package.get("packageArguments")
                or package.get("runtimeHint", "npx") not in {"npx", "bunx"}
            ):
                raise InvalidInputError(
                    "mcp_config_unsupported", "此描述含额外启动参数，请导入服务方的客户端配置。"
                )
            inputs = fields(package.get("environmentVariables", []))
            command, args = package.get("runtimeHint", "npx"), ["-y", f"{identifier}@{version}"]
            keys = [item["name"] for item in inputs]
            validate_stdio(command, args, keys, self.config)
            entries.append(
                dict(
                    name=title,
                    description=description,
                    transport="stdio",
                    url=None,
                    command=command,
                    args=args,
                    env_keys=keys,
                    auth_type="env" if keys else "none",
                    header_name=None,
                    has_credential=False,
                    input_fields=inputs,
                )
            )
        if not entries:
            raise InvalidInputError("mcp_config_unsupported", "描述没有当前部署支持的接入方式。")
        return {"entries": entries, "warnings": warnings}


def validate_stdio(command, args, env_keys, config):
    if not config.stdio_enabled:
        raise InvalidInputError(
            "stdio_disabled", "部署尚未开启可信本机 MCP；请由部署者开启后使用。"
        )
    if os.name != "posix":
        raise InvalidInputError(
            "stdio_platform_unsupported", "当前可信进程接入仅支持 macOS 和 Linux。"
        )
    if (
        not isinstance(command, str)
        or not command
        or len(command) > 2048
        or any(character in command for character in ("\x00", "\n", "\r"))
        or not isinstance(args, list)
        or len(args) > 64
        or any(not isinstance(arg, str) or len(arg) > 4096 or "\x00" in arg for arg in args)
        or not isinstance(env_keys, list)
        or len(env_keys) > 32
        or len(set(env_keys)) != len(env_keys)
        or any(
            not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key)
            for key in env_keys
        )
        or any(token in json.dumps([command, args]) for token in ("${", "{{"))
    ):
        raise InvalidInputError(
            "stdio_configuration_invalid", "程序、结构化参数或环境变量名称无效。"
        )
    if any(runtime_environment_key(key) for key in env_keys):
        raise InvalidInputError(
            "stdio_environment_denied",
            "环境变量只允许业务凭据或参数，不能改变程序搜索、加载、代理或宿主目录。",
        )
