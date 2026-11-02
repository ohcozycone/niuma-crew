"""Typed values stored as portable text in the configuration tables."""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Text, inspect, text
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import TypeDecorator


def new_uuid() -> str:
    return str(uuid4())


def normalize_uuid(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("标识必须是 UUID 字符串。")
    return str(UUID(value))


def utc_now() -> datetime:
    return datetime.now(UTC)


class UUIDText(TypeDecorator[str]):
    """Bind identifiers in one canonical, hyphenated lowercase representation."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else normalize_uuid(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Keep timezone-aware Python values and fixed-width UTC text in SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("时间必须包含时区。")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def process_result_value(self, value, dialect):
        return None if value is None else datetime.fromisoformat(value).astimezone(UTC)


class StringListJSON(TypeDecorator[list[str]]):
    """Validate list elements at the backend boundary; SQL also checks array shape."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("内容必须是字符串数组。")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def process_result_value(self, value, dialect):
        return json.loads(value)


UTC_TIMESTAMP_DEFAULT = text("(strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')")


class IdentityTimestamps:
    """Stable identity and timestamps for an agent or a skill definition."""

    id: Mapped[str] = mapped_column(UUIDText(), primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT, onupdate=utc_now
    )

    @validates("id")
    def validate_id(self, key: str, value: str) -> str:
        value = normalize_uuid(value)
        identity = inspect(self).identity
        if identity is not None and identity[0] != value:
            raise ValueError("已保存记录的 ID 不可修改。")
        return value


def required_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("必填文本不能为空。")
    return value.strip()


def optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("内容必须是字符串或空值。")
    return value.strip() or None
