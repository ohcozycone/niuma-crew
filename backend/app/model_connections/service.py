"""Configuration CRUD and bounded, explicit provider checks outside transactions."""

import json

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.actor import Actor
from app.auth.permissions import require_permission
from app.employees.models import Agent
from app.errors import ConflictError, InvalidInputError, NotFoundError, ServiceUnavailableError
from app.execution.models import ACTIVE, Run
from app.infrastructure.credentials import CredentialUnavailableError, CredentialVault
from app.infrastructure.database.errors import is_unique_violation
from app.infrastructure.database.session import Database
from app.infrastructure.database.transactions import reserve_writer
from app.knowledge.models import LibraryVectorIndex
from app.llm.config import LLMConfig
from app.llm.embeddings import EmbeddingConfig, embed_texts
from app.model_connections.models import ModelConnection
from app.model_connections.presets import PRESETS, ModelPreset
from app.model_connections.schemas import (
    AgentReference,
    ConnectionCreate,
    ConnectionPatch,
    ConnectionRead,
    ConnectionTestResult,
)
from app.schemas import Page


def credentials_unavailable() -> ServiceUnavailableError:
    return ServiceUnavailableError(
        "model_credentials_unavailable", "模型密钥无法读取，请检查或恢复服务端加密主密钥。"
    )


def require_connection(session, connection_id: str) -> ModelConnection:
    connection = session.get(ModelConnection, connection_id)
    if connection is None:
        raise NotFoundError("model_connection_not_found", "大脑配置不存在，请刷新后重新选择。")
    return connection


def connection_response(session, connection) -> ConnectionRead:
    preset = PRESETS[connection.preset_id]
    agents = session.execute(
        select(Agent.id, Agent.name)
        .where(Agent.model_connection_id == connection.id)
        .order_by(Agent.name, Agent.id)
    )
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
        agents=[AgentReference(id=id, name=name) for id, name in agents],
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


