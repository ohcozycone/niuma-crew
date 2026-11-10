from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.common.errors import ConflictError
from app.common.schemas import Page
from app.infrastructure.credentials import CredentialUnavailableError, CredentialVault
from app.infrastructure.database.errors import is_unique_violation
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.infrastructure.llm.config import LLMConfig
from app.infrastructure.llm.embeddings import EmbeddingConfig, embed_texts
from app.infrastructure.llm.probe import probe_chat
from app.resources.model_connections.models import ModelConnection
from app.resources.model_connections.presets import PRESETS, ModelPreset
from app.resources.model_connections.resolution import (
    ModelResolution,
    credentials_unavailable,
    require_connection,
)
from app.resources.model_connections.schemas import (
    AgentReference,
    ConnectionCreate,
    ConnectionPatch,
    ConnectionRead,
    ConnectionTestResult,
)


def connection_response(session, connection, employee_references) -> ConnectionRead:
    preset = PRESETS[connection.preset_id]
    agents = employee_references(session, connection.id)
    return ConnectionRead(
        enabled=connection.enabled,
        capability=connection.capability,
        config_revision=connection.config_revision,
        credential_revision=connection.credential_revision,
        id=connection.id,
        name=connection.name,
        preset_id=connection.preset_id,
        provider=preset.provider,
        protocol=preset.protocol,
        base_url=preset.base_url,
        model_id=connection.model_id,
        has_api_key=bool(connection.encrypted_api_key),
        agents=[AgentReference(**ref) for ref in agents],
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


class ModelConnectionService:
    def __init__(
        self, database: Database, vault: CredentialVault, *, employee_references, check_references
    ):
        self.database, self.vault = database, vault
        self.resolution = ModelResolution(database, vault)
        self.employee_references = employee_references
        self.check_references = check_references

    @staticmethod
    def presets(actor: Actor) -> list[ModelPreset]:
        require_permission(actor, "model_connections:read")
        return list(PRESETS.values())

    def _encrypt(self, session, key):
        existing = session.scalar(select(ModelConnection).limit(1))
        # 先确认现有密文可解密，再保存新凭据。
        if existing:
            self.resolution._decrypt(existing.encrypted_api_key)
        try:
            return self.vault.encrypt(key.get_secret_value(), allow_create=existing is None)
        except CredentialUnavailableError:
            raise credentials_unavailable() from None

    def create(self, data: ConnectionCreate, actor: Actor) -> ConnectionRead:
        require_permission(actor, "model_connections:create")
        preset = PRESETS[data.preset_id]
        model_id = data.model_id if "model_id" in data.model_fields_set else preset.default_model_id
        self.resolution.validate_model(preset, model_id)
        try:
            with self.database.transaction() as session:
                reserve_writer(session, ModelConnection.__table__)
                row = ModelConnection(
                    enabled=data.enabled,
                    name=data.name,
                    preset_id=data.preset_id,
                    capability=preset.capability,
                    model_id=model_id,
                    encrypted_api_key=self._encrypt(session, data.api_key),
                )
                session.add(row)
                session.flush()
                result = connection_response(session, row, self.employee_references)
            return result
        except IntegrityError as error:
            if not is_unique_violation(error, table="model_connections", columns=("name",)):
                raise
            raise ConflictError(
                "model_connection_conflict", "大脑名称已存在，请换一个名称。"
            ) from error

    def list(self, offset=0, limit=20, *, actor: Actor) -> Page[ConnectionRead]:
        require_permission(actor, "model_connections:read")
        with self.database.transaction() as session:
            total = session.scalar(select(func.count()).select_from(ModelConnection))
            rows = session.scalars(
                select(ModelConnection)
                .order_by(ModelConnection.created_at.desc(), ModelConnection.id)
                .offset(offset)
                .limit(limit)
            )
            return Page(
                items=[connection_response(session, row, self.employee_references) for row in rows],
                total=total,
                offset=offset,
                limit=limit,
            )

    def get(self, connection_id: str, actor: Actor) -> ConnectionRead:
        require_permission(actor, "model_connections:read")
        with self.database.transaction() as session:
            return connection_response(
                session, require_connection(session, connection_id), self.employee_references
            )

    def update(self, connection_id: str, data: ConnectionPatch, actor: Actor) -> ConnectionRead:
        require_permission(actor, "model_connections:update")
        try:
            with self.database.transaction() as session:
                reserve_writer(session, ModelConnection.__table__)
                row = require_connection(session, connection_id)
                if "model_id" in data.model_fields_set:
                    self.resolution.validate_model(PRESETS[row.preset_id], data.model_id)
                if (row.config_revision, row.credential_revision) != (
                    data.expected_config_revision,
                    data.expected_credential_revision,
                ):
                    raise ConflictError(
                        "configuration_revision_conflict", "大脑配置或凭证已改变，请刷新后核对。"
                    )
                changes = data.model_dump(
                    exclude_unset=True,
                    exclude={"api_key", "expected_config_revision", "expected_credential_revision"},
                )
                if any(getattr(row, key) != value for key, value in changes.items()):
                    row.config_revision += 1
                for key, value in changes.items():
                    setattr(row, key, value)
                if "api_key" in data.model_fields_set:
                    row.encrypted_api_key = self._encrypt(session, data.api_key)
                    row.credential_revision += 1
                session.flush()
                result = connection_response(session, row, self.employee_references)
            return result
        except IntegrityError as error:
            if not is_unique_violation(error, table="model_connections", columns=("name",)):
                raise
            raise ConflictError(
                "model_connection_conflict", "大脑名称已存在，请换一个名称。"
            ) from error

    def delete(self, connection_id: str, actor: Actor) -> None:
        require_permission(actor, "model_connections:delete")
        with self.database.transaction() as session:
            reserve_writer(session, ModelConnection.__table__)
            row = require_connection(session, connection_id)
            self.check_references(session, connection_id)
            session.delete(row)
            session.flush()

    def test(self, connection_id: str, actor: Actor) -> ConnectionTestResult:
        require_permission(actor, "model_connections:test")
        with self.database.transaction() as session:
            capability = require_connection(session, connection_id).capability
        if capability == "embedding":
            config = self.resolve_embedding(connection_id)
            embed_texts(config, ["知识库向量连接测试。"])
            self.resolve_embedding(
                connection_id, config.config_revision, config.credential_revision
            )
            return ConnectionTestResult(
                ok=True, message="真实向量调用通过：返回有效的 1024 维向量。"
            )
        config = self.resolve(connection_id)
        return ConnectionTestResult(**probe_chat(config))

    def assert_current(
        self, connection_id, expected_config_revision, expected_credential_revision, *, db=None
    ):
        self.resolution.assert_current(
            connection_id, expected_config_revision, expected_credential_revision, db=db
        )

    def resolve(
        self, connection_id, expected_config_revision=None, expected_credential_revision=None
    ) -> LLMConfig:
        return self.resolution.resolve(
            connection_id, expected_config_revision, expected_credential_revision
        )

    def resolve_embedding(
        self, connection_id, config_revision=None, credential_revision=None, *, db=None
    ) -> EmbeddingConfig:
        return self.resolution.resolve_embedding(
            connection_id, config_revision, credential_revision, db=db
        )
