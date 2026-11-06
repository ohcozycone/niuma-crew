"""Connection writes keep credentials write-only."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr, StrictBool, StrictInt, field_validator

from app.schemas import NonBlankText, RequestModel, omitted_field


class ToolConnectionCreate(RequestModel):
    service_id: str | None = None
    account_scope: Literal["personal", "shared"] = "personal"
    name: NonBlankText
    kind: Literal["native", "mcp_http", "mcp_stdio"]
    provider_key: Literal["workspace"] | None = None
    auth_type: Literal["none", "bearer", "header", "env", "oauth"] = "none"
    oauth_client_secret: SecretStr | None = Field(default=None, max_length=4096)
    public_config: dict = Field(default_factory=dict)
    credential: SecretStr | None = Field(default=None, max_length=4096)
    environment: dict[str, SecretStr] = Field(default_factory=dict, max_length=32)
    enabled: StrictBool = True

    @field_validator("service_id")
    @classmethod
    def valid_service(cls, value):
        return str(UUID(value)) if value is not None else None


class ToolConnectionPatch(RequestModel):
    expected_config_revision: StrictInt = Field(gt=0)
    expected_credential_revision: StrictInt = Field(gt=0)
    name: NonBlankText = omitted_field()
    public_config: dict = omitted_field()
    auth_type: Literal["none", "bearer", "header", "env", "oauth"] = omitted_field()
    oauth_client_secret: SecretStr = omitted_field()
    credential: SecretStr = omitted_field()
    environment: dict[str, SecretStr] = omitted_field()
    clear_credential: StrictBool = False
    enabled: StrictBool = omitted_field()


class CatalogApprove(RequestModel):
    expected_config_revision: StrictInt = Field(gt=0)
    expected_catalog_revision: StrictInt = Field(gt=0)
    candidate_hash: str


class ToolConnectionRead(BaseModel):
    id: str
    name: str
    kind: str
    provider_key: str | None
    auth_type: str
    public_config: dict
    has_credential: bool
    oauth_status: str | None = None
    enabled: bool
    config_revision: int
    credential_revision: int
    catalog_revision: int
    service_id: str | None
    account_scope: str
    created_by_user_id: str | None
    tool_annotations: dict
    annotations_revision: int
    approved_catalog: list[dict]
    approved_instructions: str
    discovery_candidate: dict | None


class McpInputField(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    is_required: StrictBool = True
    is_secret: StrictBool = True


class McpServiceCreate(RequestModel):
    name: NonBlankText
    description: str = Field(default="", max_length=4000)
    transport: Literal["http", "stdio"] = "http"
    url: str | None = Field(default=None, max_length=2048)
    command: str | None = Field(default=None, max_length=2048)
    args: list[str] = Field(default_factory=list, max_length=64)
    env_keys: list[str] = Field(default_factory=list, max_length=32)
    input_fields: list[McpInputField] = Field(default_factory=list, max_length=32)


class McpServicePatch(RequestModel):
    expected_revision: StrictInt = Field(gt=0)
    name: NonBlankText = omitted_field()
    description: str = omitted_field()
    enabled: StrictBool = omitted_field()
    env_keys: list[str] = Field(default_factory=list, max_length=32)


class ToolAnnotation(RequestModel):
    display_name: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=2000)


class CatalogAnnotations(RequestModel):
    expected_annotations_revision: StrictInt = Field(gt=0)
    annotations: dict[str, ToolAnnotation] = Field(max_length=128)


class McpConfigImport(RequestModel):
    configuration: str = Field(max_length=65536)


class McpServiceRead(BaseModel):
    id: str
    name: str
    description: str
    transport: Literal["http", "stdio"]
    url: str | None
    command: str | None
    args: list[str]
    env_keys: list[str]
    input_fields: list[McpInputField]
    owner_user_id: str | None
    revision: int
    enabled: bool


class McpImportEntry(BaseModel):
    name: str
    transport: Literal["http", "stdio"]
    url: str | None
    command: str | None
    args: list[str]
    env_keys: list[str]
    auth_type: str
    header_name: str | None
    has_credential: bool
    host: str | None = None
    description: str = ""
    input_fields: list[McpInputField] = Field(default_factory=list)


class McpImportPreview(BaseModel):
    entries: list[McpImportEntry]
    warnings: list[str] = Field(default_factory=list)


class ToolCapabilities(BaseModel):
    stdio_enabled: bool
    stdio_registration_allowed: bool
    max_stdio_processes: int
