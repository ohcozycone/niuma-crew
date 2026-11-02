"""Skill inputs and responses for the current reusable definition."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator

from app.schemas import NonBlankText, RequestModel, omitted_field
from app.skills.parameters import validate_schema


class SkillFileInput(RequestModel):
    path: StrictStr
    content: StrictStr | None = None
    content_base64: StrictStr | None = None


class SkillFileRead(BaseModel):
    path: str
    content_hash: str
    size: int
    media_type: str
    is_text: bool


class SkillImport(RequestModel):
    archive_base64: StrictStr = Field(max_length=16 * 1024 * 1024 + 16)
    name: NonBlankText | None = None
    category: StrictStr = "其他"


class SkillImportPreview(BaseModel):
    name: str
    protocol_name: str
    description: str
    skill_md: str
    files: list[SkillFileRead]
    warnings: list[str]


class SkillFileContent(BaseModel):
    path: str
    media_type: str
    is_text: bool
    content: str | None = None
    content_base64: str | None = None


class SkillConfiguration(RequestModel):
    @field_validator("configuration_schema", check_fields=False)
    @classmethod
    def schema_valid(cls, value):
        return validate_schema(value)


class SkillCreate(SkillConfiguration):
    configuration_schema: dict = Field(default_factory=dict)
    is_active: StrictBool = True
    name: NonBlankText | None = None
    category: StrictStr = "其他"
    description: StrictStr = ""
    instructions: StrictStr = ""
    input_description: StrictStr = ""
    output_description: StrictStr = ""
    example: StrictStr = ""
    skill_md: StrictStr = ""
    package_files: list[SkillFileInput] | None = Field(default=None, max_length=128)


class SkillPatch(SkillConfiguration):
    expected_revision: StrictInt = Field(gt=0)
    configuration_schema: dict = omitted_field()
    is_active: StrictBool = omitted_field()
    name: NonBlankText | None = omitted_field()
    category: StrictStr = omitted_field()
    description: StrictStr = omitted_field()
    instructions: StrictStr = omitted_field()
    input_description: StrictStr = omitted_field()
    output_description: StrictStr = omitted_field()
    example: StrictStr = omitted_field()
    skill_md: StrictStr = omitted_field()
    package_files: list[SkillFileInput] = omitted_field()


class SkillRead(SkillCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    revision: int
    assignment_count: int = 0
    created_at: datetime
    updated_at: datetime
    protocol_name: str = ""
    files: list[SkillFileRead] = Field(default_factory=list)
    source_path: str | None = None
    source_missing: bool = False


class SkillSyncItem(BaseModel):
    name: str
    status: str
    skill_id: str | None = None
    message: str = ""


class SkillSyncResult(BaseModel):
    directory: str
    items: list[SkillSyncItem]


class PublicSkill(BaseModel):
    assignment_count: int = 0
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    category: str
    description: str
    input_description: str
    output_description: str
    example: str


class SkillSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    category: str
    description: str
    is_active: bool
    revision: int
    assignment_count: int = 0
    updated_at: datetime


class SkillLibraryRead(BaseModel):
    directory: str
