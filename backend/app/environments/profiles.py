"""Native workspace profiles and their operation catalogs."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.permissions import require_permission
from app.environments.models import WorkspaceProfile
from app.errors import ConflictError, InvalidInputError, NotFoundError
from app.infrastructure.database.transactions import reserve_writer
from app.values import digest

FILE_TOOLS = ("ls", "read_file", "glob", "grep", "write_file", "edit_file", "delete")
WRITE_TOOLS = frozenset({"write_file", "edit_file", "delete", "execute"})
RESERVED_NAMES = frozenset((*FILE_TOOLS, "execute", "read_tool_result"))


def native_catalog(mode: str) -> list[dict]:
    names = [*FILE_TOOLS, *(["execute"] if mode == "sandbox" else [])]
    return [
        {
            "name": name,
            "description": f"平台受控工作区：{name}",
            "input_schema": {"type": "object"},
            "recovery": "never" if name in WRITE_TOOLS else "readonly",
            "descriptor_hash": digest(["workspace-v1", mode, name]),
        }
        for name in names
    ]


class WorkspaceProfileService:
    def __init__(self, database, check_references):
        self.database, self.check_references = (database, check_references)

    @staticmethod
    def validate(provider, auth, config):
        if (
            provider != "workspace"
            or auth != "none"
            or set(config) - {"workspace_mode"}
            or (config.get("workspace_mode", "virtual") not in ("virtual", "sandbox"))
        ):
            raise InvalidInputError(
                "tool_configuration_invalid", "原生连接只支持受控工作区的虚拟或沙箱模式。"
            )

    @staticmethod
    def read(row):
        return {
            key: getattr(row, key)
            for key in (
                "id",
                "name",
                "kind",
                "provider_key",
                "auth_type",
                "public_config",
                "enabled",
                "config_revision",
                "credential_revision",
                "catalog_revision",
                "service_id",
                "account_scope",
                "created_by_user_id",
                "tool_annotations",
                "annotations_revision",
                "approved_catalog",
                "approved_instructions",
                "discovery_candidate",
                "oauth_status",
            )
        } | {"has_credential": False}

    @staticmethod
    def require(db, id, user_id):
        row = db.get(WorkspaceProfile, id)
        if row is None or row.created_by_user_id != user_id:
            raise NotFoundError("tool_connection_not_found", "工具连接不存在。")
        return row

    def contains(self, id):
        with self.database.transaction() as db:
            return db.get(WorkspaceProfile, id) is not None

    def list(self, actor):
        require_permission(actor, "tools:read")
        with self.database.transaction() as db:
            return [
                self.read(row)
                for row in db.scalars(
                    select(WorkspaceProfile)
                    .where(WorkspaceProfile.created_by_user_id == actor.user_id)
                    .order_by(WorkspaceProfile.name)
                )
            ]

    def create(self, actor, data):
        require_permission(actor, "tools:update")
        self.validate(data.provider_key, data.auth_type, data.public_config)
        if (
            data.service_id is not None
            or data.credential
            or data.environment
            or data.oauth_client_secret
        ):
            raise InvalidInputError("tool_credentials_invalid", "平台工作区不使用 MCP 服务或凭据。")
        try:
            with self.database.transaction() as db:
                reserve_writer(db, WorkspaceProfile.__table__)
                row = WorkspaceProfile(
                    name=data.name,
                    provider_key="workspace",
                    auth_type="none",
                    public_config=data.public_config,
                    enabled=data.enabled,
                    account_scope="shared",
                    created_by_user_id=actor.user_id,
                    approved_catalog=native_catalog(
                        data.public_config.get("workspace_mode", "virtual")
                    ),
                )
                db.add(row)
                db.flush()
                return self.read(row)
        except IntegrityError as error:
            from app.infrastructure.database.errors import is_unique_violation

            if is_unique_violation(error, table="tool_connections", columns=("name",)):
                raise ConflictError(
                    "tool_connection_name_conflict", "工具连接名称已存在。"
                ) from None
            raise

    def update(self, actor, id, data):
        require_permission(actor, "tools:update")
        with self.database.transaction() as db:
            reserve_writer(db, WorkspaceProfile.__table__)
            row = self.require(db, id, actor.user_id)
            if (row.config_revision, row.credential_revision) != (
                data.expected_config_revision,
                data.expected_credential_revision,
            ):
                raise ConflictError(
                    "configuration_revision_conflict", "连接已变化，请载入最新配置。"
                )
            fields = data.model_fields_set
            config = data.public_config if "public_config" in fields else row.public_config
            auth = data.auth_type if "auth_type" in fields else row.auth_type
            self.validate(row.provider_key, auth, config)
            if fields & {"credential", "environment", "oauth_client_secret"}:
                raise InvalidInputError("tool_credentials_invalid", "平台工作区不使用凭据。")
            changed = config != row.public_config or any(
                (k in fields and getattr(data, k) != getattr(row, k) for k in ("name", "enabled"))
            )
            if config != row.public_config:
                row.approved_catalog = native_catalog(config.get("workspace_mode", "virtual"))
                row.catalog_revision += 1
            if changed:
                row.config_revision += 1
            row.public_config = config
            for k in ("name", "enabled"):
                if k in fields:
                    setattr(row, k, getattr(data, k))
            db.flush()
            return self.read(row)

    def delete(self, actor, id, expected_config_revision, expected_credential_revision):
        require_permission(actor, "tools:update")
        with self.database.transaction() as db:
            reserve_writer(db, WorkspaceProfile.__table__)
            row = self.require(db, id, actor.user_id)
            if (row.config_revision, row.credential_revision) != (
                expected_config_revision,
                expected_credential_revision,
            ):
                raise ConflictError(
                    "configuration_revision_conflict", "连接已变化，请载入最新配置。"
                )
            self.check_references(db, [id])
            db.delete(row)
