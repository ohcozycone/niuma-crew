"""Public records in the unified capability directory."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_serializer


class CapabilityRead(BaseModel):
    id: str
    name: str
    description: str
    kind: Literal["skill", "mcp_http", "mcp_stdio"]
    enabled: bool
    created_at: datetime
    protocol_name: str | None

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        # This catalog previously returned datetime.isoformat() through plain JSON encoding.
        return value.isoformat()
