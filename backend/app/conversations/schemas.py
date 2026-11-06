from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.llm.usage import TokenUsage
from app.schemas import RequestModel


class SendRequest(RequestModel):
    file_ids: list[UUID] = Field(default_factory=list, max_length=16)
    agent_id: UUID | None = Field(default=None, description="首次交办时创建对话所关联的员工。")
    selected_skill_ids: list[UUID] = Field(default_factory=list, max_length=16)

    @field_validator("selected_skill_ids")
    @classmethod
    def unique_skills(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("不能重复选择技能。")
        return value

    client_request_id: UUID
    content: str

    @field_validator("content")
    @classmethod
    def normalize(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("请输入消息。")
        return value


class CreateRequest(SendRequest):
    agent_id: UUID


class RetryRequest(RequestModel):
    client_request_id: UUID


class EmptyRequest(RequestModel):
    pass


class PublicStep(BaseModel):
    id: str
    run_id: str
    sequence: int
    action_key: str
    call_key: str
    parent_action_id: str | None
    kind: str
    status: str
    skill_id: str | None
    safe_details: dict
    output_text: str = ""
    reasoning_text: str = ""
    reasoning_truncated: bool = False
    result_ref: str | None
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class PublicError(BaseModel):
    code: str
    message: str


ConversationStatusFilter = Literal["processing", "replied", "attention", "stopped"]


class ConversationReplySummary(BaseModel):
    id: str
    status: str
    acceptance: Literal["pending", "accepted", "failed"] | None


class ConversationRead(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    owner_user_id: str
    title: str
    version: int
    active_response_id: str | None
    last_response_id: str | None
    matched_response_id: str | None = None
    latest_response: ConversationReplySummary | None = None
    created_at: datetime
    updated_at: datetime


class ConversationStats(BaseModel):
    """Completed question/answer rounds in the caller's visible conversations."""

    completed_rounds: int = Field(ge=0)


class UserMessageView(BaseModel):
    files: list[dict] = Field(default_factory=list)
    id: str
    conversation_id: str
    sequence: int
    role: Literal["user"] = "user"
    content: str
    created_at: datetime
    updated_at: datetime


class AssistantMessageView(BaseModel):
    files: list[dict] = Field(default_factory=list)
    id: str
    conversation_id: str
    sequence: int
    role: Literal["assistant"] = "assistant"
    reply_to_message_id: str
    retry_of_response_id: str | None = None
    version: int
    status: str
    acceptance: Literal["pending", "accepted", "failed"] | None = None
    acceptance_error: str | None = None
    content: str
    content_state: Literal["empty", "draft", "complete", "partial"]
    steps: list[PublicStep]
    usage: TokenUsage | None
    error: PublicError | None
    can_retry: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class MessagePage(BaseModel):
    items: list[UserMessageView | AssistantMessageView]
    next_before_sequence: int | None
    has_more: bool
    next_after_sequence: int | None = None


class ResponseSnapshot(BaseModel):
    conversation: ConversationRead
    response: AssistantMessageView


class AcceptedSubmission(ResponseSnapshot):
    client_request_id: str
    input_message: UserMessageView


class ConversationSnapshot(BaseModel):
    conversation: ConversationRead
    agent: dict
    messages: MessagePage
    question_count: int
    latest_question_id: str | None


class QuestionRead(BaseModel):
    id: str
    sequence: int
    number: int
    preview: str
    created_at: datetime


class QuestionPage(BaseModel):
    items: list[QuestionRead]
    total: int
    next_after_sequence: int | None
    anchor: QuestionRead | None = None


class QuestionPreviewRead(BaseModel):
    """A bounded snapshot of the latest attempt for one stable question."""

    question_id: str
    question: str
    answer: str
    response_id: str
    version: int
    status: str
