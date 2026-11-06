"""Shared identifiers, text normalization and UTC time; no persistence dependency."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4


def new_uuid() -> str:
    return str(uuid4())


def normalize_uuid(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("标识必须是 UUID 字符串。")
    return str(UUID(value))


def utc_now() -> datetime:
    return datetime.now(UTC)


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


def digest(value: object) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
