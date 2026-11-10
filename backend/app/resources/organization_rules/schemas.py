from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)

from app.common.schemas import RequestModel


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