class ModelConnectionService:
    def __init__(self, database: Database, vault: CredentialVault):
        self.database, self.vault = database, vault

    @staticmethod
    def presets(actor: Actor) -> list[ModelPreset]:
        require_permission(actor, "model_connections:read")
        return list(PRESETS.values())

    def _encrypt(self, session, key):
        existing = session.scalar(select(ModelConnection).limit(1))
        # Verify that the configured key can still read stored credentials before writing more.
        if existing:
            self._decrypt(existing.encrypted_api_key)
        try:
            return self.vault.encrypt(key.get_secret_value(), allow_create=existing is None)
        except CredentialUnavailableError:
            raise credentials_unavailable() from None

    def _decrypt(self, encrypted: str) -> str:
        try:
            return self.vault.decrypt(encrypted)
        except CredentialUnavailableError:
            raise credentials_unavailable() from None

    def create(self, data: ConnectionCreate, actor: Actor) -> ConnectionRead:
        require_permission(actor, "model_connections:create")
        preset = PRESETS[data.preset_id]
        model_id = data.model_id if "model_id" in data.model_fields_set else preset.default_model_id
        self.validate_model(preset, model_id)
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
                result = connection_response(session, row)
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
                items=[connection_response(session, row) for row in rows],
                total=total,
                offset=offset,
                limit=limit,
            )

    def get(self, connection_id: str, actor: Actor) -> ConnectionRead:
        require_permission(actor, "model_connections:read")
        with self.database.transaction() as session:
            return connection_response(session, require_connection(session, connection_id))

    def update(self, connection_id: str, data: ConnectionPatch, actor: Actor) -> ConnectionRead:
        require_permission(actor, "model_connections:update")
        try:
            with self.database.transaction() as session:
                reserve_writer(session, ModelConnection.__table__)
                row = require_connection(session, connection_id)
                if "model_id" in data.model_fields_set:
                    self.validate_model(PRESETS[row.preset_id], data.model_id)
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
                result = connection_response(session, row)
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
            if session.scalar(
                select(LibraryVectorIndex.knowledge_base_id)
                .where(LibraryVectorIndex.connection_id == row.id)
                .limit(1)
            ):
                raise ConflictError(
                    "model_connection_in_use", "仍有知识库使用此向量连接，请先移除对应向量索引。"
                )
            if session.scalar(
                select(Run.id)
                .where(Run.model_connection_id == row.id, Run.status.in_(ACTIVE))
                .limit(1)
            ):
                raise ConflictError(
                    "model_connection_in_use", "仍有执行使用这个大脑，请等待结束或停止。"
                )
            if session.scalar(select(Agent.id).where(Agent.model_connection_id == row.id).limit(1)):
                raise ConflictError(
                    "model_connection_in_use", "仍有员工使用这个大脑，请先更换或解除装配。"
                )
            session.delete(row)
            session.flush()

    def assert_current(
        self, connection_id, expected_config_revision, expected_credential_revision, *, db=None
    ):
        if db is not None:
            self._current(db, connection_id, expected_config_revision, expected_credential_revision)
            return
        with self.database.transaction() as session:
            self._current(
                session, connection_id, expected_config_revision, expected_credential_revision
            )

    @staticmethod
    def _current(
        session,
        connection_id,
        expected_config_revision,
        expected_credential_revision,
        capability="chat",
    ):
        row = require_connection(session, connection_id)
        if (
            not row.enabled
            or row.capability != capability
            or (
                expected_config_revision is not None
                and row.config_revision != expected_config_revision
            )
            or (
                expected_credential_revision is not None
                and row.credential_revision != expected_credential_revision
            )
        ):
            raise ConflictError("model_configuration_changed", "大脑配置已更改，请重试。")
        return row

    @staticmethod
    def validate_model(preset: ModelPreset, model_id: str) -> None:
        if preset.capability == "embedding" and model_id != preset.default_model_id:
            raise InvalidInputError(
                "embedding_model_unsupported", "当前向量预设仅支持 BAAI/bge-m3。"
            )

    def resolve_embedding(
        self,
        connection_id: str,
        config_revision: int | None = None,
        credential_revision: int | None = None,
        *,
        db=None,
    ) -> EmbeddingConfig:
        def resolve(session):
            row = self._current(
                session,
                connection_id,
                config_revision,
                credential_revision,
                capability="embedding",
            )
            preset = PRESETS[row.preset_id]
            self.validate_model(preset, row.model_id)
            return EmbeddingConfig(
                connection_id=row.id,
                config_revision=row.config_revision,
                credential_revision=row.credential_revision,
                model_id=row.model_id,
                base_url=preset.base_url,
                api_key=self._decrypt(row.encrypted_api_key),
            )

        if db is not None:
            return resolve(db)
        with self.database.transaction() as session:
            return resolve(session)

    def resolve(
        self,
        connection_id: str,
        expected_config_revision: int | None = None,
        expected_credential_revision: int | None = None,
    ) -> LLMConfig:
        with self.database.transaction() as session:
            row = self._current(
                session, connection_id, expected_config_revision, expected_credential_revision
            )
            model_id, preset_id, encrypted = row.model_id, row.preset_id, row.encrypted_api_key
        return LLMConfig(
            model_id=model_id,
            base_url=PRESETS[preset_id].base_url,
            provider=PRESETS[preset_id].provider,
            api_key=self._decrypt(encrypted),
        )

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
        failure = "服务未返回可识别的模型目录，暂时无法验证；这不代表 Key 一定无效。"
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "GET",
                    config.base_url + "/models",
                    headers={
                        "Authorization": "Bearer " + config.api_key.get_secret_value(),
                        "User-Agent": "AgentPlatform/0.1",
                        "Accept": "application/json",
                    },
                ) as response:
                    if response.status_code in (401, 403):
                        return ConnectionTestResult(
                            ok=False,
                            message="服务拒绝访问，请检查所选预设的 API Key、账户状态及模型访问权限。",
                        )
                    if response.status_code == 429:
                        return ConnectionTestResult(ok=False, message="服务限流，请稍后重试。")
                    if response.status_code != 200:
                        return ConnectionTestResult(
                            ok=False,
                            message=f"服务返回 HTTP {response.status_code}，未完成连接检查。",
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 1048576:
                            return ConnectionTestResult(ok=False, message=failure)
            payload = json.loads(body)
            models = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(models, list):
                return ConnectionTestResult(ok=False, message=failure)
            found = any(
                isinstance(item, dict) and item.get("id") == config.model_id for item in models
            )
            return ConnectionTestResult(
                ok=found,
                message=(
                    "凭证与模型目录检查通过；尚未验证内容生成或 Agent 任务。"
                    if found
                    else "已连接，但当前 Model ID 不在可见模型目录中，请核对模型或订阅权限。"
                ),
            )
        except httpx.TimeoutException:
            return ConnectionTestResult(ok=False, message="连接检查超时，请稍后重试。")
        except httpx.HTTPError:
            return ConnectionTestResult(
                ok=False, message="无法连接模型服务，请检查服务状态和后端网络。"
            )
        except (ValueError, UnicodeError):
            return ConnectionTestResult(ok=False, message=failure)
