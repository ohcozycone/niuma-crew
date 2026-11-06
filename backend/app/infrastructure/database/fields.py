"""Typed values stored as portable text in the configuration tables."""

import json
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Text, inspect, text
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import TypeDecorator

from app.values import new_uuid, normalize_uuid, utc_now


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


class NumericID(TypeDecorator[str]):
    """Store a twelve-digit key as INTEGER and expose its canonical string."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = str(value)
        if len(value) != 12 or not value.isascii() or not value.isdigit() or value[0] == "0":
            raise ValueError("标识必须是 12 位十进制数字。")
        return int(value)

    def process_result_value(self, value, dialect):
        return None if value is None else str(value)


class NumericIdentityTimestamps:
    id: Mapped[str] = mapped_column(NumericID(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=UTC_TIMESTAMP_DEFAULT, onupdate=utc_now
    )

    @validates("id")
    def validate_id(self, key: str, value: str) -> str:
        value = str(value)
        if len(value) != 12 or not value.isascii() or not value.isdigit() or value[0] == "0":
            raise ValueError("标识必须是 12 位十进制数字。")
        identity = inspect(self).identity
        if identity is not None and identity[0] != value:
            raise ValueError("已保存记录的 ID 不可修改。")
        return value
