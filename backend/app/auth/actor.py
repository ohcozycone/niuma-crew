"""Current trusted identity, independent of HTTP transport and database sessions."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Actor:
    kind: str
    session_id: str
    user_id: str | None
    username: str | None
    role: str
    expires_at: datetime
