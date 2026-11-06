"""Write-only secrets and explicitly enumerated response fields."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
)

from app.schemas import RequestModel, omitted_field

Name = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)
]
ModelId = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$",
    ),
]
ApiKey = Annotated[SecretStr, Field(min_length=1, max_length=4096)]


class KeyValidation(RequestModel):
    @field_validator("api_key", check_fields=False, mode="before")
    @classmethod
    def clean_key(cls, value):
        if (
            not isinstance(value, str)
            or not value.strip()
            or any(ord(c) < 33 or ord(c) > 126 for c in value.strip())
        ):
            raise ValueError("API Key 必须为非空可打印 ASCII 字符，不能包含空白。")
        return value.strip()


class ConnectionCreate(KeyValidation):
    enabled: StrictBool = True
    name: Name
    preset_id: Literal["kimi-code", "zhipu", "deepseek", "siliconflow-embedding"] = "kimi-code"
    model_id: ModelId = "kimi-for-coding"
    api_key: ApiKey


class ConnectionPatch(KeyValidation):
    expected_config_revision: StrictInt = Field(gt=0)
    expected_credential_revision: StrictInt = Field(gt=0)
    enabled: StrictBool = omitted_field()
    name: Name = omitted_field()
    model_id: ModelId = omitted_field()
    api_key: ApiKey = omitted_field()


class AgentReference(BaseModel):
    id: UUID
    name: str


class ConnectionRead(BaseModel):
    enabled: bool
    capability: Literal["chat", "embedding"]
    config_revision: int
    credential_revision: int
    id: UUID
    name: str
    preset_id: str
    provider: str
    protocol: str
    base_url: str
    model_id: str
    has_api_key: bool
    agents: list[AgentReference]
    created_at: datetime
    updated_at: datetime


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str


class ConnectionTestRequest(RequestModel):
    pass
