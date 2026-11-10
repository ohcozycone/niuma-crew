from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
)

from app.employees.tool_grants import GrantInput
from app.schemas import NonBlankText, OptionalText, RequestModel, omitted_field


class SkillAssignmentInput(RequestModel):
    skill_id: UUID
    enabled: StrictBool = True
    parameters: dict = Field(default_factory=dict)


class SkillAssignmentRead(SkillAssignmentInput):
    revision: int
    updated_at: datetime
    name: str
    ready: bool
    readiness_reason: str | None = None


class KnowledgeConfigurationInput(RequestModel):
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=10)
    mode: Literal["on_demand", "always"] = "on_demand"
    top_k: StrictInt = Field(default=6, ge=1, le=12)


class AgentCreate(RequestModel):
    knowledge: KnowledgeConfigurationInput = Field(default_factory=KnowledgeConfigurationInput)
    tool_grants: list[GrantInput] = Field(default_factory=list, max_length=32)
    name: NonBlankText
    avatar_id: NonBlankText
    code: OptionalText = None
    category: StrictStr = "其他"
    description: StrictStr = ""
    role_label: OptionalText = None
    system_prompt: StrictStr = ""
    model_connection_id: UUID | None = None
    is_active: StrictBool = True
    is_favorite: StrictBool = False
    example_tasks: list[StrictStr] = Field(default_factory=list)
    deliverables: list[StrictStr] = Field(default_factory=list)
    skill_assignments: list[SkillAssignmentInput] = Field(default_factory=list)


class AgentPatch(RequestModel):
    knowledge: KnowledgeConfigurationInput = omitted_field()
    tool_grants: list[GrantInput] = omitted_field()
    expected_revision: StrictInt = Field(gt=0)
    name: NonBlankText = omitted_field()
    avatar_id: NonBlankText = omitted_field()
    code: OptionalText = None
    category: StrictStr = omitted_field()
    description: StrictStr = omitted_field()
    role_label: OptionalText = None
    system_prompt: StrictStr = omitted_field()
    model_connection_id: UUID | None = None
    is_active: StrictBool = omitted_field()
    is_favorite: StrictBool = omitted_field()
    example_tasks: list[StrictStr] = omitted_field()
    deliverables: list[StrictStr] = omitted_field()
    skill_assignments: list[SkillAssignmentInput] = omitted_field()


class AgentResourceCounts(BaseModel):
    """员工共享装配的实际计数。"""

    skills: int = Field(ge=0)
    tools: int = Field(default=0, ge=0)
    knowledge_bases: int = Field(default=0, ge=0)


class AgentRead(AgentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by_user_id: str | None = None
    revision: int
    tool_grants: list[dict] = Field(default_factory=list)
    skill_assignments: list[SkillAssignmentRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    resource_counts: AgentResourceCounts = Field(
        default_factory=lambda: AgentResourceCounts(skills=0)
    )


class PublicAgent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str | None
    name: str
    avatar_id: str
    category: str
    description: str
    role_label: str | None
    is_active: bool
    is_favorite: bool
    example_tasks: list[str]
    deliverables: list[str]
    skill_ids: list[UUID]
    resource_counts: AgentResourceCounts
    model_configured: bool = False


class AgentSkillSummary(BaseModel):
    skill_id: UUID
    name: str
    enabled: bool


class AgentSummary(BaseModel):
    """目录摘要不含指令、装配参数或任务正文。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_by_user_id: str | None = None
    code: str | None
    name: str
    category: str
    description: str
    role_label: str | None
    avatar_id: str
    is_active: bool
    is_favorite: bool
    model_connection_id: UUID | None
    revision: int
    skill_summaries: list[AgentSkillSummary] = Field(default_factory=list)
    resource_counts: AgentResourceCounts = Field(
        default_factory=lambda: AgentResourceCounts(skills=0)
    )
    updated_at: datetime


class UsageSkill(BaseModel):
    skill_id: UUID
    name: str
    enabled: bool
    ready: bool
    readiness_reason: str | None


class AgentUsage(BaseModel):
    id: UUID
    name: str
    description: str
    avatar_id: str
    is_active: bool
    example_tasks: list[str]
    model_configured: bool
    skill_assignments: list[UsageSkill]
    knowledge: dict | None = None
    tool_grants: list[dict] = Field(default_factory=list)


class OrganizationRulesUpdate(RequestModel):
    instructions: Annotated[StrictStr, Field(max_length=20000)]
    revision: Annotated[StrictInt, Field(ge=0)]

    @field_validator("instructions")
    @classmethod
    def normalize_empty(cls, value: str) -> str:
        return value if value.strip() else ""


class OrganizationRulesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instructions: str
    revision: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AgentConfiguration:
    id: str
    name: str
    revision: int
    updated_at: datetime
    system_prompt: str
    model_connection_id: str
