"""后端配置统一入口：合并来源、校验并装配模块配置，不修改进程环境。"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.auth.config import (
    AuthConfig,
    GitHubOAuthConfig,
    load_auth_config,
    load_github_oauth_config,
)
from app.environments.config import SandboxConfig
from app.execution.config import RuntimeConfig, load_runtime_config
from app.files.config import FileConfig
from app.infrastructure.database.session import DatabaseConfig
from app.mcp.config import ToolConfig
from app.skills.config import SkillConfig

BACKEND_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AppConfig:
    """应用级配置聚合；模块内部继续维护各自的类型、默认值和校验。"""

    database: DatabaseConfig
    model_encryption_key_file: Path  # 模型凭证加密主密钥文件，与数据库位置独立。
    runner_lock_file: Path  # 同一数据库的 Runner 必须共用的进程锁文件。
    auth: AuthConfig = AuthConfig()
    # 环境注入的主密钥优先于文件；秘密字段不参与 repr。
    model_encryption_key: str | None = field(default=None, repr=False)
    runtime: RuntimeConfig = RuntimeConfig()
    tools: ToolConfig = ToolConfig()
    files: FileConfig = FileConfig()
    skills: SkillConfig = SkillConfig()
    sandbox: SandboxConfig = SandboxConfig()
    github_oauth: GitHubOAuthConfig = GitHubOAuthConfig()
    frontend_dist: Path = BACKEND_DIR.parent / "frontend/dist"
    knowledge_vector_dir: Path | None = None

    def __post_init__(self) -> None:
        self.github_oauth.validate(self.auth)


def _read_values(backend_dir: Path) -> dict[str, str | None]:
    # 环境优先，包含显式空值；不使用会污染其他配置加载的 load_dotenv。
    return {**dotenv_values(backend_dir / ".env"), **os.environ}


def _value(values: dict[str, str | None], name: str, default: str) -> str:
    value = values.get(name, default)
    if not value or not value.strip():
        raise ValueError(f"{name} 不能为空。")
    return value.strip()


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base_dir / path).resolve()


def _load_database_url(value: str, data_dir: Path) -> URL:
    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError("DATABASE_URL 必须是有效的 SQLAlchemy 连接 URL。") from None
    if url.drivername != "sqlite+pysqlite":
        raise ValueError("DATABASE_URL 当前仅支持 sqlite+pysqlite 文件数据库。")
    if (
        not url.database
        or url.database == ":memory:"
        or url.database.startswith("file:")
        or "\x00" in url.database
        or any(value is not None for value in (url.username, url.password, url.host, url.port))
        or url.query
    ):
        raise ValueError("DATABASE_URL 必须指定 SQLite 文件，不支持内存库、URI 或连接参数。")
    return url.set(database=str(_resolve_path(url.database, data_dir)))


def load_config(backend_dir: Path = BACKEND_DIR) -> AppConfig:
    """统一加载部署配置并解析绝对路径，不创建目录、文件或数据库连接。"""
    values = _read_values(backend_dir)
    data_dir = _resolve_path(_value(values, "APP_DATA_DIR", ".data"), backend_dir)
    url = _load_database_url(_value(values, "DATABASE_URL", "sqlite+pysqlite:///app.db"), data_dir)
    try:
        timeout = int(values.get("SQLITE_BUSY_TIMEOUT_MS", "5000"))
    except (TypeError, ValueError) as error:
        raise ValueError("SQLITE_BUSY_TIMEOUT_MS 必须是整数。") from error
    auth = load_auth_config(values)
    return AppConfig(
        database=DatabaseConfig(url=url, busy_timeout_ms=timeout),
        model_encryption_key_file=_resolve_path(
            _value(values, "MODEL_CONNECTIONS_KEY_FILE", "model-connections.key"), data_dir
        ),
        runner_lock_file=_resolve_path(_value(values, "RUNNER_LOCK_FILE", "runner.lock"), data_dir),
        auth=auth,
        frontend_dist=_resolve_path(
            _value(values, "FRONTEND_DIST", str(backend_dir.parent / "frontend/dist")), backend_dir
        ),
        github_oauth=load_github_oauth_config(values, auth),
        model_encryption_key=values.get("MODEL_CONNECTIONS_ENCRYPTION_KEY"),
        runtime=load_runtime_config(values),
        knowledge_vector_dir=_resolve_path(values["KNOWLEDGE_VECTOR_DIR"], data_dir)
        if values.get("KNOWLEDGE_VECTOR_DIR")
        else None,
        tools=ToolConfig(
            stdio_enabled=values.get("TOOL_MCP_STDIO_ENABLED", "false").lower()
            in {"true", "1", "yes"},
            max_stdio_processes=int(values.get("TOOL_MCP_STDIO_MAX_PROCESSES", "4")),
            stdio_wait_seconds=float(values.get("TOOL_MCP_STDIO_WAIT_SECONDS", "10")),
            oauth_callback_url=values.get(
                "TOOL_OAUTH_CALLBACK_URL",
                "http://localhost:3000/api/tool-connections/oauth/callback",
            ),
        ),
        skills=SkillConfig(
            directory=_resolve_path(values["SKILL_STORAGE_DIR"], data_dir)
            if values.get("SKILL_STORAGE_DIR")
            else None,
            library_directory=_resolve_path(values["SKILL_LIBRARY_DIR"], data_dir)
            if values.get("SKILL_LIBRARY_DIR")
            else None,
        ),
        files=FileConfig(
            directory=_resolve_path(_value(values, "FILES_DIRECTORY", "files"), data_dir),
            max_file_bytes=int(values.get("FILES_MAX_FILE_BYTES", str(10 * 1024 * 1024))),
            max_run_bytes=int(values.get("FILES_MAX_RUN_BYTES", str(40 * 1024 * 1024))),
            max_owner_bytes=int(values.get("FILES_MAX_OWNER_BYTES", str(256 * 1024 * 1024))),
            max_evidence_run_bytes=int(
                values.get("FILES_MAX_EVIDENCE_RUN_BYTES", str(64 * 1024 * 1024))
            ),
            max_evidence_owner_bytes=int(
                values.get("FILES_MAX_EVIDENCE_OWNER_BYTES", str(512 * 1024 * 1024))
            ),
            retention_seconds=int(values.get("FILES_RETENTION_SECONDS", "86400")),
        ),
        sandbox=SandboxConfig(
            endpoint=values.get("OPENSANDBOX_ENDPOINT"),
            api_key=values.get("OPENSANDBOX_API_KEY"),
            image=values.get("OPENSANDBOX_IMAGE"),
            deployment_id=values.get("OPENSANDBOX_DEPLOYMENT_ID", "niuma-crew"),
            verified_profile=values.get("OPENSANDBOX_VERIFIED_PROFILE"),
            cpu=values.get("OPENSANDBOX_CPU", "1"),
            memory=values.get("OPENSANDBOX_MEMORY", "512Mi"),
            max_concurrency=int(values.get("OPENSANDBOX_MAX_CONCURRENCY", "1")),
            command_seconds=int(values.get("OPENSANDBOX_COMMAND_SECONDS", "60")),
            ttl_seconds=int(values.get("OPENSANDBOX_TTL_SECONDS", "240")),
        ),
    )
