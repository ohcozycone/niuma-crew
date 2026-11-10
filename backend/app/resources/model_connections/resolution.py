from app.common.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.infrastructure.credentials import CredentialUnavailableError
from app.infrastructure.llm.config import LLMConfig
from app.infrastructure.llm.embeddings import EmbeddingConfig
from app.resources.model_connections.models import ModelConnection
from app.resources.model_connections.presets import PRESETS, ModelPreset


def credentials_unavailable() -> ServiceUnavailableError:
    return ServiceUnavailableError(
        "model_credentials_unavailable", "模型密钥无法读取，请检查或恢复服务端加密主密钥。"
    )


def require_connection(session, connection_id: str) -> ModelConnection:
    connection = session.get(ModelConnection, connection_id)
    if connection is None:
        raise NotFoundError("model_connection_not_found", "大脑配置不存在，请刷新后重新选择。")
    return connection


class ModelResolution:
    def __init__(self, database, vault):
        self.database, self.vault = database, vault

    def _decrypt(self, encrypted: str) -> str:
        try:
            return self.vault.decrypt(encrypted)
        except CredentialUnavailableError:
            raise credentials_unavailable() from None

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
